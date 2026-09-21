"""IBKR depth subscribe / unsubscribe and idle-only capacity eviction."""
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


async def subscribe_async(symbol: str, *, live: bool = False) -> dict:
    """
    Qualify + subscribe to Level 2 (or L1 fallback).
    Safe under FastAPI's running event loop.

    ``live`` opens a real IBKR line even on a Sim desk, replacing a replay slot:
    Session Record captures the live market whatever the desk is practising on
    (#315). Panels never pass it, so a Sim desk off the live edge still shows
    the replay. At the live edge (ADR 020 live-edge amendment) a Sim tab is a
    Paper tab on the feed: it opens a real line the same way, replacing any
    replay slot it reserved off the edge, so the backend holds the line a bot
    needs (``bot.eligibility``).
    """
    from sim.mode import is_replay_desk, is_sim_mode

    if is_replay_desk() and not live:
        from sim import market as _sim_market

        state.reserve_slot(symbol)
        replayed = _sim_market.book()
        book = (
            dict(replayed)
            if replayed and str(replayed.get("symbol") or "").upper() == symbol.upper()
            else {"bids": [], "asks": [], "l1_fallback": True}
        )
        book["symbol"] = symbol.upper()
        state._subscriptions[symbol] = book
        state.push_book(symbol, book)
        return {"ok": True, "error": None, "symbols": state.subscribed_symbols()}
    if is_sim_mode():
        live = True

    if not _client.is_ready():
        return {
            "ok": False,
            "error": _client.unavailable_detail("IBKR depth"),
            "symbols": state.subscribed_symbols(),
        }

    async with state.get_subscribe_lock():
        if symbol in state._subscriptions and (not live or state.is_live(symbol)):
            return {"ok": True, "error": None, "symbols": state.subscribed_symbols()}
        if symbol in state._subscriptions:
            # A replay slot is not a line: it must not count against the cap
            # or survive as the book a real subscription replaces.
            state.drop_slot(symbol)

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
    """Free idle depth slot(s) so `incoming` can subscribe.

    Live viewers (``viewer_count > 0``) are never evicted -- a 4th symbol
    is refused by the caller (ADR 011 / D-027). Idle-only eviction stays
    so a leaked empty slot cannot wedge the cap.
    """
    while len(state._subscriptions) >= IBKR_MAX_DEPTH_SYMBOLS:
        idle = [
            s for s in list(state._subscriptions.keys())
            if s != incoming and state.viewer_count(s) <= 0
        ]
        if not idle:
            logger.warning(
                "IBKR: refusing depth subscribe for %s -- %s live viewers at cap",
                incoming, IBKR_MAX_DEPTH_SYMBOLS,
            )
            return
        victim = idle[0]
        logger.warning(
            "IBKR: evicting idle depth slot %s to free capacity for %s",
            victim, incoming,
        )
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
        # Depth-only lines use reqMktDepth. cancelMktData here steals the
        # shared ticks L1 (or logs "No subscription") and drops halt observe
        # for the focused symbol (#237). L1 fallback is ticks-owned.
    if shared:
        from ibkr import ticks as _ticks

        _ticks.drop_owner(symbol, _ticks.OWNER_DEPTH)


def needs_subscribe(symbol: str) -> bool:
    """Whether a viewer must (re)subscribe before streaming ``symbol``.

    True with no entry at all, and on a Sim desk at the live edge when the
    entry is a replay slot rather than a real line (ADR 020 live-edge
    amendment): the tab remounting at the edge must get the market, not the
    slot it reserved off it.
    """
    if not state.is_subscribed(symbol):
        return True
    from sim.mode import is_replay_desk, is_sim_mode

    return is_sim_mode() and not is_replay_desk() and not state.is_live(symbol)
