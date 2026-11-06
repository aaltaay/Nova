"""The shape of a protective stop, one rule for Paper, Sim and Live (ADR 007, operator decision 2026-11-05).

IBKR's plain stop does not work outside regular hours; its stop-limit can. So a protective exit sent outside
regular hours is a stop-limit on every venue, its limit ``PROTECTIVE_STOP_LIMIT_FRACTION`` past the stop, and a plain
stop in regular hours. Pure over the venue's clock, which each send passes in. Owner of the limit's price; the venues
only carry it.
"""
from __future__ import annotations

from constants_practice import PROTECTIVE_STOP_LIMIT_FRACTION
from execution.models import ExecutionCommand
from short_sale.hours import regular_session

STOP = "STP"
STOP_LIMIT = "STP LMT"
STOP_TYPES = (STOP, STOP_LIMIT)


def limit_for(side: str, stop: float) -> float:
    """The limit of a stop-limit on ``side``: under a SELL stop, over a BUY stop. A penny tick from $1 up."""
    past = 1 - PROTECTIVE_STOP_LIMIT_FRACTION if side.upper() == "SELL" else 1 + PROTECTIVE_STOP_LIMIT_FRACTION
    return round(float(stop) * past, 2 if float(stop) >= 1 else 4)


def exit_limit(cmd: ExecutionCommand, now_ts: float) -> float | None:
    """The limit of the stop leg of a bracket or exit pair, or None for a plain stop.

    ``now_ts`` is the venue's clock. ``outside_rth`` is the order's permission to work outside regular hours, not the
    session: the ticket sets it from a saved preference, so a bracket sent at 10:00 with it on stays a plain stop.
    Without it a stop cannot work before the open, and from the open a plain stop is the better shape.
    """
    if not cmd.outside_rth or not cmd.stop_price or regular_session(now_ts):
        return None
    if cmd.operation == "bracket":
        return limit_for("BUY" if cmd.short_entry else "SELL", cmd.stop_price)
    return limit_for(cmd.side or "SELL", cmd.stop_price) if cmd.operation == "exit_oco" else None
