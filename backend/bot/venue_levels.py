"""The bot's level belongs to a venue (operator report 2026-09-30).

"When I switch between L0 and L2 in the paper, it stays persistent when I
switch to live, and I feel like that shouldn't happen." The session kept one
``level`` (and one ``setup_levels``), so a Strategy bot chosen on Paper was
Strategy on Live the moment the desk moved there. Now each venue keeps its own
dial, the way each keeps its own loss breakers (``bot.breaker_limits``):

- a dial is ``level``, ``setup_levels``, the bot trip's latch
  (``soft_breaker_fired`` / ``soft_breaker_until``) and the bot's orders and
  shares (``working`` / ``bot_qty``): a trip on Paper's P&L never silences
  Live's own bot trip, a Paper order never blocks or sizes a Live entry, and a
  Paper order id is never cancelled on Live;
- the session's fields are the dial of the venue named in ``level_venue``, so
  every reader of ``level`` keeps reading the desk's own;
- the other venues' dials wait in ``venue_levels: {VENUE: dial}``; a venue with
  none starts Off, every setup Off, its bot trip clear;
- a venue change (``sim.mode.set_venue``) puts the old venue's dial away,
  takes the new one's and deactivates the bot: Activate never carries into
  another venue, like spend arming (ADR 018). Coming back finds the old
  level, not active.

A session written before this has no ``level_venue``: its dial is the venue the
desk showed when it was last changed (the old venue on a switch, the current
one on a start). Owner: this module (the rules; the file is ``bot.persist``'s).
"""
from __future__ import annotations

import logging
from typing import Any

from constants_bot import BOT_BREAKER_VENUES, BOT_LEVEL_OFF, BOT_LEVEL_STRATEGY, BOT_STRATEGY_SMALL_CAP

logger = logging.getLogger(__name__)


def _dial(entry: Any) -> dict[str, Any]:
    """One venue's dial: its level, its setups' levels and its bot trip latch."""
    entry = entry if isinstance(entry, dict) else {}
    try:
        lvl = int(entry.get("level") or BOT_LEVEL_OFF)
    except (TypeError, ValueError):
        lvl = BOT_LEVEL_OFF
    setups = entry.get("setup_levels")
    until = entry.get("soft_breaker_until")
    working = entry.get("working")
    qty = entry.get("bot_qty")
    return {"level": lvl, "setup_levels": dict(setups) if isinstance(setups, dict) else {},
            "soft_breaker_fired": bool(entry.get("soft_breaker_fired")),
            "soft_breaker_until": str(until) if until else None,
            "working": [dict(w) for w in working if isinstance(w, dict)] if isinstance(working, list) else [],
            "bot_qty": dict(qty) if isinstance(qty, dict) else {}}


def _stored(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = row.get("venue_levels")
    if not isinstance(raw, dict):
        return {}
    return {v: _dial(e) for v, e in raw.items() if v in BOT_BREAKER_VENUES and isinstance(e, dict)}


def switch(row: dict[str, Any], new: str | None, *, owner: str | None = None) -> str | None:
    """Give ``row`` the dial of ``new``. ``owner`` names the venue an unstamped dial belongs
    to (default: ``new``). Returns the venue the dial came from when it changed, else None.
    Mutates ``row``; the caller saves it."""
    if new not in BOT_BREAKER_VENUES:
        return None                      # a venue Nova cannot read: leave the dial where it is
    held = row.get("level_venue")
    if held not in BOT_BREAKER_VENUES:
        held = owner if owner in BOT_BREAKER_VENUES else new
        row["level_venue"] = held
    if held == new:
        return None
    stored = _stored(row)
    stored[held] = _dial(row)
    mine = stored.pop(new, None) or _dial(None)
    row["venue_levels"] = stored
    row.update(mine)
    row["strategy"] = (row.get("strategy") or BOT_STRATEGY_SMALL_CAP) if mine["level"] >= BOT_LEVEL_STRATEGY else None
    row["level_venue"] = new
    from bot.arming import clear_arm_fields

    clear_arm_fields(row)
    return held


def by_venue(row: dict[str, Any]) -> dict[str, int]:
    """``{VENUE: level}`` for the Bots page: the desk's own and every other venue's."""
    stored = _stored(row)
    here = row.get("level_venue")
    out = {v: stored[v]["level"] if v in stored else BOT_LEVEL_OFF for v in BOT_BREAKER_VENUES}
    if here in BOT_BREAKER_VENUES:
        out[here] = _dial(row)["level"]
    return out


def venue_changed(old: str | None, new: str) -> None:
    """``sim.mode.set_venue``: the desk moved from ``old`` to ``new``."""
    from bot.persist import load_session, save_session

    try:
        row = load_session()
        before = int(row.get("level") or BOT_LEVEL_OFF)
        was_active = bool(row.get("armed"))
        stamp = row.get("level_venue")
        came_from = switch(row, new, owner=old)
        if came_from is None:
            if row.get("level_venue") != stamp:
                save_session(row)        # an old session's dial, stamped with its venue
            return
        save_session(row)
        _audit(came_from, new, before, int(row.get("level") or BOT_LEVEL_OFF), was_active)
    except Exception:
        # The venue still changes: an unreadable session file is the bot's to refuse
        # (``bot.persist``), never a reason to keep the desk on the old venue.
        logger.exception("bot: the level did not follow the venue change %s -> %s", old, new)


def _audit(old: str, new: str, before: int, after: int, was_active: bool) -> None:
    from bot.audit import record

    try:
        record(action="venue", outcome=f"{old}->{new}",
               reason=(f"the desk moved to {new}: the bot takes {new}'s own level ({after}); "
                       f"{old} keeps {before}" + (" -- the bot stopped, Activate again" if was_active else "")),
               inputs={"from": old, "to": new, "level_before": before, "level_after": after,
                       "deactivated": was_active})
    except Exception:
        logger.warning("bot audit: venue change not recorded", exc_info=True)
