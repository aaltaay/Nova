"""The desk's per-day state rolls at Nova's 04:00 ET trading day, not at midnight (operator report, 2026-10-19).

From 00:00 to 04:00 ET the calendar date is already tomorrow's while the hot list, the day's P&L and the
scanner lists are still the day before's. The Setups board, the bot's daily entry count, the triggers audit
and auto-record's "declined today" list all keyed on the calendar date, so the Bots page showed 0 entries
next to yesterday's P&L, and a blank Setups board stamped with a date the rest of the screen had not reached.
Each test pins the clock at 00:30 ET and at 10:00 ET.
"""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bot import entry_rules, trigger_inputs
from bot.trigger_cells import restarts
from constants_eyes import EYES_SCHEMA_VERSION
from leaderboard import auto_record, auto_record_state
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


# -- 2. the daily entry count -------------------------------------------------------------------
def _entry(ts: float, stamp: str | None) -> dict:
    inputs = {"symbol": "AAA", "setup_type": "first_pullback", "setup_id": "A"}
    if stamp:
        inputs["venue_day"] = stamp
    return {"action": "buy_setup_limit", "outcome": "ok", "order_id": 1, "venue": "paper", "timestamp": ts,
            "inputs": inputs}


@pytest.mark.parametrize("stamp", [MON, None])           # a stamped line, and one written before the stamp
def test_the_daily_cap_is_still_mondays_until_four(stamp):
    rows = [_entry(at(MON, 9, 15), stamp)]
    small_hours = entry_rules.today("paper", datetime.fromtimestamp(at(TUE, 0, 30), ET), cap=1, rows=rows)
    assert small_hours["venue_day"] == MON and small_hours["count"] == 1      # was: 0 on a day with no date yet
    morning = entry_rules.today("paper", datetime.fromtimestamp(at(TUE, 10, 0), ET), cap=1, rows=rows)
    assert morning["venue_day"] == TUE and morning["count"] == 0


def test_an_unstamped_line_from_the_small_hours_counts_for_the_day_before():
    rows = [_entry(at(TUE, 0, 30), None)]
    assert entry_rules.today("paper", datetime.fromtimestamp(at(TUE, 3, 0), ET), cap=1, rows=rows)["count"] == 1
    assert entry_rules.today("paper", datetime.fromtimestamp(at(TUE, 10, 0), ET), cap=1, rows=rows)["count"] == 0


@pytest.mark.parametrize(("ts", "day"), [(at(TUE, 0, 30), MON), (at(TUE, 10, 0), TUE)])
def test_the_entry_stamp_and_auto_entrys_day_follow_the_venue_clock(ts, day):
    from stock_mode import runner

    entry_rules.set_clock_for_tests(lambda: datetime.fromtimestamp(ts, ET))
    try:
        assert entry_rules.venue_day() == day
        assert runner.venue_day() == day
    finally:
        entry_rules.set_clock_for_tests(None)


# -- 3. the triggers audit ----------------------------------------------------------------------
def _journal(lines: list[dict], day: str) -> None:
    from eyes.journal import journal_dir

    folder = journal_dir()
    folder.mkdir(parents=True, exist_ok=True)
    rows = [{"schema_version": EYES_SCHEMA_VERSION, "wall_ts": line["ts"], "date": day, "source": "live", **line}
            for line in lines]
    (folder / f"{day}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_a_days_triggers_table_starts_at_four_with_no_late_night_restart():
    day = "2026-09-30"
    lines = [
        {"ts": at(day, 2, 0), "event": "session", "symbol": None},                          # a restart at 02:00
        {"ts": at(day, 2, 10), "event": "triggered", "symbol": "AAA", "playing": True},     # D-1's, filed under D
        {"ts": at(day, 4, 0, 2), "event": "session", "symbol": None},                       # the 04:00 rollover
        {"ts": at(day, 9, 0), "event": "armed", "symbol": "BBB", "playing": True},
        {"ts": at(day, 9, 31), "event": "session", "symbol": None},                         # a real restart
    ]
    _journal(lines, day)
    assert trigger_inputs.day_start(day) == at(day, 4, 0)
    for today in (False, True):
        trigger_inputs.reset_for_tests()
        kept, source = trigger_inputs.journal(day, today=today)
        assert source["ok"]
        assert [k["ts"] for k in kept] == [at(day, 4, 0, 2), at(day, 9, 0), at(day, 9, 31)]
        assert restarts(kept, trigger_inputs.day_start(day)) == [at(day, 9, 31)]


# -- 4. auto-record's declined list -------------------------------------------------------------
def test_a_symbol_the_operator_stopped_stays_declined_until_four():
    auto_record.reset_for_tests()
    try:
        auto_record.operator_stopped("AAA", now=at(MON, 15, 0))
        declined_on = auto_record._declined["AAA"]
        assert declined_on == MON
        assert auto_record_state.today(at(TUE, 0, 30)) == declined_on           # still declined at 00:30
        assert auto_record_state.today(at(TUE, 10, 0)) != declined_on           # a new day lifts it
        auto_record.operator_stopped("BBB", now=at(TUE, 0, 30))
        assert auto_record._declined["BBB"] == MON                              # a small-hours stop is Monday's
    finally:
        auto_record.reset_for_tests()
