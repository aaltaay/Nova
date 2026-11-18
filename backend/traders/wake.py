"""The brain turns itself On each trading morning (ADR 072 Amendment 2, ``traders.md`` "The switches").

The operator, 2026-11-17: "Make sure the brain wakes up by itself ... Make sure it's an auto turn-on, and if I turn
it off, it just keeps honoring its schedule."

On an exchange day, from 04:00 ET, Nova turns the brain's switch On once (``by: "schedule"``), at the first moment
On is not refused (``switches.on_refusal``: Live, its day stop, past its flat by) and nobody has set the switch that
desk day. A press of yours that day is the last word until the next morning: Off stays Off (an Off pressed while
it was already Off is recorded too), and the next exchange day's 04:00 ET wakes it again. A switches file Nova
cannot read, or of an unknown version, is never woken over: it may hold your Off, and its error stays on the pill. No weekend or holiday wakes it. ``NOVA_BRAIN_WAKES=0`` in ``.env`` ends the schedule:
the switch is then your press alone. Claude never wakes by itself.

No file of its own: the day's switch row (``trader-switches.json``, untouched reads ``at: null``) is the record.
Run by the brain's watcher (``brain.watcher``) every ``BRAIN_TICK_SEC``.
"""
from __future__ import annotations

import logging
import os

from constants_traders import TRADER_SWITCH_BY_SCHEDULE, TRADER_WAKES_ENV

logger = logging.getLogger(__name__)
_OFF_WORDS = ("0", "false", "off", "no")
WOKE_TEXT = "The brain turned itself On: it wakes each trading morning. Your Off holds until the next one."


def wakes(trader: str) -> bool:
    """``trader`` turns itself On each trading morning (the brain, unless ``.env`` says no)."""
    name = TRADER_WAKES_ENV.get(trader)
    return name is not None and os.environ.get(name, "").strip().lower() not in _OFF_WORDS


def due(trader: str, now: float | None = None) -> bool:
    """It is a trading day's desk day, ``trader``'s switch is untouched and Off, and On is not refused."""
    from traders import switches

    if not wakes(trader):
        return False
    t = switches.now_ts() if now is None else float(now)
    if switches.desk_day(t) != switches.et(t).date().isoformat():
        return False                    # before 04:00 ET, a weekend or a holiday: the desk day is an earlier date
    state, error = switches.current(t)
    if error is not None:
        return False                    # an unreadable or unknown-version file may hold your Off: no wake over it
    row = state[trader]
    if row["on"] or row["at"] is not None:
        return False
    return switches.on_refusal(trader, t) is None


def run_pass(now: float | None = None) -> list[str]:
    """Wake each trader that is due; returns the ones woken."""
    from traders import switches

    woken = []
    for trader in TRADER_WAKES_ENV:
        if not due(trader, now):
            continue
        if switches.turn_on_untouched(trader, TRADER_SWITCH_BY_SCHEDULE, now) is None:
            continue
        woken.append(trader)
        from brain import session

        session.event("switch_on", WOKE_TEXT, now=now)
    return woken
