"""IBKR-sourced price repricing between full discovery/movers scans.

Extracted out of main.py (see PROBLEM_LOG 2026-07-14, "Quote panel frozen,
only Level 2 stayed live" and "Detail panel updates every ~30s instead of
every tick"). Two independent concerns live here, on purpose:

- ``reprice_detail_symbols`` / ``detail_reprice_loop``: a tiny, fast
  snapshot_quotes() call for the 0-2 symbols with an open ticker-detail
  WebSocket. This runs on its own independent timer task
  (``detail_reprice_loop``), started separately in main.py's lifespan —
  NOT nested inside the main scan loop's sleep. The main scan loop's
  per-iteration work (``_run_gainers_update`` doing a full IBKR market
  scan + snapshot for up to 100 symbols) routinely takes well over
  IBKR_REPRICE_INTERVAL_SEC by itself, which silently starved detail
  repricing when it was called from inside that loop's sleep helper.

- ``reprice_table_caches``: re-snapshots every symbol already in the
  gapper/gainer/loser caches. This batch can be 100+ symbols and is NOT
  cheap — callers must not depend on it for low-latency updates. It stays
  tied to the main scan loop's cadence since it's a best-effort refresh
  between full scans, not a per-tick guarantee.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from constants import IBKR_REPRICE_INTERVAL_SEC
from ibkr import discovery as _ibkr_discovery

logger = logging.getLogger(__name__)

RunIbkrFn = Callable[[Awaitable], object]
BroadcastFn = Callable[..., Awaitable[None]]
FindCacheRowFn = Callable[[str], Optional[dict]]
GetDetailSymbolsFn = Callable[[], list[str]]


def reprice_detail_symbols(
    detail_symbols: list[str],
    run_ibkr: RunIbkrFn,
    broadcast_trade_update: BroadcastFn,
    find_cache_row: FindCacheRowFn,
) -> None:
    """Reprice only the symbols with an open ticker-detail WS (usually 0-2)."""
    if not detail_symbols:
        return
    quotes = run_ibkr(_ibkr_discovery.snapshot_quotes(detail_symbols))
    for sym in detail_symbols:
        row = find_cache_row(sym)
        q = quotes.get(sym) if quotes else None
        price = (q or {}).get("price")
        volume = (q or {}).get("volume")
        prev_close = (q or {}).get("prev_close")
        if row:
            price = price if price is not None else (row.get("current_price") or row.get("price"))
            volume = volume if volume is not None else row.get("volume")
            prev_close = (row.get("previous_close") or row.get("prev_close")) or prev_close
        if price is None:
            continue
        run_ibkr(broadcast_trade_update(
            sym, price, None, datetime.now(timezone.utc).isoformat(), volume, prev_close,
        ))


def reprice_table_caches(
    gapper_cache: list[dict],
    gainer_cache: list[dict],
    loser_cache: list[dict],
    run_ibkr: RunIbkrFn,
) -> Optional[tuple[list[dict], list[dict], list[dict], float]]:
    """Re-snapshot every symbol in the scanner table caches.

    Returns the (possibly repriced) caches plus the timestamp, or None if
    there was nothing to reprice / the IBKR call came back empty — callers
    should leave their caches untouched in that case.
    """
    symbols = list({r["symbol"] for r in gapper_cache + gainer_cache + loser_cache})
    if not symbols:
        return None
    quotes = run_ibkr(_ibkr_discovery.snapshot_quotes(symbols))
    if not quotes:
        return None

    now = time.time()
    if gapper_cache:
        gapper_cache = [
            _ibkr_discovery.reprice_gapper_row(g, quotes[g["symbol"]]) if g["symbol"] in quotes else g
            for g in gapper_cache
        ]
    if gainer_cache:
        gainer_cache = [
            _ibkr_discovery.reprice_mover_row(m, quotes[m["symbol"]]) if m["symbol"] in quotes else m
            for m in gainer_cache
        ]
    if loser_cache:
        loser_cache = [
            _ibkr_discovery.reprice_mover_row(m, quotes[m["symbol"]]) if m["symbol"] in quotes else m
            for m in loser_cache
        ]
    return gapper_cache, gainer_cache, loser_cache, now


async def detail_reprice_loop(
    get_detail_symbols: GetDetailSymbolsFn,
    run_ibkr: RunIbkrFn,
    broadcast_trade_update: BroadcastFn,
    find_cache_row: FindCacheRowFn,
) -> None:
    """Independent fast timer for the ticker-detail panel.

    Runs every IBKR_REPRICE_INTERVAL_SEC forever, completely decoupled from
    the (much slower) main scan loop, so a watched ticker detail panel never
    waits on a full gapper/gainer/loser discovery or movers scan to finish.
    """
    loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(IBKR_REPRICE_INTERVAL_SEC)
        try:
            detail_symbols = get_detail_symbols()
            await loop.run_in_executor(
                None,
                reprice_detail_symbols,
                detail_symbols,
                run_ibkr,
                broadcast_trade_update,
                find_cache_row,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Detail reprice tick failed")
