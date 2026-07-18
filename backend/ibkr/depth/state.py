"""Shared depth subscription state and viewer refcount."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from constants import IBKR_DEPTH_RELEASE_GRACE_SEC

logger = logging.getLogger(__name__)

_subscriptions: dict[str, dict] = {}
_queues: dict[str, asyncio.Queue] = {}
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
    _queues.clear()
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


def has_queue(symbol: str) -> bool:
    return symbol in _queues


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


def push_book(symbol: str, book: dict) -> None:
    """Enqueue a book snapshot for stream() consumers."""
    q = _queues.get(symbol)
    if q is None:
        return
    try:
        q.put_nowait(book)
    except asyncio.QueueFull:
        try:
            q.get_nowait()
            q.put_nowait(book)
        except asyncio.QueueEmpty:
            logger.debug("IBKR depth: queue empty after full for %s", symbol)
        except asyncio.QueueFull:
            logger.warning("IBKR depth: queue still full for %s after drop", symbol)


def reserve_slot(symbol: str) -> None:
    _subscriptions[symbol] = {"bids": [], "asks": [], "l1_fallback": False}
    _queues[symbol] = asyncio.Queue(maxsize=100)


def drop_slot(symbol: str) -> None:
    _subscriptions.pop(symbol, None)
    _queues.pop(symbol, None)


def pop_contract(symbol: str) -> Any | None:
    return _contracts.pop(symbol, None)


def clear_symbol(symbol: str) -> None:
    _tickers.pop(symbol, None)
    _shared_l1.discard(symbol)
    drop_slot(symbol)
