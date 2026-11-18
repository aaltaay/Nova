"""The brain's own limits on an entry, checked before the execution door (ADR 072 decisions 7, 8, 10).

The door's gates still apply after these (the padlock, Freeze, the owners' rules and budget, the shared loss lines,
buying power). This module adds what is the brain's alone and says every refusal in words. ``shape_refusal`` and
``day_refusal`` are pure; ``entry_refusal`` reads the switch, the venue, the clock, the lane, Paper and the view lock.
"""
from __future__ import annotations

import logging
from typing import Any

from brain.constants_brain import (
    BRAIN_DAY_STOP,
    BRAIN_DAY_STOP_USD,
    BRAIN_HALTED,
    BRAIN_IN_TRADE,
    BRAIN_NO_LINE,
    BRAIN_NOT_PAPER,
    BRAIN_ORIGIN,
    BRAIN_PADLOCK,
    BRAIN_PADLOCK_TEXT,
    BRAIN_PAST_FLAT_BY,
    BRAIN_SHAPE,
    BRAIN_STALE,
    BRAIN_SWITCH_OFF,
    BRAIN_UNREAD_TEXT,
    BRAIN_VENUE,
)

logger = logging.getLogger(__name__)


def shape_refusal(order: dict[str, Any], limits: dict[str, Any]) -> str | None:
    """Why the order's own numbers break the brain's limits, or None. Long only; every entry carries its stop and a
    target, in one bracket."""
    qty, limit, stop, target = order.get("qty"), order.get("limit"), order.get("stop"), order.get("target")
    max_shares, risk_usd = int(limits["max_shares"]), float(limits["risk_usd"])
    if not isinstance(qty, (int, float)) or isinstance(qty, bool) or qty <= 0 or int(qty) != qty:
        return "shares must be a whole number above 0"
    if qty > max_shares:
        return f"{qty:g} shares is over the brain's {max_shares:,} a trade"
    if not isinstance(limit, (int, float)) or limit <= 0:
        return "the limit price must be above 0"
    if not isinstance(stop, (int, float)) or stop <= 0:
        return "every entry carries a stop"
    if stop >= limit:
        return f"the stop {stop:g} must be under the limit {limit:g} (the brain is long only)"
    risk = (limit - stop) * qty
    if risk > risk_usd + 1e-6:
        return f"${risk:,.2f} between entry and stop is over the brain's ${risk_usd:,.0f} a trade"
    if not isinstance(target, (int, float)) or target <= limit:
        return "an entry needs a target above its limit to sell into"
    return None


def day_refusal(pnl: float) -> str | None:
    """The brain's day stop (a code constant until its loss line lands, ADR 072 build order 4)."""
    if pnl <= BRAIN_DAY_STOP_USD:
        return f"The brain is done for today: ${pnl:,.2f} reached its ${BRAIN_DAY_STOP_USD:,.0f} day stop"
    return None


def past_flat_by(limits: dict[str, Any]) -> str | None:
    from market import now_et

    clock, flat_by = now_et(), str(limits["flat_by"])
    if clock.weekday() < 5 and clock.strftime("%H:%M") >= flat_by:
        return f"It is past the brain's flat-by time ({flat_by} ET): no new trade today"
    return None


def standing_refusal() -> tuple[str, str] | None:
    """``(code, text)`` when no entry of the brain's could go now, whatever its numbers: the switch, the venue, the
    clock, the day stop, Paper unread. ``GET /api/brain`` shows it as ``why_not``."""
    from brain import book
    from sim.mode import venue
    from traders import limits, switches

    if not switches.is_on(BRAIN_ORIGIN):
        return BRAIN_SWITCH_OFF, "The brain's switch is Off: no new trade until the operator switches it On"
    if venue() != BRAIN_VENUE:
        return BRAIN_NOT_PAPER, f"The desk is on {venue()}: the brain opens trades only while it is on Paper"
    from ibkr import safety

    if not safety.armed() and safety.locked_by() == "operator":
        return BRAIN_PADLOCK, BRAIN_PADLOCK_TEXT       # its arm would be refused: said here, never a silent block
    if why := past_flat_by(limits.of(BRAIN_ORIGIN)):
        return BRAIN_PAST_FLAT_BY, why
    try:
        if why := day_refusal(book.day_pnl()):
            return BRAIN_DAY_STOP, why
    except book.ReadError:
        logger.warning("BRAIN: Paper could not be read for the day stop", exc_info=True)
        return BRAIN_STALE, BRAIN_UNREAD_TEXT
    return None


def entry_refusal(order: dict[str, Any]) -> tuple[str, str] | None:
    """``(code, text)`` when the brain may not open this trade now, else None, in ``bot.md``'s order."""
    from agent_trader import halts
    from brain import book
    from line_lanes import brain as lane
    from line_lanes import lanes
    from market_view import gate
    from sim.mode import venue
    from traders import limits, switches

    if not switches.is_on(BRAIN_ORIGIN):
        return BRAIN_SWITCH_OFF, "The brain's switch is Off: no new trade until the operator switches it On"
    if venue() != BRAIN_VENUE:
        return BRAIN_NOT_PAPER, f"The desk is on {venue()}: the brain opens trades only while it is on Paper"
    mine = limits.of(BRAIN_ORIGIN)
    if why := shape_refusal(order, mine):
        return BRAIN_SHAPE, why
    if why := past_flat_by(mine):
        return BRAIN_PAST_FLAT_BY, why
    sym = str(order.get("symbol") or "").upper()
    if halts.halted(sym) is True:
        return BRAIN_HALTED, f"{sym} is halted: the brain opens no trade until it trades again"
    if not sym or sym != (lane.stock() or "") or not lanes.lines_up(sym)[lanes.DEPTH]:
        return BRAIN_NO_LINE, (f"The brain trades only the stock its Level 2 lane is on ({lane.stock() or 'none'}), "
                               "with its Level 2 up")
    try:
        held = book.positions(with_handed=True)
        resting = book.entries()
        if held or resting:
            where = next(iter(held), None) or str(resting[0].get("symbol") or "")
            return BRAIN_IN_TRADE, f"The brain is already in {where}: one position at a time"
        if why := day_refusal(book.day_pnl()):
            return BRAIN_DAY_STOP, why
    except book.ReadError:
        logger.warning("BRAIN entry: Paper could not be read", exc_info=True)
        return BRAIN_STALE, BRAIN_UNREAD_TEXT
    if lock := gate.desk_lock(sym):
        return BRAIN_STALE, str(lock.get("reason") or lock.get("text") or "the market view lags")
    return None
