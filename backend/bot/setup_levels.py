"""A level per setup (ADR 031, operator decisions A and B, 2026-09-24).

The chosen setup's level is the session's ``level`` (ADR 027: Off / Eyes /
Strategy; the localhost bot API reads it). Every other setup with a scanner
keeps its own in the session's ``setup_levels`` -- Off or Eyes, never
Strategy: one setup plays at a time. Off watches and scores in silence; Eyes
proposes. A setup missing from ``setup_levels`` is Off.

Owner: this module (the rules; the session file is ``bot.persist``'s).
"""
from __future__ import annotations

from typing import Any

from bot.errors import BotError
from constants_bot import (
    BOT_LEVEL_EYES,
    BOT_LEVEL_OFF,
    BOT_REASON_SETUP_LEVEL,
    BOT_SCANNER_SETUPS,
    BOT_SETUP_DEFAULT,
    BOT_SETUPS_WITH_SCANNER,
)


def _stored(row: dict[str, Any]) -> dict[str, int]:
    raw = row.get("setup_levels")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for sid, value in raw.items():
        try:
            level = int(value)
        except (TypeError, ValueError):
            continue
        if sid in BOT_SETUPS_WITH_SCANNER:
            out[sid] = BOT_LEVEL_EYES if level >= BOT_LEVEL_EYES else BOT_LEVEL_OFF
    return out


def levels_of(row: dict[str, Any]) -> dict[str, Any]:
    """``{"chosen": SETUP, "levels": {SETUP: 0 | 1 | 2}}`` for every setup with a scanner."""
    chosen = row.get("setup") or BOT_SETUP_DEFAULT
    level = int(row.get("level") or BOT_LEVEL_OFF)
    stored = _stored(row)
    levels = {sid: level if sid == chosen else stored.get(sid, BOT_LEVEL_OFF) for sid in BOT_SCANNER_SETUPS}
    return {"chosen": chosen, "levels": levels}


def apply(row: dict[str, Any], patch: Any) -> None:
    """``PATCH {setup_levels: {SETUP: 0 | 1}}``: a setup with a scanner other than the chosen one."""
    if not isinstance(patch, dict):
        raise BotError("setup_levels is an object of setup: level", 400, BOT_REASON_SETUP_LEVEL)
    chosen = row.get("setup") or BOT_SETUP_DEFAULT
    stored = _stored(row)
    for sid, value in patch.items():
        if sid not in BOT_SETUPS_WITH_SCANNER:
            raise BotError(f"{sid} has no scanner -- it has no level yet", 400, BOT_REASON_SETUP_LEVEL)
        if sid == chosen:
            raise BotError(f"{sid} is the chosen setup: its level is the bot's level", 400, BOT_REASON_SETUP_LEVEL)
        try:
            level = int(value)
        except (TypeError, ValueError):
            raise BotError(f"the level of {sid} is 0 (Off) or 1 (Eyes)", 400, BOT_REASON_SETUP_LEVEL) from None
        if level not in (BOT_LEVEL_OFF, BOT_LEVEL_EYES):
            raise BotError(f"only the chosen setup can be at Strategy -- {sid} is 0 (Off) or 1 (Eyes)", 400,
                           BOT_REASON_SETUP_LEVEL)
        stored[sid] = level
    row["setup_levels"] = stored


def on_choose(row: dict[str, Any], new: str) -> bool:
    """The chosen setup changes to ``new``: it takes the session's level, the old one keeps
    Eyes at most. Returns True when the change deactivates an active bot (a different
    setup is a new decision)."""
    old = row.get("setup") or BOT_SETUP_DEFAULT
    if new == old:
        return False
    level = int(row.get("level") or BOT_LEVEL_OFF)
    stored = _stored(row)
    if old in BOT_SETUPS_WITH_SCANNER:
        stored[old] = min(level, BOT_LEVEL_EYES)
    stored.pop(new, None)
    row["setup_levels"] = stored
    from bot.arming import is_desk_active

    return bool(is_desk_active(row))
