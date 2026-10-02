"""The all-stop's day lock, per venue: no new buy there until the next 04:00 ET (spec D).

When a venue's all-stop trips (``bot.breakers``), new buys on **that** venue are refused until
the next 04:00 ET (``bot.clock``): Paper's all-stop locks Paper, Live's locks Live (#658 option
b). The lock lives in the venue's dial (``bot.venue_levels``): on the session row for the
desk's venue (``level_venue``), in ``venue_levels[VENUE]`` for the others, so switching away and
back does not escape it. Its fields:

- ``hard_lock_until_date`` -- when it lifts (ISO datetime; a legacy date lifts at its 00:00 ET);
- ``hard_lock_at`` -- the epoch second it tripped; ``hard_lock_pnl`` -- the day P&L that tripped
  it; ``hard_lock_usd`` -- the all-stop's line then.

``execution.service`` asks ``buy_refusal`` with the door's own venue for every place or bracket
from a non-protective source, manual and bot alike: a BUY, and a SELL that opens a short. Selling
what is held, cancels, Flatten and KILL are never locked. The bot and stock mode ask
``day_lock_active``. A session Nova cannot read counts as locked, stated: the all-stop's state is
unknown, never assumed clear.

The bot trip's record (``bot_trip_for``) is read here too, for the same readers: the latch
``soft_breaker_fired`` / ``soft_breaker_until`` (set by ``bot.autonomy.drop_to_eyes``) and
``soft_breaker_at`` / ``soft_breaker_pnl`` / ``soft_breaker_usd`` (set by ``bot.breakers``).

Owner: this module (the reads and the words; the breakers write the fields).
"""
from __future__ import annotations

import logging
from typing import Any

from bot.breaker_limits import venue_key
from bot.clock import clock_text, end_iso, lock_is_active, soft_latched, until_text
from constants_bot import BOT_BREAKER_VENUES, BOT_REASON_DAY_LOCK
from ibkr.safety import PROTECTIVE_SOURCES

logger = logging.getLogger(__name__)

_VENUE_NAMES = {"live": "Live", "paper": "Paper", "sim": "Sim"}
_STILL_WORKS = "Selling what you hold, cancels, Flatten and KILL still work."


def desk_venue() -> str | None:
    """The desk venue, or None when it cannot be read (logged)."""
    try:
        from sim.mode import venue

        return venue()
    except Exception:
        logger.warning("bot day lock: the desk venue is unreadable -- Live's lock applies", exc_info=True)
        return None


def dial_of(row: dict[str, Any], venue: str | None) -> dict[str, Any]:
    """The dial that holds ``venue``'s breaker fields: the row for the desk's own, else the stored one.

    A venue with no stored dial has none of its own (an empty dict: no lock, no trip).
    """
    key = venue_key(venue)
    here = row.get("level_venue")
    if here not in BOT_BREAKER_VENUES or here == key:
        return row
    stored = row.get("venue_levels")
    dial = stored.get(key) if isinstance(stored, dict) else None
    return dial if isinstance(dial, dict) else {}


def _money(value: Any) -> str | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value != value:
        return None
    text = f"{abs(float(value)):,.2f}"
    if text.endswith(".00"):
        text = text[:-3]
    return f"{'-' if value < 0 else ''}${text}"


def lock_text(lock: dict[str, Any]) -> str:
    """The plain words for an active day lock: whose all-stop, when, at what P&L, until when."""
    name = _VENUE_NAMES.get(str(lock.get("venue")), str(lock.get("venue")))
    if lock.get("error"):
        return (f"Nova could not read the bot session ({lock['error']}), so the all-stop's day lock "
                f"counts as on: new buys are refused until it reads again. {_STILL_WORKS}")
    when = clock_text(lock.get("tripped_at"))
    pnl, line = _money(lock.get("pnl")), _money(lock.get("threshold"))
    until = until_text(lock.get("until")) or "the next 04:00 ET"
    said = f"{name}'s all-stop tripped" + (f" at {when}" if when else "")
    if pnl:
        said += f" with the day at {pnl}"
    if line:
        said += f" (its line is {line})"
    return f"{said}: new buys on {name} are locked until {until}. {_STILL_WORKS}"


