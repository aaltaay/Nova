"""The loss limit's day walks back over weekends and NYSE holidays (#1090, ADR 056 amendment 2026-10-27).

Before, the loss limit turned at 04:00 ET every calendar day, so Saturday 04:00 cleared a Friday lock and
started the count at zero while the boards, Orders (Today) and Day P&L still read Friday. Its day is now the
trading session the rest of the desk uses (``market.session_key_et``): a Friday lock and count hold until the
next exchange day's 04:00 ET -- Monday, or Tuesday after a Monday holiday.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from loss_limit import gate, settings, state, watch
from practice.clock import session_day_start_ts

ET = ZoneInfo("America/New_York")


def et(year: int, month: int, day: int, hour: int, minute: int = 0) -> float:
    return datetime(year, month, day, hour, minute, tzinfo=ET).timestamp()


FRI_0932 = et(2026, 10, 16, 9, 32)        # the WETO morning's week (EDT throughout)
SAT_1000 = et(2026, 10, 17, 10)
SUN_2300 = et(2026, 10, 18, 23)
MON_0359 = et(2026, 10, 19, 3, 59)
MON_0400 = et(2026, 10, 19, 4)


@pytest.fixture(autouse=True)
def _fresh():
    settings.reset_for_tests()
    state.reset_for_tests()
    watch.reset_for_tests()
    yield
    settings.reset_for_tests()
    state.reset_for_tests()
    watch.reset_for_tests()


def _trip(now: float) -> None:
    state.write("paper", {"tripped_at": now, "tripped_loss": 451.03, "limit_usd": 405}, now)


# -- the day and when it ends ------------------------------------------------------------------------


def test_a_weekend_belongs_to_fridays_desk_day_and_monday_0400_begins_the_next():
    friday = ("2026-10-16", MON_0400)
    for now in (FRI_0932, SAT_1000, SUN_2300, MON_0359):
        assert state.desk_day(now) == friday
        assert state.until(now) == MON_0400
        assert state.day_start(now) == et(2026, 10, 16, 4)
    assert state.desk_day(MON_0400) == ("2026-10-19", et(2026, 10, 20, 4))
    assert state.day_start(MON_0400) == MON_0400


def test_weekdays_still_turn_at_0400_et():
    assert state.desk_day(et(2026, 10, 21, 3, 59)) == ("2026-10-20", et(2026, 10, 21, 4))
    assert state.desk_day(et(2026, 10, 21, 4)) == ("2026-10-21", et(2026, 10, 22, 4))
    assert state.desk_day(et(2026, 10, 22, 23, 59)) == ("2026-10-22", et(2026, 10, 23, 4))
    # Friday's day ends on Monday, not Saturday.
    assert state.desk_day(et(2026, 10, 23, 4)) == ("2026-10-23", et(2026, 10, 26, 4))


def test_the_day_is_the_one_the_rest_of_the_desk_shows():
    for now in (FRI_0932, SAT_1000, SUN_2300, MON_0359, MON_0400, et(2026, 9, 7, 12), et(2026, 11, 26, 12)):
        assert state.day_start(now) == session_day_start_ts(now)


def test_a_monday_holiday_holds_fridays_day_until_tuesday_0400():
    # Labor Day, Monday 2026-09-07.
    tuesday = et(2026, 9, 8, 4)
    for now in (et(2026, 9, 4, 15), et(2026, 9, 5, 10), et(2026, 9, 6, 23), et(2026, 9, 7, 10), et(2026, 9, 8, 3, 59)):
        assert state.desk_day(now) == ("2026-09-04", tuesday)
    assert state.desk_day(tuesday) == ("2026-09-08", et(2026, 9, 9, 4))


def test_a_midweek_holiday_belongs_to_the_day_before():
    # Thanksgiving, Thursday 2026-11-26.
    assert state.desk_day(et(2026, 11, 26, 12)) == ("2026-11-25", et(2026, 11, 27, 4))
    assert state.desk_day(et(2026, 11, 27, 4)) == ("2026-11-27", et(2026, 11, 30, 4))


def test_the_dst_weekend_ends_at_monday_0400_standard_time():
    # Clocks fall back on Sunday 2026-11-01: Friday 04:00 is EDT, Monday 04:00 is EST.
    monday = datetime(2026, 11, 2, 4, tzinfo=ET)
    assert monday.utcoffset().total_seconds() == -5 * 3600
    for now in (et(2026, 10, 30, 10), et(2026, 10, 31, 10), et(2026, 11, 1, 23)):
        assert state.desk_day(now) == ("2026-10-30", monday.timestamp())
    assert state.desk_day(monday.timestamp())[0] == "2026-11-02"


# -- a Friday lock ------------------------------------------------------------------------------------


def test_a_friday_lock_holds_through_the_weekend_and_clears_monday_0400():
    _trip(FRI_0932)
    for now in (SAT_1000, SUN_2300, MON_0359):
        assert state.record("paper", now)["tripped_at"] == FRI_0932
        stop = gate.stopped("paper", now, actor="you")
        assert stop is not None and stop["until"] == MON_0400
        assert "until 04:00 ET Mon Oct 19" in stop["text"]
    assert state.record("paper", MON_0400) == {}
    assert gate.stopped("paper", MON_0400, actor="you") is None


def test_a_friday_lock_saved_to_disk_survives_a_weekend_restart():
    _trip(FRI_0932)
    state.reset_for_tests()                                          # a restart on Sunday reads the file
    assert state.record("paper", SUN_2300)["tripped_loss"] == 451.03
    assert state.records(SUN_2300)[0] == "2026-10-16"
    state.reset_for_tests()
    assert state.record("paper", MON_0400) == {}


def test_a_friday_lock_holds_over_a_monday_holiday_until_tuesday_0400():
    friday = et(2026, 9, 4, 15)
    _trip(friday)
    assert state.record("paper", et(2026, 9, 7, 10))["tripped_at"] == friday
    assert state.record("paper", et(2026, 9, 8, 3, 59))["tripped_at"] == friday
    assert state.record("paper", et(2026, 9, 8, 4)) == {}


def test_a_weekday_lock_still_clears_at_the_next_0400():
    tuesday = et(2026, 10, 20, 9, 32)
    _trip(tuesday)
    assert state.record("paper", et(2026, 10, 21, 3, 59))["tripped_at"] == tuesday
    assert state.record("paper", et(2026, 10, 21, 4)) == {}
