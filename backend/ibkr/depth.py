"""
IBKR Level 2 depth subscription manager.

Hard cap: IBKR_MAX_DEPTH_SYMBOLS concurrent depth streams (matches the
plan's 3-symbol simultaneous limit).

If depth entitlement is not yet active (e.g. Non-Professional status
still processing), falls back to Level 1 top-of-book so the UI still
works without errors.

State (module-level, this module owns it):
  _subscriptions  -- {symbol: {"bids": [...], "asks": [...], "l1_fallback": bool}}
  _queues         -- {symbol: asyncio.Queue} for WebSocket push
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from constants import IBKR_MAX_DEPTH_SYMBOLS
from ibkr import client as _client

logger = logging.getLogger(__name__)

_subscriptions: dict[str, dict] = {}
_queues: dict[str, asyncio.Queue] = {}

# ib_async contract types (imported lazily to avoid hard ImportError)
_Contract = None
_Stock = None


def _load_ib_types() -> bool:
    global _Contract, _Stock
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


def _on_update_book(ticker: Any, symbol: str) -> None:
    """ib_async ticker event handler — normalizes to {bids, asks}."""
    bids = [{"price": d.price, "size": d.size, "side": "bid"} for d in ticker.domBids]
    asks = [{"price": d.price, "size": d.size, "side": "ask"} for d in ticker.domAsks]
    book = {"bids": bids[:10], "asks": asks[:10], "l1_fallback": False}
    _subscriptions[symbol] = book
    q = _queues.get(symbol)
    if q:
        q.put_nowait(book)


def _on_update_ticker(ticker: Any, symbol: str) -> None:
    """L1 top-of-book fallback when depth entitlement is unavailable."""
    book = {
        "bids": [{"price": ticker.bid, "size": ticker.bidSize, "side": "bid"}] if ticker.bid else [],
        "asks": [{"price": ticker.ask, "size": ticker.askSize, "side": "ask"}] if ticker.ask else [],
        "l1_fallback": True,
    }
    _subscriptions[symbol] = book
    q = _queues.get(symbol)
    if q:
        q.put_nowait(book)


def subscribe(symbol: str) -> dict:
    """
    Subscribe to Level 2 depth for symbol.
    Returns {"ok": bool, "error": str|None, "symbols": [...]}.
    """
    if not _client.is_connected():
        return {"ok": False, "error": "IBKR not connected", "symbols": subscribed_symbols()}

    if symbol in _subscriptions:
        return {"ok": True, "error": None, "symbols": subscribed_symbols()}

    if len(_subscriptions) >= IBKR_MAX_DEPTH_SYMBOLS:
        return {
            "ok": False,
            "error": f"Symbol cap reached ({IBKR_MAX_DEPTH_SYMBOLS} max simultaneous depth streams)",
            "symbols": subscribed_symbols(),
        }

    if not _load_ib_types():
        return {"ok": False, "error": "ib_async not installed", "symbols": subscribed_symbols()}

    ib = _client.get_ib()
    if ib is None:
        return {"ok": False, "error": "IBKR not connected", "symbols": subscribed_symbols()}

    contract = _Stock(symbol, "SMART", "USD")
    _subscriptions[symbol] = {"bids": [], "asks": [], "l1_fallback": False}
    _queues[symbol] = asyncio.Queue(maxsize=100)

    try:
        ticker = ib.reqMktDepth(contract, numRows=10)
        ticker.updateEvent += lambda t: _on_update_book(t, symbol)
        logger.info("IBKR: subscribed depth for %s", symbol)
    except Exception as exc:
        logger.warning("IBKR: depth unavailable for %s (%s), falling back to L1", symbol, exc)
        try:
            ticker = ib.reqMktData(contract, "", False, False)
            ticker.updateEvent += lambda t: _on_update_ticker(t, symbol)
            _subscriptions[symbol]["l1_fallback"] = True
        except Exception as exc2:
            del _subscriptions[symbol]
            del _queues[symbol]
            logger.error("IBKR: L1 fallback also failed for %s: %s", symbol, exc2)
            return {"ok": False, "error": str(exc2), "symbols": subscribed_symbols()}

    return {"ok": True, "error": None, "symbols": subscribed_symbols()}


def unsubscribe(symbol: str) -> None:
    ib = _client.get_ib()
    _subscriptions.pop(symbol, None)
    _queues.pop(symbol, None)
    if ib:
        try:
            from ib_async import Stock
            ib.cancelMktDepth(_Stock(symbol, "SMART", "USD"))
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
            yield None  # heartbeat — caller sends ping
