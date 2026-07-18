"""
HOD Momo universe enrichment loops.

Kept separate from hod_momo.py to keep main.py thin (backend-modularity rule).

Two loops are registered as asyncio tasks in main.py lifespan:
  - universe_enrichment_loop() — batch-fetches Alpaca snapshots for all HOD
    universe symbols every HOD_MOMO_ENRICH_INTERVAL_SEC, then writes RVOL /
    gap / change through hod_momo.update_ticker_snapshot().
  - fundamentals_enrichment_loop() — drains the fundamentals queue produced by
    hod_momo.mark_needs_fundamentals(); fetches float_shares + fifty_two_week_high
    and writes them through the HOD snapshot API.

Feed-level RVOL routing (§ yfinance fallback + Warrior pace):
  - SIP feed: pace RVOL = Alpaca volume / (Alpaca avg × elapsed 04:00–16:00 ET frac)
  - IEX feed: same formula with yfinance current_volume / average_volume
  - HOD_MOMO_RVOL_USE_PACE=False falls back to raw daily/avg
"""

from __future__ import annotations

import asyncio
import logging

from alpaca import _get_discovery_provider, _alpaca_headers, _get_feed
import hod_momo as _hod_momo
from constants import (
    HOD_MOMO_ENRICH_INTERVAL_SEC,
    HOD_MOMO_FUNDAMENTALS_QUEUE_INTERVAL_SEC,
    HOD_MOMO_FUNDAMENTALS_BATCH_SIZE,
    HOD_MOMO_RVOL_USE_PACE,
)
from market import pace_relative_volume
from runtime_state import get_runtime_state

logger = logging.getLogger(__name__)


def ibkr_avg_volume(symbol: str) -> float | None:
    """avg_volume for discovery=ibkr — yfinance only (single-market-data-feed rule).

    Alpaca IEX-feed daily bars (``state.avg_volume_cache``, populated by
    ``universe.ensure_avg_volume``) capture only a sliver of consolidated volume
    for thin microcaps and silently understated avg_volume, blowing up pace RVOL
    100x-3000x+ (live-observed: CJMB 7016x, LBGJ 1526x, ATPC 3025x) for exactly
    the low-float/low-volume names this scanner targets. Never read that cache
    here, even as a fallback — matches fundamentals_enrichment_loop's ibkr path.
    """
    from fundamentals import _fundamentals_cache

    fund = _fundamentals_cache.get(symbol, {})
    avg_vol = fund.get("average_volume")
    return float(avg_vol) if avg_vol else None


