"""The loss breakers' clock: one day boundary, 04:00 America/New_York (spec D, 2026-09-30).

The all-stop's day lock and the bot trip's latch lift at the next 04:00 ET -- the practice
day's rollover (``practice.clock``, ``PRACTICE_DAY_ROLLOVER_HOUR_ET``), when Paper's and Sim's
day P&L start again. They used to lift at midnight, so between 00:00 and 04:00 the breakers
read yesterday's practice day P&L, still past the line, and tripped again: a second flatten,
the bot to Off and a lock on the whole new day.

A lock's end is stored as an ISO datetime (``lock_until``). A value written before this is a
date ``YYYY-MM-DD`` and keeps its old meaning: it lifts at that date's 00:00 ET. A number is an
epoch second. A value that cannot be read counts as locked -- a latch Nova cannot read is never
assumed clear (the kill switch's rule) -- and says so in the log.

Owner: this module (the time rules; the fields live in each venue's dial, ``bot.venue_levels``).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from constants_bot import BOT_TZ
from constants_practice import PRACTICE_DAY_ROLLOVER_HOUR_ET

logger = logging.getLogger(__name__)

_ET = ZoneInfo(BOT_TZ)
_ROLLOVER = time(PRACTICE_DAY_ROLLOVER_HOUR_ET)
_now_for_tests: Callable[[], datetime] | None = None


def now_et(now: datetime | None = None) -> datetime:
    if now is None:
        if _now_for_tests is not None:
            return now_et(_now_for_tests())
        return datetime.now(_ET)
    if now.tzinfo is None:
        return now.replace(tzinfo=_ET)
    return now.astimezone(_ET)


def today_et(now: datetime | None = None) -> date:
    return now_et(now).date()


def now_ts() -> float:
    """The breakers' "now" as an epoch second (a trip's ``*_at`` stamp)."""
    return now_et().timestamp()


def next_midnight_et(now: datetime | None = None) -> datetime:
    current = now_et(now)
    tomorrow = current.date() + timedelta(days=1)
    return datetime.combine(tomorrow, time.min, tzinfo=_ET)


def next_rollover_et(now: datetime | None = None) -> datetime:
    """The next 04:00 ET strictly after ``now``: where a lock tripped now lifts."""
    current = now_et(now)
    today = datetime.combine(current.date(), _ROLLOVER, tzinfo=_ET)
    if today > current:
        return today
    return datetime.combine(current.date() + timedelta(days=1), _ROLLOVER, tzinfo=_ET)


def lock_until(now: datetime | None = None) -> str:
    """ISO datetime of the next 04:00 ET -- a lock or latch tripped now lifts then."""
    return next_rollover_et(now).isoformat()


# The name every caller knows; the value is a datetime now, no longer a date.
lock_until_date = lock_until


class LockUnreadable(ValueError):
    """A stored lock end Nova cannot read: the lock counts as on."""


def lock_end(value: Any) -> datetime | None:
    """When a stored lock lifts (ET), or None when there is no lock.

    Raises ``LockUnreadable`` for a value Nova cannot read.
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise LockUnreadable(f"lock end {value!r} is not a time")
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=_ET)
        except (OverflowError, OSError, ValueError) as exc:
            raise LockUnreadable(f"lock end {value!r} is not a time") from exc
    text = str(value).strip()
    try:
        if len(text) == 10:                     # legacy YYYY-MM-DD: lifts at that date's 00:00 ET
            return datetime.combine(date.fromisoformat(text), time.min, tzinfo=_ET)
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise LockUnreadable(f"lock end {text!r} is not a date or a time") from exc
    return parsed.replace(tzinfo=_ET) if parsed.tzinfo is None else parsed.astimezone(_ET)


def lock_is_active(lock_until: Any, now: datetime | None = None) -> bool:
    """True until the stored end has passed; an unreadable end counts as locked (logged)."""
    try:
        end = lock_end(lock_until)
    except LockUnreadable:
        logger.warning("bot clock: %r cannot be read as a lock end -- it counts as locked", lock_until)
        return True
    if end is None:
        return False
    return now_et(now) < end


def soft_latched(row: dict, now: datetime | None = None) -> bool:
    """The bot trip fired this practice day and has not been re-enabled.

    The latch keeps a tripped bot from flattening again and again the same day.
    It lapses at the next 04:00 ET, like the day lock: a latch left on from an
    earlier day silenced every later day's bot trip. One written before it carried
    its end (no ``soft_breaker_until``) has lapsed.
    """
    return bool(row.get("soft_breaker_fired")) and lock_is_active(row.get("soft_breaker_until"), now)


def end_iso(value: Any) -> str | None:
    """A stored lock end as one ISO datetime (a legacy date becomes its 00:00 ET); None when absent
    or unreadable."""
    try:
        end = lock_end(value)
    except LockUnreadable:
        return None
    return end.isoformat() if end is not None else None


def clock_text(epoch: Any) -> str | None:
    """``10:42 ET`` for an epoch second; None when there is none."""
    if not isinstance(epoch, (int, float)) or isinstance(epoch, bool):
        return None
    try:
        moment = datetime.fromtimestamp(float(epoch), tz=_ET)
    except (OverflowError, OSError, ValueError):  # maintainer: allow-swallow a time that is not one is told as none
        return None
    return f"{moment:%H:%M} ET"


def until_text(value: Any) -> str | None:
    """``04:00 ET Thu Oct 1`` for a stored lock end; None when absent or unreadable."""
    try:
        end = lock_end(value)
    except LockUnreadable:
        return None
    if end is None:
        return None
    return f"{end:%H:%M} ET {end:%a} {end:%b} {end.day}"


def set_clock_for_tests(fn: Callable[[], datetime] | None) -> None:
    """Pin "now" for the breakers' clock (None: the wall clock again)."""
    global _now_for_tests
    _now_for_tests = fn
