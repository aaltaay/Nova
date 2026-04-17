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
    RVOL_LOOKBACK_DAYS,
)

logger = logging.getLogger(__name__)


async def universe_enrichment_loop() -> None:
    """Batch-fetch Alpaca snapshots for the full HOD universe every ~30 s.

    For each symbol, computes: price, prev_close, change_pct, gap_pct, volume,
    rvol (using main._avg_volume_cache), and writes into hod_momo._ticker_snaps.
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
            logger.info(
                "HOD Momo enrichment: fetching snapshots for %d symbols", len(symbols)
            )

            # Run blocking HTTP calls in executor to avoid stalling the event loop
            loop = asyncio.get_event_loop()
            snaps: dict = await loop.run_in_executor(
                None, lambda: _main._fetch_snapshots(symbols, headers)
            )

            if not snaps:
                logger.warning("HOD Momo enrichment: snapshot fetch returned empty")
                continue

            # Progressively fill avg_vol for symbols that are missing it — one chunk of
            # 200 per enrichment cycle to avoid the 20s×60-batch timeout that blocks the
            # event loop.  Most symbols become enriched within a few cycles.
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
                    avg_vol = _main._avg_volume_cache.get(sym)

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

                    rvol: float | None = None
                    if avg_vol and avg_vol > 0 and volume > 0:
                        rvol = round(volume / avg_vol, 2)

                    _hod_momo.update_ticker_snapshot(
                        sym,
                        price=float(price),
                        rvol=rvol,
                        gap_pct=gap_pct,
                        volume=volume if volume else None,
                        change_pct=change_pct,
                    )
                    enriched += 1
                except Exception as sym_exc:
                    logger.debug("HOD Momo enrichment: error for %s: %s", sym, sym_exc)

            logger.info(
                "HOD Momo enrichment: enriched %d / %d symbols", enriched, len(snaps)
            )

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("HOD Momo universe enrichment loop error: %s", exc)


async def fundamentals_enrichment_loop() -> None:
    """Drain the fundamentals queue, fetching float + 52wk-high for each symbol.

    Called every HOD_MOMO_FUNDAMENTALS_QUEUE_INTERVAL_SEC.  Processes one symbol
    per tick to avoid hammering yfinance.
    """
    import main as _main

    while True:
        try:
            await asyncio.sleep(HOD_MOMO_FUNDAMENTALS_QUEUE_INTERVAL_SEC)

            sym = _hod_momo.pop_fundamentals_request()
            if not sym:
                continue

            logger.debug("HOD Momo fundamentals: fetching for %s", sym)

            loop = asyncio.get_event_loop()
            fund: dict = await loop.run_in_executor(
                None, lambda: _main._fetch_fundamentals(sym)
            )

            float_shares = fund.get("float_shares")
            fifty_two_week_high = fund.get("fifty_two_week_high")

            snap = _hod_momo._ticker_snaps.get(sym)
            if snap is None:
                # Symbol has no price yet — keep it warm for next enrichment cycle
                _hod_momo.mark_needs_fundamentals(sym)
                continue

            _hod_momo.update_ticker_snapshot(
                sym,
                price=snap.price,
                float_shares=float_shares,
                fifty_two_week_high=fifty_two_week_high,
            )
            logger.debug(
                "HOD Momo fundamentals: %s float=%s 52wkH=%s",
                sym, float_shares, fifty_two_week_high,
            )

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("HOD Momo fundamentals loop error: %s", exc)
