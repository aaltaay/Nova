"""IBKR depth subscribe / unsubscribe and idle-only capacity eviction.

A line of an ended IBKR session is let go here (``drop_stale``, #562): cancelled
only where the IB in hand still holds it, and asked for again by
``ibkr/line_session.py`` while a viewer, a hold or the L2 recorder wants it.

A line IBKR refused (309) is let go without a cancel (``refuse_line``): IBKR never
opened it, and its viewers are told why and ask again on their own backoff. Every
other line is let go through ``ibkr/depth/release.py``, which cancels a request only
once IBKR has answered it: a cancel that beats IBKR's grant leaves the line held
inside IB Gateway until it restarts (tested on the live Gateway, 2026-10-13).
"""
from __future__ import annotations

import asyncio
import logging

from constants import (
    IBKR_DEPTH_NUM_ROWS,
    IBKR_DEPTH_REGISTRY_KIND,
    IBKR_DEPTH_SMART,
    IBKR_MAX_DEPTH_SYMBOLS,
)
from ibkr import client as _client
from ibkr import line_session, stray_lines
from ibkr.depth import handlers, release, state
from metrics.op_metrics import timed_sync

logger = logging.getLogger(__name__)


def _facade_attr(name: str):
    """Resolve monkeypatchable symbols on the ibkr.depth facade."""
    import ibkr.depth as facade
    return getattr(facade, name)


async def subscribe_async(symbol: str, *, live: bool = False, agent: bool = False) -> dict:
    """
    Qualify + subscribe to Level 2 (or L1 fallback).
    Safe under FastAPI's running event loop.

    ``agent`` is Claude's own line (ADR 068). Every other request leaves Claude's
    reserved line alone: past ``agent_trader.lines.desk_cap`` lines of its own it is
    refused in words, with ``agent_reserved: true``.

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
        if any(state.is_stale(s) for s in list(state._subscriptions)):
            line_session.settle()  # lines of an ended session hold no slot (#562)
        if symbol in state._subscriptions and (not live or state.is_live(symbol)):
            return {"ok": True, "error": None, "symbols": state.subscribed_symbols()}
        if symbol in state._subscriptions:
            # A replay slot is not a line: it must not count against the cap
            # or survive as the book a real subscription replaces.
            state.drop_slot(symbol)

        if len(state._subscriptions) >= IBKR_MAX_DEPTH_SYMBOLS:
            await evict_for_capacity(symbol)
        if not agent and (held_for_agent := _agent_refusal(symbol)):
            return {"ok": False, "error": held_for_agent, "cap": True, "agent_reserved": True,
                    "symbols": state.subscribed_symbols()}
        if len(state._subscriptions) >= IBKR_MAX_DEPTH_SYMBOLS:
            return {
                "ok": False,
                "error": (
                    f"Symbol cap reached ({IBKR_MAX_DEPTH_SYMBOLS} max simultaneous "
                    "depth streams)"
                ),
                "cap": True,
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
        state.stamp_line(symbol)

        try:
            state.reset_book(symbol)  # IBKR sends this request's book from row 0 (#540)
            # A request let go but held for IBKR's answer carries on as this line (ib_async reuses it).
            release.take_back(ib, contract)
            with timed_sync("ibkr.depth.subscribe"):
                ticker = ib.reqMktDepth(
                    contract,
                    numRows=IBKR_DEPTH_NUM_ROWS,
                    isSmartDepth=IBKR_DEPTH_SMART,
                )
            state.note_line_ib(symbol, ib)
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


def _agent_refusal(symbol: str) -> str | None:
    """Why a desk request must leave Claude's reserved line alone (ADR 068), or None."""
    from agent_trader import lines as agent_lines

    return agent_lines.desk_refusal(symbol)


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


def unsubscribe(symbol: str, *, refused: bool = False) -> None:
    """Let go of the symbol's line through ``release``: cancelled once IBKR has answered; ``refused`` never.

    The IB is the one the request was made on: while the session is not READY ``get_ib`` is None, and a line
    let go then must be held for READY, never dropped from the books with its request still open at IBKR.
    """
    ib = state.pop_line_ib(symbol) or _client.get_ib()
    fate = _fate(ib, symbol) if state.is_stale(symbol) else None
    contract = state.pop_contract(symbol)
    shared = state.is_shared_l1(symbol)
    handlers.detach_update_handler(symbol)
    state.clear_symbol(symbol)
    if ib is not None and contract is not None:
        if refused:
            release.forget(ib, contract)
        elif fate != line_session.GONE:
            release.release(ib, contract, symbol, IBKR_DEPTH_SMART, lost=fate == line_session.LOST)
        # Depth-only lines use reqMktDepth. cancelMktData here steals the
        # shared ticks L1 (or logs "No subscription") and drops halt observe
        # for the focused symbol (#237). L1 fallback is ticks-owned.
    if shared:
        from ibkr import ticks as _ticks

        _ticks.drop_owner(symbol, _ticks.OWNER_DEPTH)


