"""The breakers' one day boundary: 04:00 America/New_York (spec D, 2026-09-30).

The all-stop's day lock and the bot trip's latch lift at the next 04:00 ET, the practice day's
rollover. A lock written before this is a date and keeps its old meaning (its 00:00 ET).
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bot.clock import (
    clock_text,
    end_iso,
    lock_is_active,
    lock_until,
    lock_until_date,
    next_midnight_et,
    next_rollover_et,
    soft_latched,
    until_text,
)

ET = ZoneInfo("America/New_York")


def test_a_lock_tripped_in_the_day_lifts_at_the_next_4am():
    now = datetime(2026, 9, 17, 15, 30, tzinfo=ET)
    assert lock_until(now) == "2026-09-18T04:00:00-04:00"
    assert lock_until_date(now) == lock_until(now)          # the name every caller knows
    nxt = next_rollover_et(now)
    assert (nxt.date().isoformat(), nxt.hour) == ("2026-09-18", 4)


def test_a_lock_tripped_after_midnight_lifts_the_same_morning():
    """At 02:00 the practice day is still yesterday's: the lock lifts at today's 04:00."""
    now = datetime(2026, 9, 18, 2, 0, tzinfo=ET)
    assert lock_until(now) == "2026-09-18T04:00:00-04:00"
    exactly = datetime(2026, 9, 18, 4, 0, tzinfo=ET)
    assert lock_until(exactly) == "2026-09-19T04:00:00-04:00"


def test_the_lock_holds_through_midnight_until_4am():
    until = lock_until(datetime(2026, 9, 17, 15, 30, tzinfo=ET))
    assert lock_is_active(until, datetime(2026, 9, 17, 23, 59, tzinfo=ET)) is True
    assert lock_is_active(until, datetime(2026, 9, 18, 0, 30, tzinfo=ET)) is True     # the bug: it lifted here
    assert lock_is_active(until, datetime(2026, 9, 18, 3, 59, tzinfo=ET)) is True
    assert lock_is_active(until, datetime(2026, 9, 18, 4, 0, tzinfo=ET)) is False
    assert lock_is_active(None, datetime(2026, 9, 18, 4, 0, tzinfo=ET)) is False


def test_a_legacy_date_still_lifts_at_its_midnight():
    assert lock_is_active("2026-09-18", datetime(2026, 9, 17, 23, 59, tzinfo=ET)) is True
    assert lock_is_active("2026-09-18", datetime(2026, 9, 18, 0, 0, tzinfo=ET)) is False
    assert end_iso("2026-09-18") == "2026-09-18T00:00:00-04:00"
    assert next_midnight_et(datetime(2026, 9, 17, 15, 30, tzinfo=ET)).hour == 0


def test_an_unreadable_lock_counts_as_locked(caplog):
    assert lock_is_active("not a time", datetime(2026, 9, 18, 5, 0, tzinfo=ET)) is True
    assert "cannot be read" in caplog.text
    assert end_iso("not a time") is None


def test_dst_ends_still_lift_at_4am_wall_time():
    """1 Nov 2026: clocks fall back at 02:00 -- the lock still lifts at 04:00 on the wall."""
    now = datetime(2026, 10, 31, 15, 0, tzinfo=ET)
    assert lock_until(now) == "2026-11-01T04:00:00-05:00"


def test_the_bot_trip_latch_lapses_at_4am_too():
    row = {"soft_breaker_fired": True,
           "soft_breaker_until": lock_until(datetime(2026, 9, 17, 15, 30, tzinfo=ET))}
    assert soft_latched(row, datetime(2026, 9, 18, 1, 0, tzinfo=ET)) is True
    assert soft_latched(row, datetime(2026, 9, 18, 4, 0, tzinfo=ET)) is False
    assert soft_latched({"soft_breaker_fired": True}, datetime(2026, 9, 18, 1, 0, tzinfo=ET)) is False


def test_the_words():
    assert until_text("2026-10-01T04:00:00-04:00") == "04:00 ET Thu Oct 1"
    assert clock_text(datetime(2026, 9, 30, 10, 42, tzinfo=ET).timestamp()) == "10:42 ET"
    assert clock_text(None) is None and until_text(None) is None
