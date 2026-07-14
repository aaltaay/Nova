"""
IBKR Level 2 depth subscription manager.

Hard cap: IBKR_MAX_DEPTH_SYMBOLS concurrent depth streams.

Contracts are qualified (conId) before depth/L1 requests — required by ib_async.
If depth entitlement is unavailable, falls back to L1 top-of-book.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from constants import (
    IBKR_DEPTH_NUM_ROWS,
    IBKR_DEPTH_RELEASE_GRACE_SEC,
    IBKR_DEPTH_SMART,
    IBKR_ERROR_DEPTH_NOT_SUPPORTED,
    IBKR_MAX_DEPTH_SYMBOLS,
)
from ibkr import client as _client

logger = logging.getLogger(__name__)

_subscriptions: dict[str, dict] = {}
_queues: dict[str, asyncio.Queue] = {}
_tickers: dict[str, Any] = {}
_contracts: dict[str, Any] = {}

# Serializes subscribe_async so concurrent DepthLadder / StrictMode WS opens
# cannot all pass the "not in _subscriptions" check, race through
# qualifyContractsAsync, and fire multiple reqMktDepth for the same symbol
# (burns the 3-slot IBKR cap and leaves Level 2 stuck on Reconnecting).
_subscribe_lock: asyncio.Lock | None = None


def _get_subscribe_lock() -> asyncio.Lock:
    global _subscribe_lock
    if _subscribe_lock is None:
        _subscribe_lock = asyncio.Lock()
    return _subscribe_lock

# The exact updateEvent listener currently wired for each symbol's ticker, so
# it can be precisely disconnected before wiring a new one. ib_async caches
# Ticker objects per contract hash, so reqMktData(contract) after
# reqMktDepth(contract) on the SAME contract returns the SAME Ticker
# instance — attaching a second listener without removing the first leaves
# both firing on every real tick, interleaving a stale empty depth-book
# message with the real L1 book forever (see PROBLEM_LOG 2026-07-13,
# "Level 2 depth ladder flickers between empty and real book after L1
# fallback").
_update_handlers: dict[str, Any] = {}


def _detach_update_handler(symbol: str) -> None:
    ticker = _tickers.get(symbol)
    handler = _update_handlers.pop(symbol, None)
    if ticker is not None and handler is not None:
        try:
            ticker.updateEvent -= handler
        except Exception:
            pass


def _attach_update_handler(symbol: str, ticker: Any, handler: Any) -> None:
    _detach_update_handler(symbol)
    ticker.updateEvent += handler
    _tickers[symbol] = ticker
    _update_handlers[symbol] = handler

# Counts live depth WebSocket viewers per symbol (DepthLadder can be open in
# more than one place at once — SidePanel + TradingTab + TickerDetailPage all
# use the same /ws/ibkr/depth/{symbol} route). Only the LAST viewer closing
# should release the line, otherwise the small IBKR_MAX_DEPTH_SYMBOLS budget
# gets burned by clicking through a few rows in the scanner (see PROBLEM_LOG
# 2026-07-13, "Level 2 not visible in scanner side panel").
_ws_viewers: dict[str, int] = {}

# Tracks which `ib` connections already have the depth-rejection error hook
# wired (keyed by id() since a fresh IB() is created on every reconnect).
_error_hooked_ib_ids: set[int] = set()

_Stock = None


def _load_ib_types() -> bool:
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


def should_send_current_book(book: dict | None) -> bool:
    """A freshly-opened WS viewer only gets the *next* tick from stream()
    otherwise — for an illiquid after-hours symbol that can be minutes away
    or never, leaving the DepthLadder stuck on "Waiting for book data" even
    though the line is already subscribed. Skip the placeholder
    pre-first-tick state ({bids: [], asks: [], l1_fallback: False}) so a
    brand new subscription still shows "Connecting…" instead of a
    momentarily-empty ladder."""
    if book is None:
        return False
    return bool(book["bids"] or book["asks"] or book["l1_fallback"])


def _on_update_book(ticker: Any, symbol: str) -> None:
    bids = [
        {
            "price": float(d.price),
            "size": float(d.size),
            "side": "bid",
            "mm": (getattr(d, "marketMaker", None) or "") or "",
        }
        for d in (ticker.domBids or [])
    ]
    asks = [
        {
            "price": float(d.price),
            "size": float(d.size),
            "side": "ask",
            "mm": (getattr(d, "marketMaker", None) or "") or "",
        }
        for d in (ticker.domAsks or [])
    ]
    book = {"bids": bids[:10], "asks": asks[:10], "l1_fallback": False}
    _subscriptions[symbol] = book
    q = _queues.get(symbol)
    if q:
        try:
            q.put_nowait(book)
        except asyncio.QueueFull:
            pass


def _on_update_ticker(ticker: Any, symbol: str) -> None:
    book = {
        "bids": (
            [{"price": float(ticker.bid), "size": float(ticker.bidSize or 0), "side": "bid", "mm": "L1"}]
            if ticker.bid
            else []
        ),
        "asks": (
            [{"price": float(ticker.ask), "size": float(ticker.askSize or 0), "side": "ask", "mm": "L1"}]
            if ticker.ask
            else []
        ),
        "l1_fallback": True,
    }
    _subscriptions[symbol] = book
    q = _queues.get(symbol)
    if q:
        try:
            q.put_nowait(book)
        except asyncio.QueueFull:
            pass


def _install_error_hook(ib: Any) -> None:
    """Wire a one-time errorEvent listener so an async depth rejection (see
    IBKR_ERROR_DEPTH_NOT_SUPPORTED) degrades to L1 instead of leaving the
    DepthLadder stuck on "Waiting for book data" forever."""
    if id(ib) in _error_hooked_ib_ids:
        return
    ib.errorEvent += _on_ib_error
    _error_hooked_ib_ids.add(id(ib))


def _on_ib_error(reqId: int, errorCode: int, errorString: str, contract: Any) -> None:
    if errorCode != IBKR_ERROR_DEPTH_NOT_SUPPORTED or contract is None:
        return
    con_id = getattr(contract, "conId", None)
    if con_id is None:
        return
    for sym, c in list(_contracts.items()):
        if getattr(c, "conId", None) == con_id and not _subscriptions.get(sym, {}).get("l1_fallback"):
            logger.warning(
                "IBKR: depth rejected server-side for %s (%s: %s) — falling back to L1",
                sym, errorCode, errorString,
            )
            _fallback_to_l1(sym, c)
            return


def _fallback_to_l1(symbol: str, contract: Any) -> None:
    ib = _client.get_ib()
    if ib is None or symbol not in _subscriptions:
        return
    try:
        ib.cancelMktDepth(contract, isSmartDepth=IBKR_DEPTH_SMART)
    except Exception:
        pass
    try:
        ticker = ib.reqMktData(contract, "", False, False)
        _attach_update_handler(symbol, ticker, lambda t: _on_update_ticker(t, symbol))
        book = {"bids": [], "asks": [], "l1_fallback": True}
        _subscriptions[symbol] = book
        # Push the fallback itself onto the queue — an illiquid after-hours
        # symbol may not print another tick for minutes (or the rest of the
        # session), and any WS viewer already connected only learns about
        # state changes via the queue, not by re-reading current_book(). See
        # PROBLEM_LOG 2026-07-13.
        q = _queues.get(symbol)
        if q:
            try:
                q.put_nowait(book)
            except asyncio.QueueFull:
                pass
        logger.info("IBKR: subscribed L1 fallback for %s (conId=%s)", symbol, contract.conId)
    except Exception as exc:
        logger.error("IBKR: L1 fallback after depth rejection failed for %s: %s", symbol, exc)


async def subscribe_async(symbol: str) -> dict:
    """
    Qualify + subscribe to Level 2 (or L1 fallback).
    Safe under FastAPI's running event loop.
    """
    if not _client.is_connected():
        return {"ok": False, "error": "IBKR not connected", "symbols": subscribed_symbols()}

    async with _get_subscribe_lock():
        if symbol in _subscriptions:
            return {"ok": True, "error": None, "symbols": subscribed_symbols()}

        if len(_subscriptions) >= IBKR_MAX_DEPTH_SYMBOLS:
            await _evict_for_capacity(symbol)
        if len(_subscriptions) >= IBKR_MAX_DEPTH_SYMBOLS:
            return {
                "ok": False,
                "error": (
                    f"Symbol cap reached ({IBKR_MAX_DEPTH_SYMBOLS} max simultaneous "
                    "depth streams)"
                ),
                "symbols": subscribed_symbols(),
            }

        if not _load_ib_types():
            return {
                "ok": False,
                "error": "ib_async not installed",
                "symbols": subscribed_symbols(),
            }

        ib = _client.get_ib()
        if ib is None:
            return {
                "ok": False,
                "error": "IBKR not connected",
                "symbols": subscribed_symbols(),
            }

        _install_error_hook(ib)

        # Reserve the slot BEFORE qualify so concurrent callers for the same
        # symbol see it as already subscribed and do not fire a second
        # reqMktDepth.
        _subscriptions[symbol] = {"bids": [], "asks": [], "l1_fallback": False}
        _queues[symbol] = asyncio.Queue(maxsize=100)

        contract = _Stock(symbol, "SMART", "USD")
        try:
            qualified = await ib.qualifyContractsAsync(contract)
            if not qualified:
                _subscriptions.pop(symbol, None)
                _queues.pop(symbol, None)
                return {
                    "ok": False,
                    "error": f"Could not qualify contract for {symbol}",
                    "symbols": subscribed_symbols(),
                }
            contract = qualified[0]
        except Exception as exc:
            _subscriptions.pop(symbol, None)
            _queues.pop(symbol, None)
            logger.error("IBKR: qualify failed for %s: %s", symbol, exc)
            return {
                "ok": False,
                "error": f"Qualify failed: {exc}",
                "symbols": subscribed_symbols(),
            }

        _contracts[symbol] = contract

        try:
            # SMART contracts need isSmartDepth=True; otherwise Gateway returns
            # 10092 for every symbol even when NASDAQ TotalView is active.
            ticker = ib.reqMktDepth(
                contract,
                numRows=IBKR_DEPTH_NUM_ROWS,
                isSmartDepth=IBKR_DEPTH_SMART,
            )
            _attach_update_handler(symbol, ticker, lambda t: _on_update_book(t, symbol))
            logger.info(
                "IBKR: subscribed depth for %s (conId=%s, smart=%s, rows=%s)",
                symbol, contract.conId, IBKR_DEPTH_SMART, IBKR_DEPTH_NUM_ROWS,
            )
        except Exception as exc:
            logger.warning(
                "IBKR: depth unavailable for %s (%s), falling back to L1", symbol, exc,
            )
            try:
                ticker = ib.reqMktData(contract, "", False, False)
                _attach_update_handler(symbol, ticker, lambda t: _on_update_ticker(t, symbol))
                _subscriptions[symbol]["l1_fallback"] = True
                logger.info(
                    "IBKR: subscribed L1 fallback for %s (conId=%s)",
                    symbol, contract.conId,
                )
            except Exception as exc2:
                unsubscribe(symbol)
                logger.error("IBKR: L1 fallback also failed for %s: %s", symbol, exc2)
                return {"ok": False, "error": str(exc2), "symbols": subscribed_symbols()}

        return {"ok": True, "error": None, "symbols": subscribed_symbols()}


async def _evict_for_capacity(incoming: str) -> None:
    """Free depth slot(s) so `incoming` can subscribe.

    Prefer symbols with zero live WS viewers. If every slot still looks
    "watched" (orphaned WebSocket viewer-count leak — see PROBLEM_LOG
    IBKR_MAX_DEPTH_SYMBOLS slots leak), force-evict another symbol and
    clear its leaked viewer count so the actively requested ticker can load
    instead of reconnect-looping on "Symbol cap reached".
    """
    while len(_subscriptions) >= IBKR_MAX_DEPTH_SYMBOLS:
        idle = [
            s for s in list(_subscriptions.keys())
            if s != incoming and viewer_count(s) <= 0
        ]
        if idle:
            victim = idle[0]
            logger.warning(
                "IBKR: evicting idle depth slot %s to free capacity for %s",
                victim, incoming,
            )
        else:
            others = [s for s in list(_subscriptions.keys()) if s != incoming]
            if not others:
                return
            victim = others[0]
            logger.warning(
                "IBKR: force-evicting depth slot %s (viewer_count=%s, possible leak) for %s",
                victim, viewer_count(victim), incoming,
            )
            _ws_viewers.pop(victim, None)
        unsubscribe(victim)
        try:
            from l2 import continuous as _l2_continuous
            await _l2_continuous.stop(victim)
        except Exception:
            logger.exception("IBKR: failed to stop continuous L2 for evicted %s", victim)

def subscribe(symbol: str) -> dict:
    """
    Sync entry — only safe when no event loop is running (tests).
    Prefer subscribe_async from FastAPI routes.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        return {
            "ok": False,
            "error": "Use async depth subscribe under a running event loop",
            "symbols": subscribed_symbols(),
        }
    return asyncio.run(subscribe_async(symbol))


