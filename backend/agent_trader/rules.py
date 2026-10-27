"""Claude's own limits on an entry, checked before the execution door (ADR 068 decision 7).

The door's gates (venue, Freeze all orders, the Bots loss line, buying power, the arm latch) still apply after
these; this module adds what is Claude's alone and says every refusal in words. Pure over what it is handed, except
``entry_refusal``'s reads of the seat, the line, Paper and the view lock.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from agent_trader.constants_agent_trader import (
    AGENT_DAY_STOP_USD,
    AGENT_ENTRY_END_ET,
    AGENT_ENTRY_START_ET,
    AGENT_MAX_ENTRIES_A_DAY,
    AGENT_MAX_RISK_USD,
    AGENT_MAX_SHARES,
    AGENT_VENUE,
)


def shape_refusal(order: dict[str, Any]) -> str | None:
    """Why the order's own numbers break Claude's limits, or None. Long only; every entry carries its stop."""
    qty, entry, stop = order.get("qty"), order.get("entry"), order.get("stop")
    targets = [t for t in (order.get("target"), order.get("target2")) if t is not None]
    if not isinstance(qty, (int, float)) or qty <= 0 or int(qty) != qty:
        return "shares must be a whole number above 0"
    if qty > AGENT_MAX_SHARES:
        return f"{qty:g} shares is over Claude's {AGENT_MAX_SHARES:,} a trade"
    if not isinstance(entry, (int, float)) or entry <= 0:
        return "the entry price must be above 0"
    if not isinstance(stop, (int, float)) or stop <= 0:
        return "every entry carries a stop"
    if stop >= entry:
        return f"the stop {stop:g} must be under the entry {entry:g} (Claude is long only)"
    risk = (entry - stop) * qty
    if risk > AGENT_MAX_RISK_USD + 1e-6:
        return f"${risk:,.2f} between entry and stop is over Claude's ${AGENT_MAX_RISK_USD:,.0f} a trade"
    if not targets:
        return "an entry needs a target to sell into"
    if any(t <= entry for t in targets):
        return "every target must be above the entry"
    half = order.get("target1_qty")
    if order.get("target2") is not None and (not isinstance(half, (int, float)) or not 0 < half < qty):
        return "two targets need the first half's shares, fewer than the whole"
    trigger = order.get("trigger")
    if trigger is not None and not (isinstance(trigger, (int, float)) and 0 < trigger <= entry):
        return "a break's trigger must be above 0 and at or under its top price"
    return None


def window_refusal(now_et: datetime) -> str | None:
    if now_et.weekday() >= 5:
        return "Claude opens trades on weekdays only"
    hm = (now_et.hour, now_et.minute)
    if hm < AGENT_ENTRY_START_ET or hm >= AGENT_ENTRY_END_ET:
        return ("Claude opens trades from {:02d}:{:02d} to {:02d}:{:02d} ET only"
                .format(*AGENT_ENTRY_START_ET, *AGENT_ENTRY_END_ET))
    return None


def day_refusal(entries: int, pnl: float) -> str | None:
    if entries >= AGENT_MAX_ENTRIES_A_DAY:
        return f"Claude has opened {entries} of its {AGENT_MAX_ENTRIES_A_DAY} trades today"
    if pnl <= AGENT_DAY_STOP_USD:
        return f"Claude is done for today: ${pnl:,.2f} reached its ${AGENT_DAY_STOP_USD:,.0f} day stop"
    return None


def entry_refusal(order: dict[str, Any], *, pending_breaks: int = 0) -> tuple[str, str] | None:
    """``(code, text)`` when Claude may not open this trade now, else None. Reads the seat, its line, Paper and
    the backend's view lock (ADR 045: the feed, the IB loop, the symbol's Time & Sales)."""
    from agent_trader import ledger, lines, seat
    from agent_trader.constants_agent_trader import (
        AGENT_LIMIT,
        AGENT_NO_LINE,
        AGENT_NOT_MINE,
        AGENT_NOT_PAPER,
        AGENT_STALE,
        AGENT_YIELDED,
    )
    from market import now_et
    from market_view import gate
    from sim.mode import venue

    if seat.is_yielded():
        return AGENT_YIELDED, "the operator has Claude's line: no new trades until it is given back"
    if venue() != AGENT_VENUE:
        return AGENT_NOT_PAPER, f"the desk is on {venue()}: Claude opens trades only while it is on Paper"
    if (why := shape_refusal(order)) or (why := window_refusal(now_et())):
        return AGENT_LIMIT, why
    sym = str(order.get("symbol") or "").upper()
    if sym != (seat.symbol() or "") or not lines.holds_depth(sym):
        return AGENT_NO_LINE, f"Claude trades only the stock its Level 2 line is on ({seat.symbol() or 'none'})"
    try:
        if why := ledger.others_in(sym):
            return AGENT_NOT_MINE, why
        if why := day_refusal(ledger.entries_today() + pending_breaks, ledger.day_pnl()):
            return AGENT_LIMIT, why
    except ledger.ReadError as exc:
        return AGENT_STALE, str(exc)
    if lock := gate.desk_lock(sym):
        return AGENT_STALE, str(lock.get("reason") or lock.get("text") or "the market view lags")
    return None
