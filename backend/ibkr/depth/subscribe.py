"""IBKR depth subscribe / unsubscribe and capacity eviction."""
from __future__ import annotations

import asyncio
import logging

from constants import IBKR_DEPTH_NUM_ROWS, IBKR_DEPTH_SMART, IBKR_MAX_DEPTH_SYMBOLS
from ibkr import client as _client
from ibkr.depth import handlers, state
from metrics.op_metrics import timed_sync

logger = logging.getLogger(__name__)


def _facade_attr(name: str):
    """Resolve monkeypatchable symbols on the ibkr.depth facade."""
    import ibkr.depth as facade
    return getattr(facade, name)


async def subscribe_async(symbol: str) -> dict:
    """
    Qualify + subscribe to Level 2 (or L1 fallback).
    Safe under FastAPI's running event loop.
    """
    if not _client.is_ready():
        return {
            "ok": False,
            "error": _client.unavailable_detail("IBKR depth"),
            "symbols": state.subscribed_symbols(),
        }

    async with state.get_subscribe_lock():
        if symbol in state._subscriptions:
            return {"ok": True, "error": None, "symbols": state.subscribed_symbols()}

        if len(state._subscriptions) >= IBKR_MAX_DEPTH_SYMBOLS:
            await evict_for_capacity(symbol)
        if len(state._subscriptions) >= IBKR_MAX_DEPTH_SYMBOLS:
            return {
                "ok": False,
                "error": (
                    f"Symbol cap reached ({IBKR_MAX_DEPTH_SYMBOLS} max simultaneous "
                    "depth streams)"
                ),
                "symbols": state.subscribed_symbols(),
            }

        if not _facade_attr("_load_ib_types")():
            return {
                "ok": False,
                "error": "ib_async not installed",
                "symbols": state.subscribed_symbols(),
            }

        ib = _client.get_ib()
        if ib is None:
            return {
                "ok": False,
                "error": _client.unavailable_detail("IBKR depth"),
                "symbols": state.subscribed_symbols(),
            }

        handlers.install_error_hook(ib)
        state.reserve_slot(symbol)

        stock_cls = _facade_attr("_Stock")
        contract = stock_cls(symbol, "SMART", "USD")
        try:
            qualified = await ib.qualifyContractsAsync(contract)
            if not qualified:
                state.drop_slot(symbol)
                return {
                    "ok": False,
                    "error": f"Could not qualify contract for {symbol}",
                    "symbols": state.subscribed_symbols(),
                }
            contract = qualified[0]
        except Exception as exc:
            state.drop_slot(symbol)
            logger.exception("IBKR: qualify failed for %s: %s", symbol, exc)
            return {
                "ok": False,
                "error": f"Qualify failed: {exc}",
                "symbols": state.subscribed_symbols(),
            }

        state._contracts[symbol] = contract

        try:
            with timed_sync("ibkr.depth.subscribe"):
                ticker = ib.reqMktDepth(
                    contract,
                    numRows=IBKR_DEPTH_NUM_ROWS,
                    isSmartDepth=IBKR_DEPTH_SMART,
                )
            handlers.attach_update_handler(
                symbol, ticker, lambda t: handlers.on_update_book(t, symbol),
            )
            logger.info(
                "IBKR: subscribed depth for %s (conId=%s, smart=%s, rows=%s)",
                symbol, contract.conId, IBKR_DEPTH_SMART, IBKR_DEPTH_NUM_ROWS,
            )
        except Exception as exc:
            logger.warning(
                "IBKR: depth unavailable for %s (%s), falling back to L1", symbol, exc,
            )
            try:
                from ibkr import ticks as _ticks

                # Own the fallback through ticks: a private reqMktData returns
                # the same pooled ticker anyway, and depth's cancelMktData
                # would then close a line scanner/detail/HOD still want.
                reused = _ticks.get_ticker(symbol) is not None
                if not await _ticks.subscribe(symbol, _ticks.OWNER_DEPTH):
                    raise RuntimeError("shared L1 subscribe failed")
                ticker = _ticks.get_ticker(symbol)
                if ticker is None:
                    raise RuntimeError("shared L1 ticker missing after subscribe")
                state.mark_shared_l1(symbol)
                handlers.attach_update_handler(
                    symbol, ticker, lambda t: handlers.on_update_ticker(t, symbol),
                )
                state._subscriptions[symbol]["l1_fallback"] = True
                logger.info(
                    "IBKR: subscribed L1 fallback for %s (conId=%s, reused_ticks_stream=%s)",
                    symbol, contract.conId, reused,
                )
            except Exception as exc2:
                unsubscribe(symbol)
                logger.exception("IBKR: L1 fallback also failed for %s: %s", symbol, exc2)
                return {"ok": False, "error": str(exc2), "symbols": state.subscribed_symbols()}

        return {"ok": True, "error": None, "symbols": state.subscribed_symbols()}


async def evict_for_capacity(incoming: str) -> None:
    """Free depth slot(s) so `incoming` can subscribe."""
    while len(state._subscriptions) >= IBKR_MAX_DEPTH_SYMBOLS:
        idle = [
            s for s in list(state._subscriptions.keys())
            if s != incoming and state.viewer_count(s) <= 0
        ]
        if idle:
            victim = idle[0]
            logger.warning(
                "IBKR: evicting idle depth slot %s to free capacity for %s",
                victim, incoming,
            )
        else:
            others = [s for s in list(state._subscriptions.keys()) if s != incoming]
            if not others:
                return
            victim = others[0]
            logger.warning(
                "IBKR: force-evicting depth slot %s (viewer_count=%s, possible leak) for %s",
                victim, state.viewer_count(victim), incoming,
            )
            # "Possible leak" is a guess, not a guarantee -- if viewer_count
            # was real (an active viewer, not a leaked count), this line is
            # being torn down out from under them. Tell any open viewer
            # queue before unsubscribing so its socket closes and the
            # frontend reconnects instead of silently sitting on a dead
            # line (PROBLEM_LOG 2026-08-25).
            state.push_error(
                victim,
                f"Depth line closed to free capacity for {incoming}",
                evicted=True,
            )
            state._ws_viewers.pop(victim, None)
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
            "symbols": state.subscribed_symbols(),
        }
    return asyncio.run(subscribe_async(symbol))


def unsubscribe(symbol: str) -> None:
    ib = _client.get_ib()
    contract = state.pop_contract(symbol)
    shared = state.is_shared_l1(symbol)
    handlers.detach_update_handler(symbol)
    state.clear_symbol(symbol)
    if ib and contract is not None:
        try:
            ib.cancelMktDepth(contract, isSmartDepth=IBKR_DEPTH_SMART)
        except Exception as exc:
            logger.debug(
                "IBKR: cancelMktDepth on unsubscribe for %s ignored: %s",
                symbol, exc,
            )
        # Shared fallback ticker is owned by ibkr.ticks (refcounted by owner) —
        # cancelling it here would kill the stream out from under scanner/HOD/
        # detail owners who still want it. Release the depth owner instead; ticks
        # cancels only when depth was the last one holding the line.
        if not shared:
            try:
                ib.cancelMktData(contract)
            except Exception as exc:
                logger.debug(
                    "IBKR: cancelMktData on unsubscribe for %s ignored: %s",
                    symbol, exc,
                )
    if shared:
        from ibkr import ticks as _ticks

        _ticks.drop_owner(symbol, _ticks.OWNER_DEPTH)
