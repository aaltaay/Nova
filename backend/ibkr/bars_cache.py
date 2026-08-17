"""TTL cache + single-flight for IBKR historical bars.

Freshness-bounded only: expired entries are never returned. Failures are not
cached and never fall back to last-good data (loud 503 stays loud).
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

from constants import (
    IBKR_BARS_CACHE_MAX_KEYS,
    IBKR_BARS_CACHE_TTL_DAILY_SEC,
    IBKR_BARS_CACHE_TTL_INTRADAY_SEC,
)
from metrics.op_metrics import record

logger = logging.getLogger(__name__)

_DAILY_TFS = frozenset({"1Day", "1Week", "1Month"})

_store_lock = threading.Lock()
# key -> (expires_at_monotonic, payload)
_entries: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
# Touched only on the IB event loop (single-flight). Task outlives caller cancel.
_inflight: dict[tuple[str, str], asyncio.Task] = {}

FetchFn = Callable[..., Awaitable[dict[str, Any]]]


def _cache_key(symbol: str, timeframe: str) -> tuple[str, str]:
    return (symbol.upper(), timeframe)


def _ttl_for(timeframe: str) -> float:
    if timeframe in _DAILY_TFS:
        return float(IBKR_BARS_CACHE_TTL_DAILY_SEC)
    return float(IBKR_BARS_CACHE_TTL_INTRADAY_SEC)


def _trim_payload(payload: dict[str, Any], limit: int) -> dict[str, Any]:
    bars = payload.get("bars") or []
    if limit < len(bars):
        bars = bars[-limit:]
    out = {
        "symbol": payload["symbol"],
        "timeframe": payload["timeframe"],
        "bars": list(bars),
        "source": payload.get("source", "ibkr"),
    }
    if "cache" in payload:
        out["cache"] = payload["cache"]
    return out


def get_cached(symbol: str, timeframe: str, limit: int) -> dict[str, Any] | None:
    """Return a still-fresh cached payload trimmed to ``limit``, or None."""
    key = _cache_key(symbol, timeframe)
    now = time.monotonic()
    with _store_lock:
        entry = _entries.get(key)
        if entry is None:
            return None
        expires_at, payload = entry
        if now >= expires_at:
            del _entries[key]
            return None
        bars = payload.get("bars") or []
        # Fewer bars than requested means we cannot satisfy from cache.
        if bars and limit > len(bars):
            return None
        out = _trim_payload(payload, limit)
        out["cache"] = "hit"
        return out


def put_cached(payload: dict[str, Any]) -> None:
    """Store a successful IBKR payload. Errors must never call this."""
    if "bars" not in payload:
        return
    symbol = str(payload.get("symbol") or "").upper()
    timeframe = str(payload.get("timeframe") or "")
    if not symbol or not timeframe:
        return
    key = _cache_key(symbol, timeframe)
    stored = {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": list(payload.get("bars") or []),
        "source": payload.get("source", "ibkr"),
    }
    expires_at = time.monotonic() + _ttl_for(timeframe)
    with _store_lock:
        _entries[key] = (expires_at, stored)
        _evict_locked()


def _evict_locked() -> None:
    """Caller holds ``_store_lock``. Drop expired, then oldest by expiry."""
    now = time.monotonic()
    expired = [k for k, (exp, _) in _entries.items() if now >= exp]
    for k in expired:
        del _entries[k]
    while len(_entries) > IBKR_BARS_CACHE_MAX_KEYS:
        oldest_key = min(_entries.items(), key=lambda item: item[1][0])[0]
        del _entries[oldest_key]


def clear_for_tests() -> None:
    """Reset cache + inflight map (unit tests only)."""
    with _store_lock:
        _entries.clear()
    leftover = list(_inflight.values())
    _inflight.clear()
    for task in leftover:
        if not task.done():
            task.cancel()


def _drop_inflight(key: tuple[str, str], task: asyncio.Task) -> None:
    if _inflight.get(key) is task:
        del _inflight[key]
    if task.cancelled():
        return
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc is not None:
        logger.debug("ibkr.bars_cache fetch ended with %s", type(exc).__name__)


async def get_or_fetch(
    symbol: str,
    timeframe: str,
    limit: int,
    *,
    interactive: bool,
    fetch_fn: FetchFn,
) -> dict[str, Any]:
    """Return cached bars or coalesce concurrent fetches for the same key.

    The IBKR fetch runs in a detached task: a timed-out HTTP / ``run_coro``
    cancel must not kill a historical another pane (or a retry) still needs.
    ``reqHistoricalDataAsync`` keeps its own timeout as the backstop.
    """
    hit = get_cached(symbol, timeframe, limit)
    if hit is not None:
        record("ibkr.bars_cache.hit", 0)
        return hit

    key = _cache_key(symbol, timeframe)
    existing = _inflight.get(key)
    if existing is not None:
        record("ibkr.bars_cache.coalesce", 0)
        result = await asyncio.shield(existing)
        return _trim_payload({**result, "cache": "coalesce"}, limit)

    started = time.perf_counter_ns()

    async def _run() -> dict[str, Any]:
        result = await fetch_fn(
            symbol, timeframe, limit, interactive=interactive,
        )
        put_cached(result)
        record("ibkr.bars_cache.miss", time.perf_counter_ns() - started)
        return result

    task = asyncio.create_task(_run())
    _inflight[key] = task
    task.add_done_callback(lambda t: _drop_inflight(key, t))

    result = await asyncio.shield(task)
    return _trim_payload({**result, "cache": "miss"}, limit)