def refusal_message(symbol: str) -> str:
    """What the ladder shows for a 309: whose lines are in use, and how to free one.

    Requests Nova let go but holds for IBKR's answer count as Nova's: they free the moment IBKR answers.
    Fewer than the cap between them means lines held outside Nova -- logged as an ERROR, with the evidence.
    """
    held = [s for s in state.subscribed_symbols() if s != symbol and state.is_live(s)]
    waiting = [h for h in release.held_lines() if h["symbol"] != symbol.upper()]
    cap = IBKR_MAX_DEPTH_SYMBOLS
    if len(held) >= cap:
        return (f"IBKR refused this Level 2: all {cap} of its Level 2 lines are in use "
                f"({', '.join(held)}). Close one to free a line. Asking again shortly.")
    if len(held) + len(waiting) >= cap:
        names = ", ".join(f"{h['symbol']} ({h['age_sec']:.0f} s)" for h in waiting)
        mine = f"{', '.join(held)} and " if held else ""
        return (f"IBKR refused this Level 2: all {cap} of its Level 2 lines are in use -- {mine}"
                f"{names}, which Nova let go and cancels the moment IBKR answers its request. "
                "Asking again shortly.")
    holds = f"only {len(held)} ({', '.join(held)})" if held else "none of them"
    if waiting:
        holds += f" and waits on IBKR's answer for {', '.join(h['symbol'] for h in waiting)}"
    logger.error("IBKR depth: IBKR refused %s's Level 2 with all %s lines in use, but Nova holds %s -- %s "
                 "line(s) are held outside Nova (inside IB Gateway, or by another session of this login)",
                 symbol, cap, holds, cap - len(held) - len(waiting))
    return (f"IBKR refused this Level 2 (IB error 309): all {cap} of its Level 2 lines are in use, "
            f"and Nova holds {holds}. The others are held inside IB Gateway; if this stays, "
            "restarting IB Gateway frees them. Asking again shortly.")


def refuse_line(symbol: str, req_id: int) -> bool:
    """IBKR refused the symbol's line (309): it is not open. Its viewers are told and close; True when ended.

    Only while the line is still that request: a newer request for the symbol is left alone.
    """
    ib = _client.get_ib()
    contract = state._contracts.get(symbol)
    if contract is None or state.is_stale(symbol):
        return False
    if ib is not None and stray_lines.request_id(ib, contract, "mktDepth") != req_id:
        return False
    message = refusal_message(symbol)
    state.note_refused(symbol, message)
    state.push_error(symbol, message, evicted=True)
    unsubscribe(symbol, refused=True)
    return True


def _fate(ib, symbol: str) -> str:
    return line_session.fate(ib, state._contracts.get(symbol), IBKR_DEPTH_REGISTRY_KIND,
                             state._tickers.get(symbol))


def is_watched(symbol: str) -> bool:
    """A viewer, a hold (Session Record, auto-record) or the L2 recorder still wants the line."""
    if state.viewer_count(symbol) > 0:
        return True
    from l2 import recorder as l2_recorder

    return l2_recorder.is_recording(symbol)


def drop_stale() -> list[str]:
    """Let go of every depth line of an ended IBKR session (#562); the symbols still watched.

    A line IBKR kept across a connectivity restore (1102) is restamped and stays.
    Viewers keep their queues, so the line asked for again feeds them.
    """
    ib = _client.get_ib()
    watched: list[str] = []
    for symbol in [s for s in list(state._subscriptions) if state.is_stale(s)]:
        fate = _fate(ib, symbol)
        if fate == line_session.KEPT:
            state.stamp_line(symbol)
            logger.info("IBKR depth: %s's Level 2 line survived the connectivity restore (IBKR kept it)", symbol)
            continue
        logger.warning("IBKR depth: the Level 2 line of %s ended with its IBKR session (%s) -- letting it go",
                       symbol, fate)
        unsubscribe(symbol)
        if is_watched(symbol):
            watched.append(symbol)
    return watched


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
