"""``GET /api/traders``: Claude and the brain as the header pills and their panels show them (``traders.md``).

Read-only. Claude's state, stock, position and note are its seat's (``agent_trader.view``); the brain has no door
yet (ADR 072 build order 4), so it reads Off or Watching with what its book holds. Figures are the desk venue's
account (Paper on Live, where neither trades).
"""
from __future__ import annotations

import logging
from typing import Any

from constants_owners import AI_TRADERS, OWNER_BRAIN, OWNER_CLAUDE
from constants_practice import PRACTICE_VENUE_PAPER, PRACTICE_VENUE_SIM
from constants_traders import (
    TRADER_STATE_BUY_SET,
    TRADER_STATE_DONE,
    TRADER_STATE_IN_TRADE,
    TRADER_STATE_OFF,
    TRADER_STATE_WATCHING,
    TRADERS_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)
_SHORT = {OWNER_CLAUDE: "Claude", OWNER_BRAIN: "Brain"}
_SEAT_STATES = {"set": TRADER_STATE_BUY_SET, "in": TRADER_STATE_IN_TRADE, "done": TRADER_STATE_DONE}


def _venue() -> str:
    from sim.mode import venue

    return venue()


def _broker(venue: str) -> Any:
    from practice.broker import for_venue

    return for_venue(venue if venue in (PRACTICE_VENUE_PAPER, PRACTICE_VENUE_SIM) else PRACTICE_VENUE_PAPER)


def _money(pnl: float | None) -> str:
    return "" if pnl is None else f" {'+' if pnl >= 0 else '-'}${abs(pnl):,.2f}"


def _handed(trader: str, broker: Any) -> list[dict[str, Any]]:
    from traders import handed
    from traders.off import _resting_stops

    ledger = broker.ledger
    out = []
    for symbol, who in sorted(handed.active(broker.venue, ledger, broker.reference.now_ts()).items()):
        if who != trader:
            continue
        stops = _resting_stops(trader, broker.venue, symbol)
        out.append({"symbol": symbol, "qty": ledger.owners.qty_of(symbol, trader),
                    "stop_price": stops[0] if stops else None})
    return out


def _position(trader: str, broker: Any, handed_symbols: set[str]) -> dict[str, Any] | None:
    owners = getattr(broker.ledger, "owners", None)
    if owners is None:
        return None
    for symbol, lots in sorted(owners.lots.items()):
        lot = lots.get(trader)
        if lot is None or abs(lot.qty) < 1e-9 or symbol in handed_symbols:
            continue
        mark = broker.ledger.mark_or_cost(symbol)
        return {"symbol": symbol, "qty": lot.qty, "avg_cost": round(lot.avg, 4), "mark": mark,
                "unrealized_pnl": round((float(mark) - lot.avg) * lot.qty, 2)}
    return None


def _today(trader: str, broker: Any) -> dict[str, Any]:
    owners = getattr(broker.ledger, "owners", None)
    pnl = None if owners is None else round(owners.today(trader, broker.ledger.mark_or_cost)["day_pnl"], 2)
    return {"pnl": pnl, "loss_limit_usd": None, "tripped_at": None}


def _limits(trader: str, broker: Any) -> dict[str, Any]:
    from owners import budget
    from traders import limits

    row = limits.of(trader)
    return {"max_shares": row["max_shares"], "risk_usd": row["risk_usd"], "budget_usd": row["budget_usd"],
            "budget_used_usd": round(budget.used_usd(broker.ledger, trader), 2), "flat_by": row["flat_by"]}


def trader_view(trader: str, switch: dict[str, Any], now: float) -> dict[str, Any]:
    from traders import switches

    broker = _broker(_venue())
    handed_rows = _handed(trader, broker)
    why = switches.on_refusal(trader, now)
    position = _position(trader, broker, {h["symbol"] for h in handed_rows})
    today = _today(trader, broker)
    out: dict[str, Any] = {
        "name": trader, "on": bool(switch.get("on")), "at": switch.get("at"),
        "can_turn_on": why is None, "why_not_on": None if why is None else {"reason": why[0], "error": why[1]},
        "done_for_today": False, "state": TRADER_STATE_OFF, "text": f"{_SHORT[trader]} · Off", "symbol": None,
        "lane": {"symbol": None, "depth": False, "tape": False}, "position": position, "handed": handed_rows,
        "today": today, "limits": _limits(trader, broker), "note": None,
    }
    if trader == OWNER_CLAUDE:
        _claude(out)
    if why is not None and why[0] == "TRADER_DAY_STOP":
        out["done_for_today"] = True
    if not out["on"]:
        out["state"] = TRADER_STATE_DONE if out["done_for_today"] else TRADER_STATE_OFF
        tail = f" · {handed_rows[0]['symbol']} is yours to close" if handed_rows else ""
        out["text"] = (f"{_SHORT[trader]} · Done for today{_money(today['pnl'])}" if out["done_for_today"]
                       else f"{_SHORT[trader]} · Off{tail}")
    elif trader == OWNER_BRAIN:
        out["state"] = TRADER_STATE_IN_TRADE if position else TRADER_STATE_WATCHING
        out["text"] = (f"Brain · In {position['symbol']}{_money(position['unrealized_pnl'])}" if position
                       else "Brain · Watching")
    return out


def _claude(out: dict[str, Any]) -> None:
    """Claude's seat says its state, stock, lane and note while its switch is On."""
    from agent_trader import view as seat_view

    try:
        seat = seat_view.status()
    except Exception:
        logger.warning("TRADERS: Claude's seat could not be read", exc_info=True)
        return
    line = seat.get("line") or {}
    out["symbol"] = seat.get("symbol")
    out["lane"] = {"symbol": line.get("symbol"), "depth": bool(line.get("depth")), "tape": bool(line.get("tape"))}
    out["note"] = seat.get("note")
    out["today"]["pnl"] = seat.get("today", {}).get("pnl", out["today"]["pnl"])
    out["today"]["loss_limit_usd"] = seat.get("today", {}).get("day_stop")
    if out["on"]:
        state = str(seat.get("state") or "")
        out["state"] = _SEAT_STATES.get(state, TRADER_STATE_WATCHING)
        out["done_for_today"] = state == "done"
        out["text"] = (str(seat.get("text") or "Claude") if seat.get("on")
                       else "Claude · On · waiting for its session")


def snapshot(now: float | None = None) -> dict[str, Any]:
    from traders import switches

    t = switches.now_ts() if now is None else float(now)
    state, error = switches.current(t)
    return {"schema_version": TRADERS_SCHEMA_VERSION, "generated_at": t, "venue": _venue(),
            "traders": {trader: trader_view(trader, state[trader], t) for trader in AI_TRADERS}, "error": error}
