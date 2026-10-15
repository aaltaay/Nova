"""The family keys (operator decisions 2026-10-15): one key per bot family, per practice venue, under the Bot switch.

A bot buys only while three keys are on: the Bot switch (``bot.switch``, the header's), its family's key (this
module: ``strategy`` -- the setup strategies' bot and Auto-entry -- or ``live_trader``, ADR 055) and its own key (a
strategy's On, a host's Bot key). With any of them off a bot places no order, not even a sell (operator decision
2026-10-15): what it holds waits until the keys are back on or the operator sells it, while what already rests at
the broker (a bracket's stop and target, a short's buy stop) still fills. ``hold`` is what every bot reads first.

Persisted: ``bot-keys.json`` in the operator cache (``BOT_KEYS_FILENAME``),
``{schema_version: 1, venues: {paper | sim: {strategy, live_trader, at}}}``. Owner: this module -- it reads the file
once and writes it through a temp file and a rename on every change. Invalidation: none by time, start or venue change
(a key is a setting, like a strategy's level; only the Bot switch never survives a start, ADR 042 B); a
``schema_version`` other than ``BOT_KEYS_SCHEMA_VERSION`` or a file that cannot be read is refused loud: every family
key reads off with the reason, and writes answer 409 ``BOT_KEYS_UNREADABLE`` instead of overwriting it. A venue or a
family the file does not hold reads ``BOT_KEY_DEFAULT_ON``. Live has no family keys: they read off. Shapes:
architecture/schema/bot.md ("The three keys").
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from bot.errors import BotError
from constants_bot import (
    BOT_AUDIT_ACTION_KEY,
    BOT_FAMILIES,
    BOT_FAMILY_NAMES,
    BOT_KEY_DEFAULT_ON,
    BOT_KEYS_FILENAME,
    BOT_KEYS_SCHEMA_VERSION,
    BOT_KEYS_VENUES,
    BOT_REASON_KEY_UNKNOWN,
    BOT_REASON_KEYS_UNREADABLE,
    BOT_REASON_LIVE_NOT_BUILT,
    BOT_REASON_VENUE_UNKNOWN,
    BOT_SKIP_FAMILY_OFF,
)

logger = logging.getLogger(__name__)
_PAGES = {"strategy": "Bots > Strategy Bots", "live_trader": "Bots > LiveTrader Bots"}
_LIVE_WHY = "bots never trade Live: the family keys are Paper's and Sim's"
_UNKNOWN_VENUE_WHY = "Nova cannot read the desk's venue, so every family key reads off"

_lock = threading.Lock()
_state: dict[str, Any] | None = None     # {"path", "venues": {venue: {family: bool, "at"}}}
_error: str | None = None


def reset_for_tests() -> None:
    global _state, _error
    with _lock:
        _state, _error = None, None


def _path() -> Path:
    from paths import cache_dir

    return cache_dir() / BOT_KEYS_FILENAME


def _load_locked() -> dict[str, Any]:
    global _state, _error
    path = _path()
    if _state is not None and _state["path"] == path:
        return _state
    _state, _error = {"path": path, "venues": {}}, None
    if not path.exists():
        return _state
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _error = f"{path.name} could not be read ({type(exc).__name__}): every family key reads off until it is fixed"
        logger.exception("bot keys: %s", _error)
        return _state
    if not isinstance(raw, dict) or raw.get("schema_version") != BOT_KEYS_SCHEMA_VERSION:
        version = raw.get("schema_version") if isinstance(raw, dict) else None
        _error = (f"{path.name} has schema_version {version!r}, not {BOT_KEYS_SCHEMA_VERSION}: refused, not "
                  "overwritten -- every family key reads off")
        logger.error("bot keys: %s", _error)
        return _state
    venues = raw.get("venues") if isinstance(raw.get("venues"), dict) else {}
    for venue in BOT_KEYS_VENUES:
        row = venues.get(venue)
        if isinstance(row, dict):
            _state["venues"][venue] = {**{f: row[f] for f in BOT_FAMILIES if isinstance(row.get(f), bool)},
                                       "at": row.get("at")}
    return _state


def _save_locked(state: dict[str, Any]) -> None:
    path = state["path"]
    payload = {"schema_version": BOT_KEYS_SCHEMA_VERSION, "venues": state["venues"]}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            logger.warning("bot keys: the temp file %s was not removed", tmp)
        raise


def desk_venue() -> str | None:
    """The desk venue, or None when it cannot be read (every family key then reads off)."""
    try:
        from sim.mode import venue

        return venue()
    except Exception:
        logger.warning("bot keys: the desk venue is unreadable -- every family key reads off", exc_info=True)
        return None


def error() -> str | None:
    with _lock:
        _load_locked()
        return _error


def _read(family: str, venue: str | None) -> tuple[bool, str | None]:
    """``(on, why_off)`` for ``family`` on ``venue``."""
    if venue is None:
        return False, _UNKNOWN_VENUE_WHY
    if venue not in BOT_KEYS_VENUES:
        return False, _LIVE_WHY
    with _lock:
        state = _load_locked()
        if _error is not None:
            return False, _error
        on = state["venues"].get(venue, {}).get(family, BOT_KEY_DEFAULT_ON)
    return bool(on), None if on else off_words(family)


def state(family: str, venue: str | None = None) -> tuple[bool, str | None]:
    """``(on, why_off)`` for ``family`` on ``venue`` (the desk's by default)."""
    return _read(family, desk_venue() if venue is None else venue)


def hold(family: str, venue: str | None = None, row: dict[str, Any] | None = None) -> tuple[str, str] | None:
    """``(code, why)`` while ``family``'s bots may place no order on ``venue`` -- the Bot switch off (it is the desk
    venue's: another venue's reads off), or the family's key off -- else None. Off places nothing, not even a sell
    (operator decision 2026-10-15); each bot's own key is the bot's to read."""
    from bot import switch
    from bot.persist import load_session
    from constants_bot import BOT_SKIP_NOT_ACTIVE

    desk = desk_venue()
    venue = desk if venue is None else venue
    if venue is None or venue != desk or not switch.is_on(load_session() if row is None else row):
        return BOT_SKIP_NOT_ACTIVE, "the Bot switch in the header is off: bots place no order, not even a sell"
    on, why = _read(family, venue)
    return None if on else (BOT_SKIP_FAMILY_OFF, f"{why}: its bots place no order, not even a sell")


def off_words(family: str) -> str:
    return f"the {BOT_FAMILY_NAMES[family]} key is off: turn it on at the top of {_PAGES[family]}"


def is_on(family: str, venue: str | None = None) -> bool:
    """Whether ``family``'s key is on, on ``venue`` (the desk's by default)."""
    return _read(family, desk_venue() if venue is None else venue)[0]


def block(family: str, venue: str | None = None) -> tuple[str, str] | None:
    """``(BOT_SKIP_FAMILY_OFF, why)`` while ``family``'s key is off, else None."""
    on, why = _read(family, desk_venue() if venue is None else venue)
    return None if on else (BOT_SKIP_FAMILY_OFF, str(why))


def view(venue: str | None) -> dict[str, Any]:
    """The session view's ``keys``: the desk venue's family keys."""
    out: dict[str, Any] = {"venue": venue, "error": error()}
    for family in BOT_FAMILIES:
        on, why = _read(family, venue)
        out[family] = {"on": on, "why_off": why}
    return out


def turn(family: str, on: bool) -> bool:
    """Turn ``family``'s key on or off on the desk venue. Returns whether it changed (the same state writes nothing);
    raises ``BotError`` on an unknown family, Live, an unreadable venue or an unreadable file."""
    if family not in BOT_FAMILIES:
        raise BotError(f"there is no {family!r} bot family (strategy or live_trader)", 400, BOT_REASON_KEY_UNKNOWN)
    venue = desk_venue()
    if venue is None:
        raise BotError(_UNKNOWN_VENUE_WHY, 409, BOT_REASON_VENUE_UNKNOWN)
    if venue not in BOT_KEYS_VENUES:
        raise BotError(_LIVE_WHY, 409, BOT_REASON_LIVE_NOT_BUILT)
    with _lock:
        state = _load_locked()
        if _error is not None:
            raise BotError(_error, 409, BOT_REASON_KEYS_UNREADABLE)
        row = state["venues"].setdefault(venue, {})
        before = bool(row.get(family, BOT_KEY_DEFAULT_ON))
        if before == bool(on):
            return False
        row[family], row["at"] = bool(on), round(time.time(), 3)
        try:
            _save_locked(state)
        except OSError as exc:
            row[family] = before
            raise BotError(f"{BOT_KEYS_FILENAME} could not be written ({type(exc).__name__}): the key is unchanged",
                           409, BOT_REASON_KEYS_UNREADABLE) from exc
    _audit(family, venue, bool(on))
    return True


def _audit(family: str, venue: str, on: bool) -> None:
    from bot.audit import record

    name = BOT_FAMILY_NAMES[family]
    said = (f"the {name} key is on: its bots may place orders again on {venue}" if on
            else f"the {name} key is off: its bots place no order on {venue}, not even a sell")
    try:
        record(action=BOT_AUDIT_ACTION_KEY, outcome="on" if on else "off", reason=said,
               inputs={"family": family, "venue": venue, "on": on})
    except Exception:
        logger.warning("bot audit: the %s key (%s) was not recorded", name, "on" if on else "off", exc_info=True)