def lock_for(row: dict[str, Any], venue: str | None) -> dict[str, Any]:
    """``{active, until, tripped_at, pnl, venue, threshold, text}`` -- ``venue``'s day lock.

    ``until`` is one ISO datetime (a legacy date reads as its 00:00 ET); ``text`` is set while active.
    The trip's facts stay after the lock lifts, as the record of the last trip.
    """
    key = venue_key(venue)
    dial = dial_of(row, key)
    raw_until = dial.get("hard_lock_until_date")
    lock = {
        "active": lock_is_active(raw_until),
        "until": end_iso(raw_until),
        "tripped_at": dial.get("hard_lock_at"),
        "pnl": dial.get("hard_lock_pnl"),
        "threshold": dial.get("hard_lock_usd"),
        "venue": key,
    }
    if raw_until and lock["until"] is None:
        lock["until"] = str(raw_until)      # unreadable: shown as stored, and it counts as locked
    lock["text"] = lock_text(lock) if lock["active"] else None
    return lock


def day_locks(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every venue's day lock, ``{VENUE: lock_for(...)}``."""
    return {venue: lock_for(row, venue) for venue in BOT_BREAKER_VENUES}


def bot_trip_for(row: dict[str, Any], venue: str | None) -> dict[str, Any]:
    """``{fired, at, pnl, until, threshold, venue}`` -- ``venue``'s bot trip latch and its record."""
    key = venue_key(venue)
    dial = dial_of(row, key)
    return {
        "fired": soft_latched(dial),
        "at": dial.get("soft_breaker_at"),
        "pnl": dial.get("soft_breaker_pnl"),
        "until": end_iso(dial.get("soft_breaker_until")),
        "threshold": dial.get("soft_breaker_usd"),
        "venue": key,
    }


def day_lock(venue: str | None = None) -> dict[str, Any]:
    """``venue``'s day lock (None: the desk's), read from the session.

    A session Nova cannot read is a lock that counts as on, with ``error`` saying why.
    """
    key = venue_key(venue if venue is not None else desk_venue())
    try:
        from bot.persist import load_session

        row = load_session()
    except Exception as exc:
        logger.exception("bot day lock: the bot session is unreadable -- buys on %s count as locked", key)
        lock = {"active": True, "until": None, "tripped_at": None, "pnl": None, "threshold": None,
                "venue": key, "error": f"{type(exc).__name__}: {exc}"}
        lock["text"] = lock_text(lock)
        return lock
    return lock_for(row, key)


def day_lock_active(venue: str | None = None) -> bool:
    """True while ``venue``'s all-stop holds buys (None: the desk's venue)."""
    return bool(day_lock(venue)["active"])


def buy_refusal(
    side: str | None,
    source: str | None,
    venue: str | None = None,
    *,
    short_entry: bool = False,
) -> dict[str, Any] | None:
    """``{code, text, lock}`` when ``venue``'s day lock refuses this order, else None.

    It refuses what adds exposure: a BUY, or a SELL that opens a short. Protective sources
    (flatten / kill / cancel_working) are never refused.
    """
    opens = (side or "").upper() == "BUY" or ((side or "").upper() == "SELL" and short_entry)
    if not opens or source in PROTECTIVE_SOURCES:
        return None
    lock = day_lock(venue)
    if not lock["active"]:
        return None
    return {"code": BOT_REASON_DAY_LOCK, "text": lock["text"] or lock_text(lock), "lock": lock}


def buy_blocked(side: str | None, source: str | None, venue: str | None = None) -> tuple[bool, str | None]:
    """``(True, BOT_DAY_LOCK)`` while ``venue``'s day lock refuses a BUY from ``source``."""
    refusal = buy_refusal(side, source, venue)
    return (refusal is not None, refusal["code"] if refusal else None)
