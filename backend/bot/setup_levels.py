"""The bot's levels: a master ceiling and a level per setup (ADR 031, ADR 042).

ADR 042 retired the "chosen" setup. The session's ``level`` (each venue's own,
``bot.venue_levels``) is the **master ceiling**: the most any setup may do on this
venue -- Off (0), Eyes (1) or Strategy (2); the localhost bot API reads it. Every
setup with a scanner keeps its own level in ``setup_levels`` (0..2; a setup missing
from it is Off). A setup's **effective** level is ``min(master, its own)``:

- Off watches and scores in silence;
- Eyes proposes on near + go;
- Strategy lets Nova's bot trade its go triggers -- only while the bot is Active
  (``bot.activation``); while it is not, a Strategy setup proposes like Eyes.

ADR 049: a short setup is On (Strategy) only once its five-year test passed on the rules in play
(``setup_scanner.short_tests``): ``apply`` refuses On before that (409 ``BOT_SHORT_TEST``), and a short at On
whose test stops matching -- its template edited, the result replaced -- reads as Eyes.

Owner: this module (the rules; the session file is ``bot.persist``'s).
"""
from __future__ import annotations

import logging
from typing import Any

from bot.errors import BotError
from constants_bot import (
    BOT_LEVEL_EYES,
    BOT_LEVEL_OFF,
    BOT_LEVEL_STRATEGY,
    BOT_REASON_SETUP_LEVEL,
    BOT_REASON_SHORT_TEST,
    BOT_SCANNER_SETUPS,
    BOT_SETUPS_WITH_SCANNER,
    SIDE_SHORT,
    setup_side,
)

logger = logging.getLogger(__name__)
LEVEL_NAMES = {BOT_LEVEL_OFF: "Off", BOT_LEVEL_EYES: "Eyes", BOT_LEVEL_STRATEGY: "Strategy"}


def _level(value: Any) -> int | None:
    try:
        level = int(value)
    except (TypeError, ValueError):
        return None
    return level if level in LEVEL_NAMES else None


def master(row: dict[str, Any]) -> int:
    """The master ceiling: the session's (this venue's) ``level``."""
    return _level(row.get("level")) or BOT_LEVEL_OFF


def own_levels(row: dict[str, Any]) -> dict[str, int]:
    """``{SETUP: 0 | 1 | 2}`` for every setup with a scanner; a missing or unreadable one is Off."""
    raw = row.get("setup_levels")
    raw = raw if isinstance(raw, dict) else {}
    return {sid: _level(raw.get(sid)) or BOT_LEVEL_OFF for sid in BOT_SCANNER_SETUPS}


def short_lock(setup: str) -> str | None:
    """Why a short setup may not be On (ADR 049): its five-year test has not passed on the rules in play. None
    for a long setup. A test or a template Nova cannot read keeps it locked, and says so."""
    if setup_side(setup) != SIDE_SHORT:
        return None
    try:
        from setup_scanner import short_tests
        from setup_templates.store import get_store

        return short_tests.lock(setup, get_store().in_play(setup).fingerprint)
    except Exception as exc:
        logger.warning("bot: %s's five-year test could not be read -- On stays locked", setup, exc_info=True)
        return f"On waits on the {name(setup)} five-year test, which could not be read ({exc})"


def effective(row: dict[str, Any]) -> dict[str, int]:
    """``{SETUP: min(master, own)}``: what each setup does on this venue now. A short setup at On whose test no
    longer passes on the rules in play reads as Eyes (ADR 049)."""
    top = master(row)
    out = {sid: min(top, lvl) for sid, lvl in own_levels(row).items()}
    for sid, lvl in out.items():
        if lvl >= BOT_LEVEL_STRATEGY and short_lock(sid):
            out[sid] = BOT_LEVEL_EYES
    return out


def at_strategy(row: dict[str, Any]) -> list[str]:
    """The setups at effective Strategy, in the playbook's order."""
    return [sid for sid, lvl in effective(row).items() if lvl >= BOT_LEVEL_STRATEGY]


def levels_of(row: dict[str, Any]) -> dict[str, Any]:
    """``{"chosen": None, "levels": effective, "own": own, "master": level}`` (ADR 042).

    ``levels`` is each setup's effective level -- what the setup scanner's proposing, the
    board and the stock read act on. ``chosen`` stays in the shape for its readers and is
    always None: no setup is chosen any more.
    """
    return {"chosen": None, "levels": effective(row), "own": own_levels(row), "master": master(row)}


def name(setup: str | None) -> str:
    return str(setup or "setup").replace("_", " ")


def apply(row: dict[str, Any], patch: Any) -> dict[str, tuple[int, int]]:
    """``PATCH {setup_levels: {SETUP: 0 | 1 | 2}}`` for setups with a scanner.

    Returns ``{SETUP: (before, after)}`` for each own level that changed; raises
    ``BotError`` (400 ``BOT_SETUP_LEVEL``) and changes nothing on any bad entry.
    """
    if not isinstance(patch, dict):
        raise BotError("setup_levels is an object of setup: level", 400, BOT_REASON_SETUP_LEVEL)
    before = own_levels(row)
    after = dict(before)
    for sid, value in patch.items():
        if sid not in BOT_SETUPS_WITH_SCANNER:
            raise BotError(f"{name(sid)} has no scanner -- it has no level yet", 400, BOT_REASON_SETUP_LEVEL)
        level = _level(value)
        if level is None:
            raise BotError(f"the level of {name(sid)} is 0 (Off), 1 (Eyes) or 2 (Strategy)", 400,
                           BOT_REASON_SETUP_LEVEL)
        if level >= BOT_LEVEL_STRATEGY and before.get(sid, BOT_LEVEL_OFF) < BOT_LEVEL_STRATEGY:
            locked = short_lock(sid)
            if locked:
                raise BotError(locked, 409, BOT_REASON_SHORT_TEST)
        after[sid] = level
    row["setup_levels"] = after
    return {sid: (before[sid], after[sid]) for sid in after if after[sid] != before[sid]}


def migrate_chosen(dial: dict[str, Any], chosen: str | None) -> None:
    """Schema 4 -> 5: the old chosen setup takes the dial's old level; the others keep 0 / 1."""
    raw = dial.get("setup_levels")
    levels = {k: v for k, v in raw.items() if k in BOT_SETUPS_WITH_SCANNER} if isinstance(raw, dict) else {}
    if chosen in BOT_SETUPS_WITH_SCANNER:
        levels[chosen] = master(dial)
    dial["setup_levels"] = {sid: _level(levels.get(sid)) or BOT_LEVEL_OFF for sid in BOT_SCANNER_SETUPS}
