"""IBKR-sourced price repricing between full discovery/movers scans.

Extracted out of main.py (see PROBLEM_LOG 2026-07-14).

- ``detail_reprice_loop``: 0–2 open ticker-detail symbols (panel backstop).
- ``table_reprice_loop``: retired compatibility/test helper. App lifespan does
  not start it; active-table freshness is owned by scanner_l1 ``reqMktData``.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from constants import (
    IBKR_REPRICE_INTERVAL_SEC,
    IBKR_TABLE_REPRICE_CHUNK_SIZE,
    IBKR_TABLE_REPRICE_CHUNK_TIMEOUT_SEC,
    IBKR_TABLE_REPRICE_INTERVAL_SEC,
)
from ibkr import discovery as _ibkr_discovery

logger = logging.getLogger(__name__)

RunIbkrFn = Callable[[Awaitable], object]
BroadcastFn = Callable[..., Awaitable[None]]
ScheduleBroadcastFn = Callable[..., None]
FindCacheRowFn = Callable[[str], Optional[dict]]
GetDetailSymbolsFn = Callable[[], list[str]]
GetProviderFn = Callable[[], str]
RepriceCachesFn = Callable[[], Optional[dict[str, Any]]]
PushFn = Callable[[dict[str, Any]], Awaitable[None]]
GetSymbolsFn = Callable[[], list[str]]
IsStreamFreshFn = Callable[[str], bool]

_table_reprice_busy = False
_table_chunk_rotate = 0
_table_last_ok_ts: float | None = None
_table_busy_skips = 0
_table_timeouts = 0
_table_last_request_ms: float | None = None


def reprice_detail_symbols(
    detail_symbols: list[str],
    run_ibkr: RunIbkrFn,
    schedule_broadcast: ScheduleBroadcastFn,
    find_cache_row: FindCacheRowFn,
    is_stream_fresh: Optional[IsStreamFreshFn] = None,
) -> None:
    """Reprice only the symbols with an open ticker-detail WS (usually 0-2).

    ``schedule_broadcast`` must push the coroutine onto the FastAPI/main event
    loop (not through ``run_ibkr``) — broadcasting over the IB bridge contended
    with snapshot_quotes and made trade_update feel 10–14s apart.

    ``is_stream_fresh`` (optional): when a symbol already has a live
    ``reqMktData`` stream (``ibkr/ticks.py``) that ticked recently, this
    reqTickersAsync snapshot is redundant and only adds IBKR-request-queue
    contention with ``table_reprice_loop`` — skip both the snapshot and the
    broadcast for that symbol entirely (ticks.py already owns its broadcasts).
    Symbols with no fresh stream keep the exact prior snapshot-backstop
    behavior, unchanged.
    """
    if not detail_symbols:
        return
    backstop_symbols = (
        [s for s in detail_symbols if not is_stream_fresh(s)]
        if is_stream_fresh is not None
        else list(detail_symbols)
    )
    if not backstop_symbols:
        return
    # Injected run_ibkr must accept a single coro (tests); production bridge
    # defaults on_error="none" so failures are None, not [].
    quotes = run_ibkr(_ibkr_discovery.snapshot_quotes(backstop_symbols))
    if not isinstance(quotes, dict):
        return
    for sym in backstop_symbols:
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
        schedule_broadcast(
            sym, price, None, datetime.now(timezone.utc).isoformat(), volume, prev_close,
        )


def _patch_row(row: dict) -> dict:
    price = row.get("price")
    if price is None:
        price = row.get("current_price")
    return {
        "symbol": row["symbol"],
        "price": price,
        "change_pct": row.get("change_pct"),
        "change_abs": row.get("change_abs"),
        "volume": row.get("volume"),
        "gap_percent": row.get("gap_percent"),
    }


def apply_quote_patches(
    gapper_cache: list[dict],
    gainer_cache: list[dict],
    loser_cache: list[dict],
    quotes: dict[str, dict],
) -> Optional[tuple[list[dict], list[dict], list[dict], float, list[dict]]]:
    """Apply a quotes dict to caches; returns patched caches + ts + rows, or None."""
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
    by_sym: dict[str, dict] = {}
    for row in gapper_cache + gainer_cache + loser_cache:
        by_sym[row["symbol"]] = _patch_row(row)
    return gapper_cache, gainer_cache, loser_cache, now, list(by_sym.values())


def reprice_table_caches(
    gapper_cache: list[dict],
    gainer_cache: list[dict],
    loser_cache: list[dict],
    run_ibkr: RunIbkrFn,
) -> Optional[tuple[list[dict], list[dict], list[dict], float, list[dict]]]:
    """Sync path: snapshot via ``run_ibkr`` then apply (tests / legacy)."""
    symbols = list({r["symbol"] for r in gapper_cache + gainer_cache + loser_cache})
    if not symbols:
        return None
    quotes = run_ibkr(_ibkr_discovery.snapshot_quotes(symbols))
    if not isinstance(quotes, dict):
        return None
    return apply_quote_patches(gapper_cache, gainer_cache, loser_cache, quotes)


async def snapshot_table_quotes(
    symbols: list[str],
    *,
    timeout_sec: float = IBKR_TABLE_REPRICE_CHUNK_TIMEOUT_SEC,
) -> dict[str, dict]:
    """Await IBKR snapshots on the running event loop (no thread bridge)."""
    if not symbols:
        return {}
    result = await _ibkr_discovery.snapshot_quotes(symbols, timeout_sec=timeout_sec)
    return result if isinstance(result, dict) else {}


async def detail_reprice_loop(
    get_detail_symbols: GetDetailSymbolsFn,
    run_ibkr: RunIbkrFn,
    broadcast_trade_update: BroadcastFn,
    find_cache_row: FindCacheRowFn,
    is_stream_fresh: Optional[IsStreamFreshFn] = None,
) -> None:
    """Independent timer for the ticker-detail panel (volume/prev_close backstop).

    ``is_stream_fresh`` lets the caller skip this snapshot entirely for
    symbols already served by ``ibkr/ticks.py``'s streaming subscription —
    see ``reprice_detail_symbols`` for why.
    """
    loop = asyncio.get_running_loop()

    def schedule_broadcast(*args) -> None:
        asyncio.run_coroutine_threadsafe(broadcast_trade_update(*args), loop)

    while True:
        await asyncio.sleep(IBKR_REPRICE_INTERVAL_SEC)
        try:
            detail_symbols = get_detail_symbols()
            await loop.run_in_executor(
                None,
                reprice_detail_symbols,
                detail_symbols,
                run_ibkr,
                schedule_broadcast,
                find_cache_row,
                is_stream_fresh,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Detail reprice tick failed")


def pick_table_chunk(symbols: list[str], rotate: int, chunk_size: int) -> tuple[list[str], int]:
    """Rotate scanner UI symbols in progressive chunks (pure helper for tests)."""
    if not symbols:
        return [], rotate
    chunks = _ibkr_discovery.chunk_symbols(symbols, chunk_size)
    if not chunks:
        return [], rotate
    chunk = chunks[rotate % len(chunks)]
    return list(chunk), rotate + 1


async def table_reprice_loop(
    get_provider: GetProviderFn,
    get_symbols: GetSymbolsFn,
    apply_quotes: Callable[[dict[str, dict]], Optional[dict[str, Any]]],
    push: PushFn,
    get_active_batch: Optional[GetSymbolsFn] = None,
) -> None:
    """Scanner-table + HOD active-set snapshots in progressive chunks (IB event loop).

    One giant ``reqTickersAsync(~100)`` took 7–10s and painted the whole UI
    "stale". Instead: each 1Hz tick snapshots one fair batch of
    ``IBKR_TABLE_REPRICE_CHUNK_SIZE`` (hot active + age-fair tail, with leftover
    slots for scanner UI rotation) and pushes immediately.
    """
    global _table_reprice_busy, _table_chunk_rotate
    global _table_last_ok_ts, _table_busy_skips, _table_timeouts, _table_last_request_ms

    while True:
        await asyncio.sleep(IBKR_TABLE_REPRICE_INTERVAL_SEC)
        try:
            if get_provider() != "ibkr":
                continue
            if _table_reprice_busy:
                _table_busy_skips += 1
                await push({"type": "price_heartbeat", "ts": time.time(), "stale": True})
                continue
            scanner_symbols = get_symbols()
            scanner_chunk, _table_chunk_rotate = pick_table_chunk(
                scanner_symbols, _table_chunk_rotate, IBKR_TABLE_REPRICE_CHUNK_SIZE,
            )
            active_batch: list[str] = []
            if get_active_batch is not None:
                try:
                    active_batch = list(get_active_batch() or [])
                except Exception:
                    logger.exception("Active reprice batch failed")
                    active_batch = []
            if active_batch:
                from hod_momo_active import merge_with_scanner_chunk
                chunk = merge_with_scanner_chunk(
                    active_batch, scanner_chunk, chunk_size=IBKR_TABLE_REPRICE_CHUNK_SIZE,
                )
            else:
                chunk = scanner_chunk
            if not chunk:
                continue

            _table_reprice_busy = True
            t0 = time.perf_counter()
            try:
                quotes = await snapshot_table_quotes(chunk)
                _table_last_request_ms = (time.perf_counter() - t0) * 1000.0
                if not quotes:
                    _table_timeouts += 1
                    await push({"type": "price_heartbeat", "ts": time.time(), "stale": True})
                else:
                    result = apply_quotes(quotes)
                    if result is None:
                        await push({"type": "price_heartbeat", "ts": time.time(), "stale": True})
                    else:
                        _table_last_ok_ts = time.time()
                        await push(result)
            finally:
                _table_reprice_busy = False
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Table reprice tick failed")
            _table_reprice_busy = False
            try:
                await push({"type": "price_heartbeat", "ts": time.time(), "stale": True})
            except Exception:
                logger.exception("Table reprice stale heartbeat failed")
