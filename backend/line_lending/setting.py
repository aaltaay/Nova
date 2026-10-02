"""Lending on or off: ``line_lending`` in bot-session.json (ADR 044 decision 6).

Desk-wide, not a venue's dial (``bot.venue_levels`` moves only the dial's own keys),
so the switch on the Bots page means the same on every venue. A session without
the key lends. The file is ``bot.persist``'s; this module reads and writes one key
through its helpers and never builds the session view.

A session that cannot be read lends nothing: unknown is never "on".
"""
from __future__ import annotations

import logging
from typing import Any

from line_lending.constants_line_lending import LINE_LENDING_DEFAULT_ON, LINE_LENDING_SETTING_KEY

logger = logging.getLogger(__name__)


def read(row: dict[str, Any]) -> bool:
    """The switch as a session row holds it; absent is the default (on)."""
    raw = row.get(LINE_LENDING_SETTING_KEY)
    return LINE_LENDING_DEFAULT_ON if raw is None else bool(raw)


def is_on() -> tuple[bool, str | None]:
    """``(on, error)``: off with the reason when the bot session cannot be read."""
    from bot.persist import load_session

    try:
        return read(load_session()), None
    except Exception as exc:
        logger.warning("line lending: the bot session could not be read -- no line is lent", exc_info=True)
        return False, f"the bot session could not be read ({type(exc).__name__}), so no line is lent"


def set_on(on: bool) -> bool:
    """Write the switch; returns what it was before."""
    from bot.persist import load_session, save_session

    row = load_session()
    before = read(row)
    row[LINE_LENDING_SETTING_KEY] = bool(on)
    save_session(row)
    return before
