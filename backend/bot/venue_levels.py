"""The bot's dial belongs to a venue (operator report 2026-09-30; ADR 042).

"When I switch between L0 and L2 in the paper, it stays persistent when I
switch to live, and I feel like that shouldn't happen." The session kept one
``level`` (and one ``setup_levels``), so a Strategy bot chosen on Paper was
Strategy on Live the moment the desk moved there. Now each venue keeps its own
dial, the way each keeps its own loss breakers (``bot.breaker_limits``):

- a dial is ``level`` (the master ceiling), ``setup_levels``, the sleeve
  (``caps``), the bot's stock list (``symbol_allowlist``), the bot trip's latch
  (``soft_breaker_*``), the all-stop's day lock (``hard_lock_*``) and the bot's
  orders and shares (``working`` / ``bot_qty``): a trip on Paper's P&L never
  silences Live's own bot trip, Paper's all-stop never locks Live's buys (nor
  the reverse), a Paper order never blocks or sizes a Live entry, and a Paper
  order id is never cancelled on Live;
- the session's fields are the dial of the venue named in ``level_venue``, so
  every reader of ``level`` keeps reading the desk's own;
- the other venues' dials wait in ``venue_levels: {VENUE: dial}``; a venue with
  none starts Off, every setup Off, the default sleeve, no stocks, no trip;
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

from constants_bot import BOT_BREAKER_VENUES, BOT_LEVEL_OFF

logger = logging.getLogger(__name__)

# The trip and lock fields a dial carries (written by ``bot.breakers``; read by ``bot.buy_lock``).
TRIP_FIELDS = ("soft_breaker_until", "soft_breaker_at", "soft_breaker_pnl", "soft_breaker_usd",
               "hard_lock_until_date", "hard_lock_at", "hard_lock_pnl", "hard_lock_usd")


def _dial(entry: Any) -> dict[str, Any]:
    """One venue's dial, normalized."""
    from bot.eligibility import normalize_symbols
    from bot.sleeve import normalize as normalize_caps

    entry = entry if isinstance(entry, dict) else {}
    try:
        lvl = int(entry.get("level") or BOT_LEVEL_OFF)
    except (TypeError, ValueError):
        lvl = BOT_LEVEL_OFF
    setups = entry.get("setup_levels")
    working = entry.get("working")
    qty = entry.get("bot_qty")
    out = {"level": lvl, "setup_levels": dict(setups) if isinstance(setups, dict) else {},
           "soft_breaker_fired": bool(entry.get("soft_breaker_fired")),
           "working": [dict(w) for w in working if isinstance(w, dict)] if isinstance(working, list) else [],
           "bot_qty": dict(qty) if isinstance(qty, dict) else {},
           "caps": normalize_caps(entry.get("caps")),
           "symbol_allowlist": normalize_symbols(entry.get("symbol_allowlist"))}
    for key in TRIP_FIELDS:
        out[key] = entry.get(key) if entry.get(key) not in ("", None) else None
    return out


