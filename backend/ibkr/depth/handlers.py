"""IBKR depth tick handlers, error hook, and L1 fallback."""
from __future__ import annotations

import logging
from typing import Any

from constants import IBKR_DEPTH_SMART, IBKR_ERROR_DEPTH_NOT_SUPPORTED
from ibkr import client as _client
from ibkr.depth import state

logger = logging.getLogger(__name__)


def detach_update_handler(symbol: str) -> None:
    ticker = state._tickers.get(symbol)
    handler = state._update_handlers.pop(symbol, None)
    if ticker is not None and handler is not None:
        try:
            ticker.updateEvent -= handler
        except (AttributeError, ValueError, TypeError) as exc:
            logger.debug(
                "IBKR: could not detach depth update handler for %s: %s",
                symbol, exc,
            )


def attach_update_handler(symbol: str, ticker: Any, handler: Any) -> None:
    detach_update_handler(symbol)
    ticker.updateEvent += handler
    state._tickers[symbol] = ticker
    state._update_handlers[symbol] = handler


def on_update_book(ticker: Any, symbol: str) -> None:
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
    state._subscriptions[symbol] = book
    state.push_book(symbol, book)


def on_update_ticker(ticker: Any, symbol: str) -> None:
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
    state._subscriptions[symbol] = book
    state.push_book(symbol, book)


def install_error_hook(ib: Any) -> None:
    """Wire a one-time errorEvent listener for async depth rejection → L1."""
    if id(ib) in state._error_hooked_ib_ids:
        return
    ib.errorEvent += on_ib_error
    state._error_hooked_ib_ids.add(id(ib))


def on_ib_error(reqId: int, errorCode: int, errorString: str, contract: Any) -> None:
    if errorCode != IBKR_ERROR_DEPTH_NOT_SUPPORTED or contract is None:
        return
    con_id = getattr(contract, "conId", None)
    if con_id is None:
        return
    for sym, c in list(state._contracts.items()):
        if getattr(c, "conId", None) == con_id and not state._subscriptions.get(sym, {}).get("l1_fallback"):
            logger.warning(
                "IBKR: depth rejected server-side for %s (%s: %s) — falling back to L1",
                sym, errorCode, errorString,
            )
            fallback_to_l1(sym, c)
            return


def _cancel_depth(ib: Any, contract: Any, symbol: str) -> None:
    try:
        ib.cancelMktDepth(contract, isSmartDepth=IBKR_DEPTH_SMART)
    except Exception as exc:
        logger.debug(
            "IBKR: cancelMktDepth during cleanup for %s ignored: %s",
            symbol, exc,
        )


def fallback_to_l1(symbol: str, contract: Any) -> None:
    ib = _client.get_ib()
    if ib is None or symbol not in state._subscriptions:
        return
    _cancel_depth(ib, contract, symbol)
    try:
        from ibkr import ticks as _ticks

        shared_ticker = _ticks.get_ticker(symbol)
        reused = shared_ticker is not None
        if reused:
            ticker = shared_ticker
            state.mark_shared_l1(symbol)
        else:
            ticker = ib.reqMktData(contract, "", False, False)
        attach_update_handler(symbol, ticker, lambda t: on_update_ticker(t, symbol))
        book = {"bids": [], "asks": [], "l1_fallback": True}
        state._subscriptions[symbol] = book
        state.push_book(symbol, book)
        logger.info(
            "IBKR: subscribed L1 fallback for %s (conId=%s, reused_ticks_stream=%s)",
            symbol, contract.conId, reused,
        )
    except Exception as exc:
        logger.exception("IBKR: L1 fallback after depth rejection failed for %s: %s", symbol, exc)
