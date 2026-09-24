"""IBKR depth tick handlers, error hook, and L1 fallback."""
from __future__ import annotations

import logging
from typing import Any

from constants import (
    IBKR_DEPTH_NUM_ROWS,
    IBKR_DEPTH_SMART,
    IBKR_ERROR_DEPTH_NOT_SUPPORTED,
    IBKR_ERROR_DEPTH_RESET,
)
from ibkr import client as _client
from ibkr.depth import state
from ibkr.depth.book import Level, sort_levels
from metrics.op_metrics import timed_fn

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


def _record_book(symbol: str, book: dict) -> None:
    """Feed Session Record's quote/L2 streams (D-064).

    Hooked here, at the two ib_async ``updateEvent`` handlers, rather than at
    ``state.push_book``: that is a shared broadcast channel which ``sim/feed``
    and ``sim/market`` also push through, so a hook there recorded SIM and
    replay books into a live capture -- stamped with wall clock while the sim
    bridge stamps sim session time, which tripped the recorder's
    timestamp-regression stop. Only the IBKR feed reaches these two.

    Runs inside the socket callback, so it only enqueues (ADR 010).
    """
    try:
        from capture.bridge_ibkr import enqueue_book

        enqueue_book(symbol, book)
    except Exception:
        logger.exception("IBKR depth: capture book enqueue failed for %s", symbol)


def _watch_book(symbol: str, book: dict) -> None:
    """Feed the book watcher (ADR 031) the live book -- enqueue only, like the recorder (ADR 010)."""
    try:
        from book_watch.live import enqueue_book

        enqueue_book(symbol, book)
    except Exception:
        logger.exception("IBKR depth: book watcher enqueue failed for %s", symbol)


def _broadcast_live(symbol: str, book: dict) -> None:
    """Show a live book to the desk's panels -- except on a Sim desk off the live edge.

    There the only live line is one Session Record holds (#315). Its books still
    update ``_subscriptions`` (the live print side is classified against it) and
    reach the recording, but the practice desk's ladders and sensors read the
    replay through ``push_book`` and must not be handed the market. At the live
    edge a Sim tab is live (ADR 020 live-edge amendment) and sees the book.
    """
    from sim.mode import is_replay_desk
    if not is_replay_desk():
        state.push_book(symbol, book)


def _rows(levels: list[Level], side: str) -> list[dict]:
    return [{"price": lv.price, "size": lv.size, "side": side, "mm": lv.mm} for lv in levels]


_warned_out_of_order: set[str] = set()


@timed_fn("ib.depth")
def on_update_book(ticker: Any, symbol: str) -> None:
    """Push the book kept from ``ticker.domTicks`` (#540), never ib_async's ``domBids`` / ``domAsks``."""
    kept = state.book_for(symbol)
    kept.apply(getattr(ticker, "domTicks", None) or ())
    bids = _rows(kept.bids, "bid")[:IBKR_DEPTH_NUM_ROWS]
    asks = _rows(kept.asks, "ask")[:IBKR_DEPTH_NUM_ROWS]
    if not kept.in_price_order():
        # A row operation Nova never saw (it cannot happen while every update
        # event is handled). Keep the best price first rather than push a wrong
        # top of book, and say so once per line.
        if symbol not in _warned_out_of_order:
            _warned_out_of_order.add(symbol)
            logger.warning("IBKR depth: %s book out of price order after an update; sorting it", symbol)
        bids, asks = sort_levels(bids, bid=True), sort_levels(asks, bid=False)
    book = {"bids": bids, "asks": asks, "l1_fallback": False}
    state._subscriptions[symbol] = book
    _broadcast_live(symbol, book)
    _record_book(symbol, book)
    _watch_book(symbol, book)


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
    _broadcast_live(symbol, book)
    _record_book(symbol, book)


def install_error_hook(ib: Any) -> None:
    """Wire a one-time errorEvent listener for async depth rejection → L1."""
    if id(ib) in state._error_hooked_ib_ids:
        return
    ib.errorEvent += on_ib_error
    state._error_hooked_ib_ids.add(id(ib))


def on_ib_error(reqId: int, errorCode: int, errorString: str, contract: Any) -> None:
    if errorCode not in (IBKR_ERROR_DEPTH_NOT_SUPPORTED, IBKR_ERROR_DEPTH_RESET) or contract is None:
        return
    con_id = getattr(contract, "conId", None)
    if con_id is None:
        return
    if errorCode == IBKR_ERROR_DEPTH_RESET:
        # IBKR resends the whole book from row 0; start the kept book empty (#540).
        for sym, c in list(state._contracts.items()):
            if getattr(c, "conId", None) == con_id:
                state.reset_book(sym)
                _warned_out_of_order.discard(sym)
                logger.info("IBKR depth: %s book reset by IBKR (%s)", sym, errorCode)
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
