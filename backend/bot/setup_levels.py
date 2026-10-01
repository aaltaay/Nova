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

Owner: this module (the rules; the session file is ``bot.persist``'s).
"""
from __future__ import annotations

from typing import Any

from bot.errors import BotError
from constants_bot import (
    BOT_LEVEL_EYES,
    BOT_LEVEL_OFF,
    BOT_LEVEL_STRATEGY,
    BOT_REASON_SETUP_LEVEL,
    BOT_SCANNER_SETUPS,
    BOT_SETUPS_WITH_SCANNER,
)

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


def effective(row: dict[str, Any]) -> dict[str, int]:
    """``{SETUP: min(master, own)}``: what each setup does on this venue now."""
    top = master(row)
    return {sid: min(top, lvl) for sid, lvl in own_levels(row).items()}


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
