"""
HOD Momo universe enrichment loops.

Kept separate from hod_momo.py to keep main.py thin (backend-modularity rule).

Two loops are registered as asyncio tasks in main.py lifespan:
  - universe_enrichment_loop() — batch-fetches Alpaca snapshots for all HOD
    universe symbols every HOD_MOMO_ENRICH_INTERVAL_SEC, then writes RVOL /
    gap / change into hod_momo._ticker_snaps via hod_momo.update_ticker_snapshot().
  - fundamentals_enrichment_loop() — drains the fundamentals queue produced by
    hod_momo.mark_needs_fundamentals(); fetches float_shares + fifty_two_week_high
    via main._fetch_fundamentals(sym) and writes them into _ticker_snaps.

Both loops call back into main.py for HTTP helpers to avoid duplicating that code;
the import is done lazily inside the loops to prevent circular imports.

Feed-level RVOL routing (§ yfinance fallback + Warrior pace):
  - SIP feed: pace RVOL = Alpaca volume / (Alpaca avg × elapsed 04:00–16:00 ET frac)
  - IEX feed: same formula with yfinance current_volume / average_volume
  - HOD_MOMO_RVOL_USE_PACE=False falls back to raw daily/avg
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, timedelta

import hod_momo as _hod_momo
from constants import (
    HOD_MOMO_ENRICH_INTERVAL_SEC,
    HOD_MOMO_FUNDAMENTALS_QUEUE_INTERVAL_SEC,
    HOD_MOMO_FUNDAMENTALS_BATCH_SIZE,
    HOD_MOMO_RVOL_USE_PACE,
    RVOL_LOOKBACK_DAYS,
)
from market import pace_relative_volume

logger = logging.getLogger(__name__)


async def universe_enrichment_loop() -> None:
    """Batch-fetch Alpaca snapshots for the full HOD universe every ~30 s.

    For each symbol, computes: price, prev_close, change_pct, gap_pct, volume,
    rvol (using main._avg_volume_cache or yfinance fallback), and writes into
    hod_momo._ticker_snaps.
    """
    import main as _main  # lazy to avoid circular import

    while True:
        try:
            await asyncio.sleep(HOD_MOMO_ENRICH_INTERVAL_SEC)

            universe = _main.get_hod_momo_universe()
            if not universe:
                logger.debug("HOD Momo enrichment: universe empty, skipping")
                continue

            headers = _main._alpaca_headers()
            if not headers:
                logger.debug("HOD Momo enrichment: no Alpaca headers, skipping")
                continue

            symbols = list(universe)
            feed = _main._get_feed()
            is_iex = feed != "sip"

            logger.info(
                "HOD Momo enrichment: fetching snapshots for %d symbols (feed=%s)",
                len(symbols), feed,
            )

            # Run blocking HTTP calls in executor to avoid stalling the event loop
            loop = asyncio.get_event_loop()
            snaps: dict = await loop.run_in_executor(
                None, lambda: _main._fetch_snapshots(symbols, headers)
            )

            if not snaps:
                logger.warning("HOD Momo enrichment: snapshot fetch returned empty")
                continue

            # ── SIP path: fill avg_vol from Alpaca bars (consolidated) ──────────
            if not is_iex:
                snap_syms = list(snaps.keys())
                missing_avg = [s for s in snap_syms if s not in _main._avg_volume_cache]
                if missing_avg:
                    chunk = missing_avg[:200]
                    try:
                        await loop.run_in_executor(
                            None, lambda: _main._ensure_avg_volume(chunk, headers)
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
                    prev_bar = snap.get("prevDailyBar") or {}

                    price = latest_trade.get("p") or daily_bar.get("c") or 0.0
                    if not price:
                        continue

                    # Correct prev-close using the same timestamp-aware helper main.py uses
                    prev_close = _main._pick_prev_close(snap) or 0.0
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
                        fund = _main._fundamentals_cache.get(sym, {})
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
                        elif sym not in _main._fundamentals_cache:
                            _hod_momo.mark_needs_fundamentals(sym)
                            fundamentals_queued += 1
                    else:
                        avg_vol = _main._avg_volume_cache.get(sym)
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
    import main as _main

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
                    None, lambda s=sym: _main._fetch_fundamentals(s)
                )

                float_shares = fund.get("float_shares")
                fifty_two_week_high = fund.get("fifty_two_week_high")

                snap = _hod_momo._ticker_snaps.get(sym)
                if snap is None:
                    # Symbol has no price yet — keep it warm for next enrichment cycle
                    _hod_momo.mark_needs_fundamentals(sym)
                    continue

                # On IEX, also compute RVOL from yfinance data now that we have it
                rvol: float | None = None
                rvol_source: str | None = None
                feed = _main._get_feed()
                if feed != "sip":
                    yf_avg = fund.get("average_volume")
                    yf_vol = fund.get("current_volume")
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
