"""Post-roster-commit hook for the Large Cap table (ADR 014).

Warms fundamentals (yfinance) and schedules background daily-bar fills for
newly admitted symbols, ahead of the first L1 tick. Fundamentals runs on a
background thread -- ``fetch_fundamentals_batch`` is synchronous network I/O
per symbol and must never block the asyncio loop that also serves HTTP/WS
(the same loop ``scanner_hydrate._hydrate_pending`` runs on). The stored
daily bars are read on a worker thread for the same reason (D-018).
"""
from __future__ import annotations

import asyncio
import logging
import threading

from ibkr import scanner_session as _ss

logger = logging.getLogger(__name__)


async def on_large_cap_roster_commit(table: str, rows: list[dict]) -> None:
    if table != _ss.TABLE_LARGE_CAP:
        return
    symbols = [r.get("symbol") for r in rows if r.get("symbol")]
    if not symbols:
        return
    threading.Thread(
        target=_warm_fundamentals, args=(symbols,), daemon=True,
        name="large_cap_fundamentals_warm",
    ).start()
    import large_cap_metrics as _metrics

    for sym in await asyncio.to_thread(_short_of_daily_bars, symbols):
        try:
            _metrics.schedule_daily_fill(sym)
        except Exception:
            logger.debug(
                "large_cap_hooks: schedule_daily_fill failed for %s", sym, exc_info=True,
            )


def _short_of_daily_bars(symbols: list[str]) -> list[str]:
    """The symbols whose stored 1Day series is incomplete. A complete one does
    not spend an IB historical token re-requesting daily bars that do not change
    intraday (large_cap_metrics.schedule_daily_fill's session guard covers the
    incomplete-but-already-tried case)."""
    import bars_store
    from constants import LARGE_CAP_DAILY_BARS_LOOKBACK

    out: list[str] = []
    for sym in symbols:
        try:
            stored = bars_store.read(sym, "1Day", LARGE_CAP_DAILY_BARS_LOOKBACK + 1)
        except Exception:
            logger.debug("large_cap_hooks: stored daily bars unread for %s", sym, exc_info=True)
            continue
        if len((stored or {}).get("bars") or []) < LARGE_CAP_DAILY_BARS_LOOKBACK + 1:
            out.append(sym)
    return out


def _warm_fundamentals(symbols: list[str]) -> None:
    try:
        from fundamentals import fetch_fundamentals_batch

        fetch_fundamentals_batch(symbols)
    except Exception:
        logger.exception("large_cap_hooks: fundamentals warm failed")
