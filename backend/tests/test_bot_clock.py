"""America/New_York day-lock midnight unlock."""
from __future__ import annotations

from datetime import datetime

from bot.clock import lock_is_active, lock_until_date, next_midnight_et
from zoneinfo import ZoneInfo


def test_lock_until_is_next_et_calendar_day():
    now = datetime(2026, 9, 17, 15, 30, tzinfo=ZoneInfo("America/New_York"))
    assert lock_until_date(now) == "2026-09-18"
    nxt = next_midnight_et(now)
    assert nxt.hour == 0
    assert str(nxt.date()) == "2026-09-18"


def test_lock_active_until_that_midnight():
    now = datetime(2026, 9, 17, 23, 59, tzinfo=ZoneInfo("America/New_York"))
    assert lock_is_active("2026-09-18", now) is True
    after = datetime(2026, 9, 18, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    assert lock_is_active("2026-09-18", after) is False
    assert lock_is_active(None, now) is False
