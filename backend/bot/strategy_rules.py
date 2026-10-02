"""Each strategy's bot rules (ADR 044): the grades Nova buys and its setups a stock a day.

They are template parameters of the bot group (``setup_templates.catalogue``: changing them never
starts a read-out over), read from each setup's template in play -- the built-in's with the
operator's own bot rules on it (``setup_templates.store``). One rule, one wording, for Nova's bot
and Auto-entry (``bot.first_pullback.admit``) and the squares (``bot.trigger_audit``).

- **Grades**: ``bot_grades`` is ``AB`` (A and B, the default) or ``A`` (A only). C is never a
  trade: NOT A TRADE says so (``setup_scanner.trade_verdict``), so it is not said twice here. A
  grade Nova does not know is not bought.
- **Setups a day**: ``bot_setups_a_day`` is 1 (the default) or 2. A setup's number is its ``nth``
  (setups triggered on the stock that day, this one included); a trigger that carries none is the
  1st when its kind is the setup's first kind, else the 2nd.

A templates file the store refuses runs every setup's default, as the scanner does, and ``error``
says so; a store that cannot be read at all is said too, and then the strictest rules apply (A only,
the 1st of the day): Nova never buys on a rule it could not read. Owner: this module (no state).
"""
from __future__ import annotations

import logging
from typing import Any

from constants_bot import (
    BOT_GRADES_A,
    BOT_GRADES_AB,
    BOT_GRADES_DEFAULT,
    BOT_SETUP_FIRST_PULLBACK,
    BOT_SETUPS_A_DAY_DEFAULT,
    BOT_SETUPS_A_DAY_MAX,
)
from constants_setups import SETUP_KIND_FIRST_PULLBACK, SETUPS_GRADE_C, SETUPS_READOUT_KINDS

logger = logging.getLogger(__name__)
GRADES_WORDS = {BOT_GRADES_AB: "grade A and B", BOT_GRADES_A: "grade A only"}
UNREADABLE = "the template in play could not be read (the backend log has the error): the strictest rules apply"


def name(setup_type: str | None) -> str:
    return str(setup_type or BOT_SETUP_FIRST_PULLBACK).replace("_", " ")


def first_kind(setup_type: str) -> str:
    return SETUPS_READOUT_KINDS.get(setup_type, SETUP_KIND_FIRST_PULLBACK)


def grades_of(value: Any) -> str:
    return value if value in GRADES_WORDS else BOT_GRADES_DEFAULT


def per_day_of(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return BOT_SETUPS_A_DAY_DEFAULT
    return n if 1 <= n <= BOT_SETUPS_A_DAY_MAX else BOT_SETUPS_A_DAY_DEFAULT


def rules(setup_type: str) -> dict[str, Any]:
    """``{grades, setups_a_day, template: {id, rev, name} | None, error}`` -- the setup's template in play's."""
    try:
        from setup_templates.store import get_store

        store = get_store()
        t = store.in_play(setup_type)
        stored = store.error()          # an unreadable file: every setup runs its default, said
    except Exception:
        logger.warning("bot strategy rules: the %s template in play is unreadable -- A only, the 1st of the day",
                       setup_type, exc_info=True)
        return {"grades": BOT_GRADES_A, "setups_a_day": 1, "template": None, "error": UNREADABLE}
    values = t.values or {}
    return {"grades": grades_of(values.get("bot_grades")), "setups_a_day": per_day_of(values.get("bot_setups_a_day")),
            "template": {"id": t.id, "rev": t.rev, "name": t.name}, "error": stored}


def grade_block(grade: Any, grades: str) -> str | None:
    """Why a trigger graded ``grade`` is not bought under ``grades``, else None (C is NOT A TRADE's to say)."""
    g = str(grade).strip().upper() if grade else None
    if g == SETUPS_GRADE_C or (g is not None and g in grades):
        return None
    said = f"grade {g}" if g else "the grade is unknown"
    return f"{said}: this strategy buys {GRADES_WORDS.get(grades, GRADES_WORDS[BOT_GRADES_DEFAULT])}"


def number_of(setup: dict[str, Any] | None, setup_type: str) -> int:
    """The setup's number on its stock that day (its ``nth``); without one, from its kind."""
    setup = setup or {}
    nth = setup.get("nth")
    if isinstance(nth, (int, float)) and not isinstance(nth, bool) and nth >= 1:
        return int(nth)
    return 1 if setup.get("kind") == first_kind(setup_type) else 2


_SUFFIX = {1: "st", 2: "nd", 3: "rd"}


def ordinal(n: int) -> str:
    """``1st``, ``2nd``, ``3rd``, ``4th`` ... ``11th`` ... ``21st``."""
    suffix = "th" if 10 <= n % 100 <= 20 else _SUFFIX.get(n % 10, "th")
    return f"{n}{suffix}"


def nth_block(number: int, setups_a_day: int, setup_type: str) -> str | None:
    """Why the ``number``-th setup of a stock that day is not bought, else None."""
    if number <= setups_a_day:
        return None
    which = "the 1st" if setups_a_day <= 1 else "the 1st and 2nd"
    return f"a {ordinal(number)} {name(setup_type)}: this strategy buys {which} of the day only"