def _stored(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = row.get("venue_levels")
    if not isinstance(raw, dict):
        return {}
    return {v: _dial(e) for v, e in raw.items() if v in BOT_BREAKER_VENUES and isinstance(e, dict)}


def dial_of(row: dict[str, Any], venue: str | None) -> dict[str, Any]:
    """The dial ``venue`` keeps: the session's own fields when it is the desk's, else its stored one
    (a venue with none: Off, the default sleeve, no stocks, no trip)."""
    if venue is not None and venue == row.get("level_venue"):
        return _dial(row)
    return _stored(row).get(str(venue)) or _dial(None)


def stored_raw(row: dict[str, Any], venue: str) -> dict[str, Any] | None:
    """The stored dial entry of another venue as it is in the row (for an edit in place), else None."""
    raw = row.get("venue_levels")
    if not isinstance(raw, dict) or not isinstance(raw.get(venue), dict):
        return None
    return raw[venue]


def put(row: dict[str, Any], venue: str, field: str, value: Any) -> None:
    """Set one field of ``venue``'s dial: the session's own when it is the desk's, else its stored one."""
    if venue == row.get("level_venue"):
        row[field] = value
        return
    stored = row.get("venue_levels") if isinstance(row.get("venue_levels"), dict) else {}
    entry = stored.get(venue) if isinstance(stored.get(venue), dict) else _dial(None)
    entry = dict(entry)
    entry[field] = value
    stored = dict(stored)
    stored[venue] = entry
    row["venue_levels"] = stored


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
    row["level_venue"] = new
    from bot.activation import deactivate

    deactivate(row, "venue", f"the desk moved from {held} to {new}: Activate never carries into another venue")
    return held


def by_venue(row: dict[str, Any]) -> dict[str, int]:
    """``{VENUE: level}`` for the Bots page: the desk's own and every other venue's."""
    return {v: dial_of(row, v)["level"] for v in BOT_BREAKER_VENUES}


def venue_changed(old: str | None, new: str) -> None:
    """``sim.mode.set_venue``: the desk moved from ``old`` to ``new``."""
    from bot.persist import load_session, save_session

    try:
        row = load_session()
        before = int(row.get("level") or BOT_LEVEL_OFF)
        from bot.arming import is_desk_active

        was_active = is_desk_active(row)
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


def migrate_v5(row: dict[str, Any], here: str, chosen: str | None) -> None:
    """Schema 4 -> 5 (ADR 042): the chosen setup's level, the sleeve, the bot list and the day lock
    move into every venue's dial. ``here`` is the venue the session's own fields belong to.

    - every dial: the old chosen setup takes the dial's level (``bot.setup_levels.migrate_chosen``);
    - the sleeve: today's one ``caps`` is copied to every venue (``allowlist`` becomes ``api_kinds``);
    - the bot list: today's list goes to Paper and Sim; Live's starts empty (Nova never buys on Live);
    - the day lock: today's one lock (if any) is copied to every venue -- a lock that held stays held
      everywhere until it lapses.
    """
    from bot.setup_levels import migrate_chosen

    row["level_venue"] = here
    caps = dict(row.get("caps") or {})
    if "allowlist" in caps and "api_kinds" not in caps:
        caps["api_kinds"] = caps.pop("allowlist")
    symbols = list(row.get("symbol_allowlist") or [])
    lock = {k: row.get(k) for k in ("hard_lock_until_date", "hard_lock_at", "hard_lock_pnl", "hard_lock_usd")}
    raw = row.get("venue_levels") if isinstance(row.get("venue_levels"), dict) else {}
    stored: dict[str, dict[str, Any]] = {}
    for venue in BOT_BREAKER_VENUES:
        if venue == here:
            continue
        entry = dict(raw.get(venue)) if isinstance(raw.get(venue), dict) else {"level": BOT_LEVEL_OFF}
        migrate_chosen(entry, chosen)
        entry.setdefault("caps", dict(caps))
        entry["symbol_allowlist"] = [] if venue == "live" else list(symbols)
        for key, value in lock.items():
            if entry.get(key) in (None, "") and value not in (None, ""):
                entry[key] = value
        stored[venue] = entry
    migrate_chosen(row, chosen)
    row["caps"] = caps
    row["symbol_allowlist"] = [] if here == "live" else symbols
    row["venue_levels"] = stored


def _audit(old: str, new: str, before: int, after: int, was_active: bool) -> None:
    from bot.audit import record

    try:
        record(action="venue", outcome=f"{old}->{new}",
               reason=(f"the desk moved to {new}: the bot takes {new}'s own level ({after}); "
                       f"{old} keeps {before}" + (" -- the bot stopped, Activate again" if was_active else "")),
               inputs={"from": old, "to": new, "level_before": before, "level_after": after,
                       "deactivated": was_active})
        if was_active:
            record(action="deactivate", outcome="ok", reason=f"the desk moved from {old} to {new}",
                   inputs={"reason": "venue", "from": old, "to": new})
    except Exception:
        logger.warning("bot audit: venue change not recorded", exc_info=True)
