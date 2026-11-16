"""The desk's per-day state rolls at Nova's 04:00 ET trading day, not at midnight (operator report, 2026-10-19).

From 00:00 to 04:00 ET the calendar date is already tomorrow's while the hot list, the day's P&L and the
scanner lists are still the day before's. The Setups board and auto-record's "declined today" list keyed on
the calendar date, so a blank Setups board was stamped with a date the rest of the screen had not reached. (The
bot's daily entry count and the triggers audit retired with the bots, ADR 072.) Each test pins the clock at
00:30 ET and at 10:00 ET.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from line_lanes import recording
from market import session_bounds_of, session_key_for_ts
from setup_scanner.store import session_date
from tests.test_setup_scanner_row_per_trigger import armed_bars, make, run

ET = ZoneInfo("America/New_York")


def at(day: str, hour: int, minute: int, second: int = 0) -> float:
    y, m, d = (int(x) for x in day.split("-"))
    return datetime(y, m, d, hour, minute, second, tzinfo=ET).timestamp()


MON, TUE, FRI, SAT = "2026-10-19", "2026-10-20", "2026-10-16", "2026-10-17"


# -- the one key --------------------------------------------------------------------------------
@pytest.mark.parametrize(("ts", "day"), [
    (at(TUE, 0, 30), MON),                  # the small hours are still Monday's
    (at(TUE, 3, 59, 59), MON),
    (at(TUE, 4, 0), TUE),
    (at(TUE, 10, 0), TUE),
    (at(SAT, 10, 0), FRI),                  # a weekend has no day of its own (ADR 008, 2026-10-17)
    (at(MON, 0, 30), FRI),
])
def test_the_trading_day_rolls_at_four_not_at_midnight(ts, day):
    assert session_key_for_ts(ts) == day
    assert session_date(ts) == day


def test_the_window_of_a_trading_day_is_that_days_04_to_20():
    assert session_bounds_of(MON) == (at(MON, 4, 0), at(MON, 20, 0))
    assert session_bounds_of(SAT) is None


# -- 1. the Setups board ------------------------------------------------------------------------
def test_the_setups_board_keeps_the_days_lanes_until_four(tmp_path):
    journal: list[dict] = []
    eng, _clock = make(tmp_path / "setups.db", armed_bars(), journal)
    day = "2026-09-21"                                  # the fixture's Monday; the next Tuesday is 09-22
    next_day = "2026-09-22"
    run(eng, at(day, 9, 10))
    assert eng.session == day and eng.window == (at(day, 4, 0), at(day, 20, 0))
    held = len(eng.bars)
    assert held and eng.lanes

    run(eng, at(next_day, 0, 30))                       # the small hours: still the day's board
    assert eng.session == day
    assert eng.window == (at(day, 4, 0), at(day, 20, 0))
    assert len(eng.bars) == held
    assert len([e for e in journal if e.get("event") == "session"]) == 1       # no midnight "session" line

    run(eng, at(next_day, 10, 0))                       # past 04:00 the board starts the new day
    assert eng.session == next_day and eng.window == (at(next_day, 4, 0), at(next_day, 20, 0))
    assert len([e for e in journal if e.get("event") == "session"]) == 2


def test_the_board_holds_fridays_session_all_weekend(tmp_path):
    eng, _clock = make(tmp_path / "setups.db", armed_bars())
    run(eng, at("2026-09-25", 15, 0))                   # a Friday
    run(eng, at("2026-09-26", 10, 0))                   # Saturday 10:00
    assert eng.session == "2026-09-25" and eng.window == (at("2026-09-25", 4, 0), at("2026-09-25", 20, 0))


# -- 2. the lanes' recording: a stock the operator stopped stays declined -------------------------
def test_a_symbol_the_operator_stopped_stays_declined_until_four():
    recording.reset_for_tests()
    try:
        recording.operator_stopped("AAA", now=at(MON, 15, 0))
        declined_on = recording._declined["AAA"]
        assert declined_on == MON
        assert session_key_for_ts(at(TUE, 0, 30)) == declined_on                # still declined at 00:30
        assert session_key_for_ts(at(TUE, 10, 0)) != declined_on                # a new day lifts it
        recording.operator_stopped("BBB", now=at(TUE, 0, 30))
        assert recording._declined["BBB"] == MON                                # a small-hours stop is Monday's
    finally:
        recording.reset_for_tests()
