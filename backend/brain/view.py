"""The brain as its program and its header pill read it: ``GET /api/brain`` and the brain's part of
``GET /api/traders`` (``bot.md`` "The brain's door", ``traders.md`` "On the wire"). Memory and ledger reads only.
"""
from __future__ import annotations

import logging
from typing import Any

from brain import book, rules, session
from brain.constants_brain import BRAIN_DAY_STOP_USD, BRAIN_ORIGIN, BRAIN_SCHEMA_VERSION, BRAIN_UNREAD_TEXT
from constants_traders import TRADER_STATE_BUY_SET, TRADER_STATE_IN_TRADE, TRADER_STATE_WATCHING

logger = logging.getLogger(__name__)
NOT_RUNNING_TEXT = "Brain · On · its program is not running"
_ORDER_FIELDS = ("order_id", "symbol", "side", "qty", "order_type", "limit_price", "stop_price", "status", "leg_role")


def lane_view() -> dict[str, Any]:
    from line_lanes import brain as lane
    from line_lanes import lanes

    sym = lane.stock()
    up = lanes.lines_up(sym) if sym else {lanes.DEPTH: False, lanes.TAPE: False}
    return {"symbol": sym, "why": lane.why(), "since": lanes.since(BRAIN_ORIGIN) if sym else None,
            "depth": bool(up[lanes.DEPTH]), "tape": bool(up[lanes.TAPE])}


def reading(lane_symbol: str | None) -> list[dict[str, str]]:
    return [{**row, "source": "lane" if row["symbol"] == lane_symbol else "level1"} for row in session.reading()]


def _money(pnl: float | None) -> str:
    return "" if pnl is None else f" {'+' if pnl >= 0 else '-'}${abs(pnl):,.2f}"


def fill_trader(out: dict[str, Any]) -> None:
    """The brain's own fields on its ``GET /api/traders`` row; with its switch On, its state and its pill's words."""
    lane = lane_view()
    out["symbol"] = lane["symbol"]
    out["lane"] = {"symbol": lane["symbol"], "depth": lane["depth"], "tape": lane["tape"], "why": lane["why"]}
    out["note"] = session.note()
    out["connected"] = session.connected()
    out["reading"] = reading(lane["symbol"])
    out["events"] = session.events()
    out["today"]["loss_limit_usd"] = BRAIN_DAY_STOP_USD
    if not out["on"]:
        return
    position = out.get("position")
    if not out["connected"]:
        out["state"], out["text"] = (TRADER_STATE_IN_TRADE if position else TRADER_STATE_WATCHING), NOT_RUNNING_TEXT
        return
    if position:
        out["state"] = TRADER_STATE_IN_TRADE
        out["text"] = f"Brain · In {position['symbol']}{_money(position['unrealized_pnl'])}"
        return
    try:
        resting = book.entries()
    except book.ReadError:
        logger.warning("BRAIN view: Paper's orders could not be read", exc_info=True)
        resting = []
    if resting:
        out["state"], out["text"] = TRADER_STATE_BUY_SET, f"Brain · Buying {resting[0].get('symbol')}"
    else:
        out["state"] = TRADER_STATE_WATCHING
        out["text"] = f"Brain · Watching {lane['symbol']}" if lane["symbol"] else "Brain · Watching"


def status(session_id: str | None = None) -> dict[str, Any]:
    """``GET /api/brain``: everything the brain's program needs to know before it acts."""
    from sim.mode import venue
    from traders import limits as trader_limits
    from traders import switches, view as traders_view

    now = switches.now_ts()
    broker = traders_view._broker(venue())          # the desk venue's account, Paper on Live (as GET /api/traders)
    refused_on = switches.on_refusal(BRAIN_ORIGIN, now)
    why_not = rules.standing_refusal()
    lane = lane_view()
    orders: list[dict[str, Any]] = []
    error = None
    try:
        orders = [{k: row.get(k) for k in _ORDER_FIELDS} for row in book.working()]
    except book.ReadError:
        logger.warning("BRAIN view: Paper's orders could not be read", exc_info=True)
        error = BRAIN_UNREAD_TEXT
    handed = traders_view._handed(BRAIN_ORIGIN, broker)
    today = traders_view._today(BRAIN_ORIGIN, broker)
    today["loss_limit_usd"] = BRAIN_DAY_STOP_USD
    return {
        "schema_version": BRAIN_SCHEMA_VERSION, "generated_at": now, "venue": venue(),
        "switch": {"on": switches.is_on(BRAIN_ORIGIN, now), "can_turn_on": refused_on is None,
                   "why_not_on": None if refused_on is None else {"reason": refused_on[0], "error": refused_on[1]}},
        "connected": session.connected(), "session": session.view(session_id),
        "lane": lane, "position": traders_view._position(BRAIN_ORIGIN, broker, {h["symbol"] for h in handed}),
        "handed": handed, "orders": orders, "today": today,
        "limits": {**traders_view._limits(BRAIN_ORIGIN, broker), **{"flat_by": trader_limits.of(BRAIN_ORIGIN)["flat_by"]}},
        "can_enter": why_not is None, "why_not": None if why_not is None else {"code": why_not[0], "text": why_not[1]},
        "note": session.note(), "reading": reading(lane["symbol"]), "events": session.events(now), "error": error,
    }
