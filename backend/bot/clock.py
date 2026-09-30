"""America/New_York clock for day-lock midnight unlock."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from constants_bot import BOT_TZ

_ET = ZoneInfo(BOT_TZ)


def now_et(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(_ET)
    if now.tzinfo is None:
        return now.replace(tzinfo=_ET)
    return now.astimezone(_ET)


def today_et(now: datetime | None = None) -> date:
    return now_et(now).date()


def next_midnight_et(now: datetime | None = None) -> datetime:
    current = now_et(now)
    tomorrow = current.date() + timedelta(days=1)
    return datetime.combine(tomorrow, time.min, tzinfo=_ET)


def lock_until_date(now: datetime | None = None) -> str:
    """ISO date of the next ET calendar day -- lock lifts at that midnight."""
    return str(next_midnight_et(now).date())


def lock_is_active(lock_until: str | None, now: datetime | None = None) -> bool:
    if not lock_until:
        return False
    return today_et(now).isoformat() < str(lock_until)


def soft_latched(row: dict, now: datetime | None = None) -> bool:
    """The bot trip fired today (ET) and has not been re-enabled.

    The latch keeps a tripped bot from flattening again and again the same day.
    It lapses at the next ET midnight, like the day lock: a latch left on from an
    earlier day silenced every later day's bot trip. One written before it carried
    its day (no ``soft_breaker_until``) has lapsed.
    """
    return bool(row.get("soft_breaker_fired")) and lock_is_active(row.get("soft_breaker_until"), now)