async def universe_enrichment_loop() -> None:
    """Batch-fetch snapshots for the full HOD universe every ~30 s.

    For each symbol, computes: price, prev_close, change_pct, gap_pct, volume,
    rvol (using avg-volume cache or yfinance fallback), and writes through
    hod_momo.update_ticker_snapshot().
    """
    from ibkr_bridge import run_ibkr
    from scanner import _fetch_snapshots, _pick_prev_close
    from universe import ensure_avg_volume, get_hod_momo_universe
    from fundamentals import _fundamentals_cache

    while True:
        try:
            await asyncio.sleep(HOD_MOMO_ENRICH_INTERVAL_SEC)
            state = get_runtime_state()

            universe = get_hod_momo_universe()
            if not universe:
                logger.debug("HOD Momo enrichment: universe empty, skipping")
                continue

            symbols = list(universe)
            loop = asyncio.get_event_loop()
            provider = _get_discovery_provider()

            # discovery=ibkr: never snapshot the full 200+ universe (starves L1).
            # Enrich only the reserved HOD active pool (≤40); live prices come from
            # scanner_l1 reqMktData. Cold snapshot is a low-priority RVOL backfill.
            if provider == "ibkr":
                from ibkr import discovery as _ibkr_discovery
                from ibkr_bridge import refresh_hod_active_set

                symbols = refresh_hod_active_set() or symbols[:40]
                quotes: dict = await loop.run_in_executor(
                    None,
                    lambda syms=symbols: run_ibkr(
                        _ibkr_discovery.snapshot_quotes(syms, timeout_sec=15.0)
                    ) or {},
                )
                if not quotes:
                    logger.debug(
                        "HOD Momo enrichment: IBKR active-set quotes empty "
                        "(L1 streams own live prices)"
                    )
                    continue

                enriched = 0
                for sym, q in quotes.items():
                    try:
                        price = q.get("price")
                        if not price:
                            continue
                        price_f = float(price)
                        vol = int(q["volume"]) if q.get("volume") is not None else 0
                        prev = q.get("prev_close")
                        change_pct = None
                        if prev:
                            try:
                                prev_f = float(prev)
                                if prev_f > 0:
                                    change_pct = (price_f - prev_f) / prev_f * 100.0
                            except (TypeError, ValueError):
                                change_pct = None

                        avg_for_5min = ibkr_avg_volume(sym)
                        rvol = None
                        rvol_source = None
                        if avg_for_5min and avg_for_5min > 0 and vol > 0:
                            if HOD_MOMO_RVOL_USE_PACE:
                                rvol = pace_relative_volume(vol, avg_for_5min)
                                rvol_source = "ibkr_pace"
                            else:
                                rvol = round(vol / avg_for_5min, 2)
                                rvol_source = "ibkr"

                        _hod_momo.update_ticker_snapshot(
                            sym,
                            price=price_f,
                            rvol=rvol,
                            volume=vol if vol else None,
                            change_pct=change_pct,
                            rvol_source=rvol_source,
                            avg_volume=avg_for_5min,
                        )
                        if avg_for_5min is None:
                            _hod_momo.mark_needs_fundamentals(sym)
                        enriched += 1
                    except Exception as sym_exc:
                        logger.debug("HOD Momo enrichment: IBKR error for %s: %s", sym, sym_exc)

                logger.info(
                    "HOD Momo enrichment: IBKR enriched %d / %d symbols",
                    enriched, len(quotes),
                )
                continue

            headers = _alpaca_headers()
            if not headers:
                logger.debug("HOD Momo enrichment: no Alpaca headers, skipping")
                continue

            feed = _get_feed()
            is_iex = feed != "sip"

            logger.info(
                "HOD Momo enrichment: fetching snapshots for %d symbols (feed=%s)",
                len(symbols), feed,
            )

            snaps: dict = await loop.run_in_executor(
                None, lambda syms=symbols, h=headers: _fetch_snapshots(syms, h)
            )

            if not snaps:
                logger.warning("HOD Momo enrichment: snapshot fetch returned empty")
                continue

            # ── SIP path: fill avg_vol from Alpaca bars (consolidated) ──────────
            if not is_iex:
                snap_syms = list(snaps.keys())
                missing_avg = [s for s in snap_syms if s not in state.avg_volume_cache]
                if missing_avg:
                    chunk = missing_avg[:200]
                    try:
                        await loop.run_in_executor(
                            None, lambda c=chunk, h=headers: ensure_avg_volume(c, h)
                        )
                        logger.debug(
                            "HOD Momo enrichment: avg_vol chunk %d/%d done",
                            len(chunk), len(missing_avg),
                        )
                    except Exception as avg_exc:
                        logger.debug("HOD Momo enrichment: avg_vol chunk failed: %s", avg_exc)

            enriched = 0
            fundamentals_queued = 0
            for sym, snap in snaps.items():
                try:
                    latest_trade = snap.get("latestTrade") or {}
                    daily_bar = snap.get("dailyBar") or {}
                    price = latest_trade.get("p") or daily_bar.get("c") or 0.0
                    if not price:
                        continue

                    # Correct prev-close using the same timestamp-aware helper
                    prev_close = _pick_prev_close(snap) or 0.0
                    volume = int(daily_bar.get("v") or 0)

                    if prev_close and prev_close > 0:
                        change_pct = (price - prev_close) / prev_close * 100.0
                        open_price = daily_bar.get("o") or 0.0
                        gap_pct = (
                            (open_price - prev_close) / prev_close * 100.0
                            if open_price else None
                        )
                    else:
                        change_pct = None
                        gap_pct = None

                    # ── RVOL: Warrior Daily Rate (pace) when enabled ───────────
                    # Pace = today_vol / (avg_daily * fraction of 04:00–16:00 ET).
                    # Raw daily/avg understates mid-morning and mid-day runners.
                    rvol: float | None = None
                    rvol_source: str | None = None

                    avg_for_5min: float | None = None
                    if is_iex:
                        fund = _fundamentals_cache.get(sym, {})
                        yf_avg = fund.get("average_volume")
                        yf_vol = fund.get("current_volume")
                        avg_for_5min = float(yf_avg) if yf_avg else None
                        if yf_avg and yf_avg > 0 and yf_vol and yf_vol > 0:
                            if HOD_MOMO_RVOL_USE_PACE:
                                rvol = pace_relative_volume(yf_vol, yf_avg)
                                rvol_source = "yfinance_pace"
                            else:
                                rvol = round(yf_vol / yf_avg, 2)
                                rvol_source = "yfinance"
                        elif sym not in _fundamentals_cache:
                            _hod_momo.mark_needs_fundamentals(sym)
                            fundamentals_queued += 1
                    else:
                        avg_vol = state.avg_volume_cache.get(sym)
                        avg_for_5min = float(avg_vol) if avg_vol else None
                        if avg_vol and avg_vol > 0 and volume > 0:
                            if HOD_MOMO_RVOL_USE_PACE:
                                rvol = pace_relative_volume(volume, avg_vol)
                                rvol_source = "alpaca_pace"
                            else:
                                rvol = round(volume / avg_vol, 2)
                                rvol_source = "alpaca"

                    _hod_momo.update_ticker_snapshot(
                        sym,
                        price=float(price),
                        rvol=rvol,
                        gap_pct=gap_pct,
                        volume=volume if volume else None,
                        change_pct=change_pct,
                        rvol_source=rvol_source,
                        avg_volume=avg_for_5min,
                    )
                    enriched += 1
                except Exception as sym_exc:
                    logger.debug("HOD Momo enrichment: error for %s: %s", sym, sym_exc)

            logger.info(
                "HOD Momo enrichment: enriched %d / %d symbols (rvol_source=%s, queued_fund=%d)",
                enriched, len(snaps), "yfinance" if is_iex else "alpaca", fundamentals_queued,
            )

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("HOD Momo universe enrichment loop error: %s", exc)


