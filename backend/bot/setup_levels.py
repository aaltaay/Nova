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

ADR 049 amendment (2026-10-13): research results never restrict a strategy's On or effective level.

#847: a watch-only setup (the pullback dip) is never On: ``apply`` refuses it (409 ``BOT_SETUP_WATCH_ONLY``) and
an On read from an older file reads as Eyes. Its Eyes draws it; it never proposes (``setup_scanner.lane_announce``).

ADR 072 (2026-11-13): the strategies only watch. Every setup with a scanner reads Eyes, whatever the session file
stored -- a stored Off or On reads as watching -- so nothing reads a setup at Strategy, and ``apply`` refuses
(410 ``BOT_STRATEGIES_WATCH``). The stored levels are left in the file, unread.

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
    BOT_REASON_STRATEGIES_WATCH,
    BOT_SCANNER_SETUPS,
    BOT_STRATEGIES_WATCH_TEXT,
    BOT_SETUPS_WITH_SCANNER,
    watch_only,
    watch_only_text,
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
    """``{SETUP: 1}`` for every setup with a scanner: every strategy watches (ADR 072), whatever is stored."""
    del row  # the stored levels are no longer read
    return {sid: BOT_LEVEL_EYES for sid in BOT_SCANNER_SETUPS}


def on_lock(setup: str) -> str | None:
    """Why a setup may not be On, else None: a watch-only setup (#847). Research never restricts On."""
    if watch_only(setup):
        return f"On is locked: {watch_only_text(setup)}"
    return None


def effective(row: dict[str, Any]) -> dict[str, int]:
    """``{SETUP: 1}``: every strategy watches, never above Eyes and never silenced (ADR 072)."""
    return own_levels(row)


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
    """``PATCH {setup_levels}``: refused (410 ``BOT_STRATEGIES_WATCH``) -- every strategy watches (ADR 072). An empty
    patch changes nothing."""
    del row
    if patch:
        raise BotError(BOT_STRATEGIES_WATCH_TEXT, 410, BOT_REASON_STRATEGIES_WATCH)
    return {}


def migrate_chosen(dial: dict[str, Any], chosen: str | None) -> None:
    """Schema 4 -> 5: the old chosen setup takes the dial's old level; the others keep 0 / 1."""
    raw = dial.get("setup_levels")
    levels = {k: v for k, v in raw.items() if k in BOT_SETUPS_WITH_SCANNER} if isinstance(raw, dict) else {}
    if chosen in BOT_SETUPS_WITH_SCANNER:
        levels[chosen] = master(dial)
    dial["setup_levels"] = {sid: _level(levels.get(sid)) or BOT_LEVEL_OFF for sid in BOT_SCANNER_SETUPS}