def ws_viewer_opened(symbol: str) -> None:
    """Record that another WS client is now watching this symbol's book."""
    _ws_viewers[symbol] = _ws_viewers.get(symbol, 0) + 1


def ws_viewer_closed(symbol: str) -> bool:
    """Record a WS client leaving. Returns True when it was the last viewer
    (safe for the caller to release the depth line), False if others remain."""
    remaining = _ws_viewers.get(symbol, 0) - 1
    if remaining <= 0:
        _ws_viewers.pop(symbol, None)
        return True
    _ws_viewers[symbol] = remaining
    return False


def viewer_count(symbol: str) -> int:
    return _ws_viewers.get(symbol, 0)


def has_queue(symbol: str) -> bool:
    return symbol in _queues


async def release_when_idle(symbol: str) -> bool:
    """Wait a short grace window, then report whether the line is still idle.

    React StrictMode and DepthLadder reconnects close+open the WS within
    tens of milliseconds. Releasing IBKR depth immediately on the close half
    of that cycle forces a full re-subscribe on the open half — which is what
    makes the side panel flash "Connecting depth for SYMBOL…" after the book
    already rendered. Returns True when the caller should actually unsubscribe
    (still zero viewers after the grace). Returns False if a new viewer
    reattached in time.
    """
    await asyncio.sleep(IBKR_DEPTH_RELEASE_GRACE_SEC)
    return viewer_count(symbol) <= 0


def unsubscribe(symbol: str) -> None:
    ib = _client.get_ib()
    contract = _contracts.pop(symbol, None)
    _detach_update_handler(symbol)
    _tickers.pop(symbol, None)
    _subscriptions.pop(symbol, None)
    _queues.pop(symbol, None)
    if ib and contract is not None:
        try:
            ib.cancelMktDepth(contract, isSmartDepth=IBKR_DEPTH_SMART)
        except Exception:
            pass
        try:
            ib.cancelMktData(contract)
        except Exception:
            pass


async def stream(symbol: str):
    """AsyncGenerator yielding book snapshots for the given symbol."""
    q = _queues.get(symbol)
    if q is None:
        return
    while True:
        try:
            book = await asyncio.wait_for(q.get(), timeout=15)
            yield book
        except asyncio.TimeoutError:
            yield None