async def fundamentals_enrichment_loop() -> None:
    """Drain the fundamentals queue, fetching float + 52wk-high + avg volume for each symbol.

    Called every HOD_MOMO_FUNDAMENTALS_QUEUE_INTERVAL_SEC.  Processes up to
    HOD_MOMO_FUNDAMENTALS_BATCH_SIZE symbols per tick to warm up faster on IEX.
    """
    from fundamentals import fetch_fundamentals

    while True:
        try:
            await asyncio.sleep(HOD_MOMO_FUNDAMENTALS_QUEUE_INTERVAL_SEC)

            # Process a batch of symbols per tick (was 1, now configurable)
            processed = 0
            for _ in range(HOD_MOMO_FUNDAMENTALS_BATCH_SIZE):
                sym = _hod_momo.pop_fundamentals_request()
                if not sym:
                    break

                logger.debug("HOD Momo fundamentals: fetching for %s", sym)

                loop = asyncio.get_event_loop()
                fund: dict = await loop.run_in_executor(
                    None, lambda s=sym: fetch_fundamentals(s)
                )

                float_shares = fund.get("float_shares")
                fifty_two_week_high = fund.get("fifty_two_week_high")

                snap = _hod_momo.get_ticker_snapshot(sym)
                if snap is None:
                    # Symbol has no price yet — keep it warm for next enrichment cycle
                    _hod_momo.mark_needs_fundamentals(sym)
                    continue

                # On IEX (Alpaca discovery), compute RVOL from yfinance.
                # When discovery=ibkr, keep IBKR pace RVOL — do not overwrite with thin yf volume.
                rvol: float | None = None
                rvol_source: str | None = None
                avg_volume: float | None = None
                provider = _get_discovery_provider()
                feed = _get_feed()
                if provider == "ibkr":
                    yf_avg = fund.get("average_volume")
                    avg_volume = float(yf_avg) if yf_avg else None
                    if avg_volume and snap.volume and snap.volume > 0:
                        if HOD_MOMO_RVOL_USE_PACE:
                            rvol = pace_relative_volume(snap.volume, avg_volume)
                            rvol_source = "ibkr_pace"
                        else:
                            rvol = round(snap.volume / avg_volume, 2)
                            rvol_source = "ibkr"
                elif feed != "sip":
                    yf_avg = fund.get("average_volume")
                    yf_vol = fund.get("current_volume")
                    avg_volume = float(yf_avg) if yf_avg else None
                    if yf_avg and yf_avg > 0 and yf_vol and yf_vol > 0:
                        if HOD_MOMO_RVOL_USE_PACE:
                            rvol = pace_relative_volume(yf_vol, yf_avg)
                            rvol_source = "yfinance_pace"
                        else:
                            rvol = round(yf_vol / yf_avg, 2)
                            rvol_source = "yfinance"

                _hod_momo.update_ticker_snapshot(
                    sym,
                    price=snap.price,
                    float_shares=float_shares,
                    fifty_two_week_high=fifty_two_week_high,
                    rvol=rvol,
                    rvol_source=rvol_source,
                    avg_volume=avg_volume,
                )
                processed += 1
                logger.debug(
                    "HOD Momo fundamentals: %s float=%s 52wkH=%s rvol=%s (src=%s)",
                    sym, float_shares, fifty_two_week_high, rvol, rvol_source,
                )

            if processed > 0:
                logger.info("HOD Momo fundamentals: processed %d symbols this tick", processed)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("HOD Momo fundamentals loop error: %s", exc)
