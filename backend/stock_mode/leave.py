"""Leaving a venue cancels Nova's working entries there first (ADR 042 F).

Before the desk moves (``sim.mode.set_venue`` and ``POST /api/desk/venue``), every Nova entry
still working on the venue it leaves -- the bot's, Auto-entry's and an approved bracket's
entry -- is cancelled there, while the execution door still sends to that venue. Each is on the
audit stream (a ``missed``, which gives the day's count back), and the venue change answers the
list as ``left: [{venue, symbol, order_id, by, text, ok}]`` so the desk toasts each. Open
positions keep their resting exits: Paper's fill while the desk is elsewhere.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from constants_sim import DESK_PRACTICE_VENUES
from constants_stock_mode import STOCK_MODE_APPROVE, STOCK_MODE_AUTO_ENTRY, STOCK_MODE_TRADE_ENTERING

logger = logging.getLogger(__name__)
_BY = {STOCK_MODE_AUTO_ENTRY: "auto_entry", STOCK_MODE_APPROVE: "approve"}
_WAIT_SEC = 10.0
_leaving: tuple[str, str] | None = None     # (old, new) while ``leave`` sweeps ``old``


def leaving() -> tuple[str, str] | None:
    """``(old, new)`` while the desk is leaving ``old``: no new Nova entry may start meanwhile."""
    return _leaving


def leaving_text(move: tuple[str, str]) -> str:
    return (f"the desk is moving from {move[0]} to {move[1]}: Nova starts no new entry while it cancels "
            f"its working ones on {move[0]}")


def has_work(old: str | None) -> bool:
    """Whether anything Nova sent waits to fill on ``old`` (a cheap, memory-only check)."""
    if old not in DESK_PRACTICE_VENUES:
        return False
    from bot.persist import load_session
    from stock_mode import store

    row = load_session()
    trade = row.get("trade")
    if isinstance(trade, dict) and trade.get("state") == "entering" and trade.get("venue") == old:
        return True
    if any(str(w.get("side") or "").upper() == "BUY" and w.get("venue") == old for w in row.get("working") or []):
        return True
    return any(t.get("venue") == old and t.get("state") == STOCK_MODE_TRADE_ENTERING for t in store.trades())


async def leave(old: str | None, new: str) -> list[dict[str, Any]]:
    """Cancel Nova's entries still working on ``old`` before the desk moves to ``new``."""
    if old in (None, new) or old not in DESK_PRACTICE_VENUES:
        return []
    global _leaving
    _leaving = (old, new)
    try:
        return await _sweep(old, new)
    finally:
        _leaving = None


async def _sweep(old: str, new: str) -> list[dict[str, Any]]:
    from bot.first_pullback.handover import leave_venue
    from stock_mode import orders, runner, store

    out = await leave_venue(old, new)
    now = runner._clock()
    for trade in store.trades():
        if trade.get("venue") != old or trade.get("state") != STOCK_MODE_TRADE_ENTERING or not trade.get("entry_order_id"):
            continue
        sym, oid = trade["symbol"], int(trade["entry_order_id"])
        by = _BY.get(str(trade.get("kind")), str(trade.get("kind")))
        receipt = await orders.cancel(trade, oid, source="manual")
        if receipt.ok:
            runner.miss(trade, now, f"the desk left {old} before the entry filled -- it was cancelled there")
            out.append({"venue": old, "symbol": sym, "order_id": oid, "by": by, "ok": True,
                        "text": f"Nova's {by.replace('_', '-')} buy of {sym} on {old} was cancelled: the desk moved "
                                f"to {new}"})
        else:
            out.append({"venue": old, "symbol": sym, "order_id": oid, "by": by, "ok": False,
                        "text": f"Nova's {by.replace('_', '-')} buy of {sym} on {old} could not be cancelled "
                                f"({orders.receipt_error(receipt)}) -- it may still fill there"})
    return out


def _on_a_loop() -> bool:
    """Whether this thread runs an event loop (it then cannot wait on one)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:  # maintainer: allow-swallow no running loop is the answer from a worker thread
        return False
    return True


def leave_sync(old: str | None, new: str) -> list[dict[str, Any]]:
    """``leave`` from a sync caller (``sim.mode.set_venue``): on the HTTP loop when it runs in another
    thread, else in a loop of its own. From a running loop's own thread it cannot wait -- the caller
    must ``await leave`` first (``POST /api/desk/venue`` does) -- and it says so."""
    try:
        if not has_work(old):
            return []
    except Exception as exc:
        # The desk still moves: an unreadable session or trades file is said, never a reason to stay.
        logger.exception("stock mode: Nova's working entries on %s could not be read before the move", old)
        return [{"venue": old, "symbol": None, "order_id": None, "by": None, "ok": False,
                 "text": f"Nova could not read its working entries on {old} ({exc}): check {old}'s orders"}]
    if _on_a_loop():
        logger.error("stock mode: the venue change from %s ran on an event loop without cancelling Nova's working "
                     "entries first -- they were left working there", old)
        return [{"venue": old, "symbol": None, "order_id": None, "by": None, "ok": False,
                 "text": f"Nova's working entries on {old} were not cancelled before the desk moved: check {old}'s "
                         "orders"}]
    from ibkr.loop_supervisor import get_http_loop

    loop = get_http_loop()
    try:
        if loop is not None and loop.is_running():
            return asyncio.run_coroutine_threadsafe(leave(old, new), loop).result(timeout=_WAIT_SEC)
        return asyncio.run(leave(old, new))
    except Exception as exc:
        # The desk still moves (a venue the operator chose is never refused over this); what Nova
        # could not cancel is said, never assumed gone.
        logger.exception("stock mode: Nova's working entries on %s could not be cancelled before the move", old)
        return [{"venue": old, "symbol": None, "order_id": None, "by": None, "ok": False,
                 "text": f"Nova could not cancel its working entries on {old} ({exc}): check {old}'s orders"}]


async def leave_safely(old: str | None, new: str) -> list[dict[str, Any]]:
    """``leave`` for an async caller: a failure is said in the list, never raised into the venue change."""
    try:
        return await leave(old, new)
    except Exception as exc:
        logger.exception("stock mode: Nova's working entries on %s could not be cancelled before the move", old)
        return [{"venue": old, "symbol": None, "order_id": None, "by": None, "ok": False,
                 "text": f"Nova could not cancel its working entries on {old} ({exc}): check {old}'s orders"}]
