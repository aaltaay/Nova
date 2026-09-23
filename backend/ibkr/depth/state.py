"""Shared depth subscription state and viewer refcount."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from constants import IBKR_DEPTH_RELEASE_GRACE_SEC
from perf.counters import incr as _count_drop

logger = logging.getLogger(__name__)

IBKR_DEPTH_QUEUE_MAXSIZE = 100

_subscriptions: dict[str, dict] = {}
# Fan-out: one queue per *viewer*, not one shared queue per symbol. Two
# viewers of the same symbol (StrictMode double-mount, or a genuine second
# Trader tab on the same ticker) must each see every book update -- a single
# shared queue makes them competing consumers instead, so whichever
# socket's handler task keeps winning the race silently starves the other
# (same defect class as tape_stream.py, fixed there first -- PROBLEM_LOG
# 2026-08-25).
_viewer_queues: dict[str, list[asyncio.Queue]] = {}
_tickers: dict[str, Any] = {}
_contracts: dict[str, Any] = {}

# Serializes subscribe_async so concurrent DepthLadder / StrictMode WS opens
# cannot all pass the "not in _subscriptions" check, race through
# qualifyContractsAsync, and fire multiple reqMktDepth for the same symbol.
_subscribe_lock: asyncio.Lock | None = None

# The exact updateEvent listener currently wired for each symbol's ticker.
_update_handlers: dict[str, Any] = {}

# Counts live depth WebSocket viewers per symbol (DepthLadder can be open in
# more than one place at once). Only the LAST viewer closing should release.
_ws_viewers: dict[str, int] = {}

# Tracks which `ib` connections already have the depth-rejection error hook.
_error_hooked_ib_ids: set[int] = set()

# Symbols whose L1 fallback reuses ibkr.ticks' shared reqMktData stream
# instead of opening a second one — see ibkr/depth/subscribe.py. unsubscribe()
# must NOT cancelMktData for these; ticks.py owns cancellation via refcounting.
_shared_l1: set[str] = set()

_Stock = None


def reset_all() -> None:
    """Clear all depth state — called on facade reload for test isolation."""
    global _subscribe_lock, _Stock
    _subscriptions.clear()
    _viewer_queues.clear()
    _tickers.clear()
    _contracts.clear()
    _update_handlers.clear()
    _ws_viewers.clear()
    _error_hooked_ib_ids.clear()
    _shared_l1.clear()
    _subscribe_lock = None
    _Stock = None


def mark_shared_l1(symbol: str) -> None:
    _shared_l1.add(symbol)


def is_shared_l1(symbol: str) -> bool:
    return symbol in _shared_l1


def get_subscribe_lock() -> asyncio.Lock:
    global _subscribe_lock
    if _subscribe_lock is None:
        _subscribe_lock = asyncio.Lock()
    return _subscribe_lock


def load_ib_types() -> bool:
    global _Stock
    try:
        from ib_async import Stock
        _Stock = Stock
        return True
    except ImportError:
        return False


def subscribed_symbols() -> list[str]:
    return list(_subscriptions.keys())


def current_book(symbol: str) -> dict | None:
    return _subscriptions.get(symbol)


def is_subscribed(symbol: str) -> bool:
    """Is there an active IB depth/L1-fallback subscription for this symbol."""
    return symbol in _subscriptions


def is_live(symbol: str) -> bool:
    """A real IBKR line (depth, or the shared L1 fallback), not a Sim replay slot.

    On a Sim desk ``subscribe_async`` reserves a slot and serves the replayed
    book, so ``is_subscribed`` alone cannot tell Session Record whether live
    books are flowing.
    """
    return symbol in _contracts or is_shared_l1(symbol)


def ws_viewer_opened(symbol: str) -> None:
    """Record that another WS client is now watching this symbol's book."""
    _ws_viewers[symbol] = _ws_viewers.get(symbol, 0) + 1


def ws_viewer_closed(symbol: str) -> bool:
    """Record a WS client leaving. Returns True when it was the last viewer."""
    remaining = _ws_viewers.get(symbol, 0) - 1
    if remaining <= 0:
        _ws_viewers.pop(symbol, None)
        return True
    _ws_viewers[symbol] = remaining
    return False


def viewer_count(symbol: str) -> int:
    return _ws_viewers.get(symbol, 0)


def _release_grace_sec() -> float:
    """Read grace from facade so tests can monkeypatch ibkr.depth.IBKR_DEPTH_RELEASE_GRACE_SEC."""
    import ibkr.depth as facade
    return float(getattr(facade, "IBKR_DEPTH_RELEASE_GRACE_SEC", IBKR_DEPTH_RELEASE_GRACE_SEC))


async def release_when_idle(symbol: str) -> bool:
    """Wait a short grace window, then report whether the line is still idle."""
    await asyncio.sleep(_release_grace_sec())
    return viewer_count(symbol) <= 0


def _broadcast(symbol: str, payload: dict) -> None:
    for q in list(_viewer_queues.get(symbol, ())):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            _count_drop("depth.viewer_dropped")
            try:
                q.get_nowait()
                q.put_nowait(payload)
            except asyncio.QueueEmpty:
                logger.debug("IBKR depth: queue empty after full for %s", symbol)
            except asyncio.QueueFull:
                logger.warning("IBKR depth: queue still full for %s after drop", symbol)


def push_book(symbol: str, book: dict) -> None:
    """Broadcast a book snapshot to every viewer currently watching this symbol."""
    try:
        from sensors.rings import observe_book

        observe_book(symbol, book)
    except Exception:
        logger.debug("IBKR depth: sensor ring skip for %s", symbol, exc_info=True)
    _broadcast(symbol, book)


def push_error(symbol: str, message: str, *, evicted: bool = False) -> None:
    """Broadcast an error to every viewer currently watching this symbol.

    Used when a line is torn down out from under a still-open viewer so
    its WS route can close and the frontend's own backoff reconnects it
    instead of sitting silently on a dead line -- same pattern as
    tape_stream's ``released`` notice (PROBLEM_LOG 2026-08-25). A 4th
    live symbol is refused, not force-evicted (D-027).
    """
    _broadcast(
        symbol,
        {"type": "error", "symbol": symbol, "message": message, "evicted": evicted},
    )


def reserve_slot(symbol: str) -> None:
    _subscriptions[symbol] = {"bids": [], "asks": [], "l1_fallback": False}


def drop_slot(symbol: str) -> None:
    _subscriptions.pop(symbol, None)


def open_viewer_queue(symbol: str) -> asyncio.Queue:
    """Register a new viewer's own queue so it gets every broadcast book update.

    Each caller (each WS connection) must hold exactly one queue and pass
    it to ``stream()``; release it via ``close_viewer_queue`` in a
    ``finally`` block regardless of how the connection ends.
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=IBKR_DEPTH_QUEUE_MAXSIZE)
    _viewer_queues.setdefault(symbol, []).append(q)
    return q


def close_viewer_queue(symbol: str, q: asyncio.Queue) -> None:
    queues = _viewer_queues.get(symbol)
    if not queues:
        return
    try:
        queues.remove(q)
    except ValueError:
        pass
    if not queues:
        _viewer_queues.pop(symbol, None)


def pop_contract(symbol: str) -> Any | None:
    return _contracts.pop(symbol, None)


def clear_symbol(symbol: str) -> None:
    _tickers.pop(symbol, None)
    _shared_l1.discard(symbol)
    drop_slot(symbol)
