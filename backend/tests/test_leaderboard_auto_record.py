"""Auto-record: setups while an arming window is open, leaders 07:00-10:00 ET, free lines only, yields to
the operator (ADR 023, ADR 041)."""
from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from constants_ibkr import IBKR_MAX_DEPTH_SYMBOLS
from leaderboard import auto_record

ET = ZoneInfo("America/New_York")


def et(hh: int, mm: int, ss: int = 0) -> float:
    return datetime(2026, 9, 18, hh, mm, ss, tzinfo=ET).timestamp()


def gainer(symbol, change, price=5.0):
    return {"symbol": symbol, "price": price, "prev_close": price / (1 + change), "volume": 500_000}


class Det:
    def __init__(self, state):
        self.state = state


class Lane:
    """Stand-in for a template in play: its armed / near setups and its scored trades."""

    def __init__(self, near=(), armed=(), trades=()):
        self.det = {s: Det("near") for s in near} | {s: Det("armed") for s in armed}
        self.trades = set(trades)

    def watching(self):
        return set(self.det)

    def trade_symbols(self, now):
        return set(self.trades)


class Desk:
    """Stand-in for the depth lines, the recorder and the Session Record path."""

    def __init__(self):
        self.operator_lines: list[str] = []
        self.recording: list[str] = []
        self.gainers: list[dict] = []
        self.lanes: list[Lane] = []
        self.stops: list[tuple[str, str | None]] = []
        self.released: list[tuple[str, bool]] = []
        self.resuming: list[str] = []
        self.restarted: list[str] = []

    def busy(self):
        return sorted(set(self.operator_lines) | set(self.recording))


@pytest.fixture
def desk(monkeypatch, tmp_path):
    d = Desk()
    auto_record.reset_for_tests()
    from leaderboard import auto_record_state

    monkeypatch.setattr(auto_record_state, "path", lambda: tmp_path / "auto-record.json")
    monkeypatch.setattr(auto_record, "_resuming", lambda: list(d.resuming))
    monkeypatch.setattr(auto_record, "_restarted", lambda: list(d.restarted))
    monkeypatch.setattr(auto_record, "_busy_lines", d.busy)
    monkeypatch.setattr(auto_record, "_recording", lambda: list(d.recording))
    monkeypatch.setattr(auto_record, "_live_gainers", lambda: list(d.gainers))
    monkeypatch.setattr(auto_record, "_live_setup_lanes", lambda: list(d.lanes))
    from capture import feed_hold, keepalive, mode
    from ibkr import client

    async def acquire(symbol):
        return None

    async def release(symbol, at_once=False):
        d.released.append((symbol, at_once))

    def set_capture_mode(enabled, *, symbol=None, protect_active=False, reason=None):
        if enabled:
            if symbol not in d.recording:
                d.recording.append(symbol)
        else:
            d.stops.append((symbol, reason))
            if symbol in d.recording:
                d.recording.remove(symbol)
        return {"capture_symbols": list(d.recording)}

    monkeypatch.setattr(feed_hold, "acquire", acquire)
    monkeypatch.setattr(feed_hold, "release", release)
    monkeypatch.setattr(mode, "set_capture_mode", set_capture_mode)
    monkeypatch.setattr(keepalive, "operator_started", lambda s: None)
    monkeypatch.setattr(keepalive, "operator_stopped", lambda s: None)
    monkeypatch.setattr(client, "is_ready", lambda: True)
    yield d
    auto_record.reset_for_tests()


def run(coro):
    return asyncio.run(coro)


def test_records_the_leaders_on_free_lines_only(desk):
    desk.gainers = [gainer("AAA", 2.0), gainer("BBB", 1.5), gainer("CCC", 1.0), gainer("DDD", 0.5)]
    desk.operator_lines = ["OPR"]  # the operator already holds one Level 2 line
    run(auto_record.tick(et(7, 5)))
    assert desk.recording == ["AAA", "BBB"]  # two free lines, never the third
    assert auto_record.status(et(7, 5))["symbols"] == ["AAA", "BBB"]
    assert len(desk.busy()) == IBKR_MAX_DEPTH_SYMBOLS


def test_the_operator_opening_level_2_takes_back_the_lowest_ranked_auto_line(desk):
    desk.gainers = [gainer("AAA", 2.0), gainer("BBB", 1.5), gainer("CCC", 1.0)]
    run(auto_record.tick(et(7, 5)))
    assert desk.recording == ["AAA", "BBB", "CCC"]
    victim = run(auto_record.make_room_for("MINE"))
    assert victim == "CCC" and ("CCC", "auto") in desk.stops
    assert desk.recording == ["AAA", "BBB"]
    assert auto_record.status(et(7, 5))["yielded"] == ["CCC"]
    # A line it holds for the same symbol is shared, not yielded.
    assert run(auto_record.make_room_for("AAA")) is None


def test_the_operators_record_also_outranks_auto_record(desk):
    desk.gainers = [gainer("AAA", 2.0), gainer("BBB", 1.5), gainer("CCC", 1.0)]
    run(auto_record.tick(et(7, 5)))
    assert run(auto_record.make_room_for("MINE", for_record=True)) == "CCC"


def test_never_touches_a_recording_the_operator_started(desk):
    desk.recording = ["AAA"]  # the operator's own Record
    desk.gainers = [gainer("AAA", 2.0), gainer("BBB", 1.5)]
    run(auto_record.tick(et(7, 5)))
    assert auto_record.status(et(7, 5))["symbols"] == ["BBB"]
    run(auto_record.tick(et(10, 0)))  # window closed
    assert desk.recording == ["AAA"] and ("AAA", "auto") not in desk.stops


def test_the_operator_took_or_stopped_it_so_auto_record_lets_go(desk):
    desk.gainers = [gainer("AAA", 2.0), gainer("BBB", 1.5)]
    run(auto_record.tick(et(7, 5)))
    auto_record.operator_took("AAA")
    auto_record.operator_stopped("BBB", now=et(7, 6))
    desk.recording.remove("BBB")
    run(auto_record.tick(et(7, 7)))
    assert "BBB" not in desk.recording  # declined for the day
    run(auto_record.tick(et(10, 1)))
    assert "AAA" in desk.recording  # the operator's now; the window closing does not stop it


def test_rotates_only_to_a_leader_that_held_its_place(desk):
    desk.gainers = [gainer("AAA", 2.0), gainer("BBB", 1.5), gainer("CCC", 1.0)]
    run(auto_record.tick(et(7, 5)))
    desk.gainers = [gainer("NEW", 3.0), gainer("AAA", 2.0), gainer("BBB", 1.5), gainer("CCC", 1.0)]
    run(auto_record.tick(et(7, 6)))
    assert "NEW" not in desk.recording  # not held long enough yet
    run(auto_record.tick(et(7, 8, 30)))
    assert "NEW" in desk.recording and "CCC" not in desk.recording
    assert ("CCC", "auto") in desk.stops


def test_outside_the_window_or_disabled_it_records_nothing(desk, monkeypatch):
    desk.gainers = [gainer("AAA", 2.0)]
    run(auto_record.tick(et(6, 59)))
    assert desk.recording == []
    monkeypatch.setenv(auto_record.AUTO_RECORD_ENV, "0")
    run(auto_record.tick(et(7, 30)))
    assert desk.recording == [] and auto_record.status(et(7, 30))["active"] is False


def test_the_window_closing_stops_its_own_recordings_as_planned(desk):
    desk.gainers = [gainer("AAA", 2.0)]
    run(auto_record.tick(et(9, 59)))
    run(auto_record.tick(et(10, 0)))
    assert desk.recording == [] and desk.stops == [("AAA", "auto")]


def test_an_auto_stop_is_a_planned_gap_in_the_recording():
    from capture.segments import missing_seconds

    segments = [
        {"started_et": "2026-09-18T07:00:00-04:00", "stopped_et": "2026-09-18T07:10:00-04:00", "reason": "auto"},
        {"started_et": "2026-09-18T07:20:00-04:00", "stopped_et": "2026-09-18T07:30:00-04:00", "reason": "failure"},
        {"started_et": "2026-09-18T07:35:00-04:00", "stopped_et": "2026-09-18T07:40:00-04:00", "reason": "operator"},
    ]
    assert missing_seconds(segments) == 5 * 60  # only the gap after the failure


# -- setups first (ADR 040) ------------------------------------------------------


def test_setups_take_the_free_lines_before_the_leaders(desk):
    desk.gainers = [gainer("AAA", 2.0), gainer("BBB", 1.5), gainer("CCC", 1.0)]
    desk.lanes = [Lane(armed=["ARM"]), Lane(near=["NER"])]
    desk.operator_lines = ["OPR"]
    run(auto_record.tick(et(7, 5)))
    assert desk.recording == ["NER", "ARM"]  # near, then armed; no line left for a leader
    got = auto_record.status(et(7, 5))
    assert got["why"] == {"ARM": "armed", "NER": "near"}
    assert got["setups"] == [{"symbol": "NER", "why": "near"}, {"symbol": "ARM", "why": "armed"}]
    assert got["setups_error"] is None


def test_a_symbol_in_several_lanes_counts_at_its_best(desk):
    lanes = [Lane(armed=["XYZ"]), Lane(trades=["XYZ"]), Lane(near=["XYZ", "ABC"])]
    assert auto_record.pick_setups(lanes, et(7, 5)) == [("XYZ", "trade"), ("ABC", "near")]


def test_a_setup_takes_a_leaders_line_once_it_ran_a_minute_but_never_another_setups(desk):
    desk.gainers = [gainer("AAA", 2.0), gainer("BBB", 1.5), gainer("CCC", 1.0)]
    run(auto_record.tick(et(7, 5)))
    assert desk.recording == ["AAA", "BBB", "CCC"]
    auto_record._auto.update({s: et(7, 5) for s in desk.recording})
    desk.lanes = [Lane(armed=["SET"])]
    run(auto_record.tick(et(7, 5, 30)))
    assert "SET" not in desk.recording  # the leaders' lines opened 30 s ago
    run(auto_record.tick(et(7, 6, 5)))
    assert "SET" in desk.recording and "CCC" not in desk.recording  # the lowest leader gave way
    assert ("CCC", "auto") in desk.stops
    desk.lanes = [Lane(armed=["SET", "TWO", "THR", "FOU"])]
    auto_record._auto.update({s: et(7, 5) for s in auto_record._auto})
    run(auto_record.tick(et(7, 8)))
    # The two leaders gave way (armed setups in symbol order); a setup never takes another setup's line.
    assert set(desk.recording) == {"SET", "FOU", "THR"}
    assert "TWO" not in desk.recording


def test_the_operator_still_outranks_every_auto_line_and_a_leader_goes_first(desk):
    desk.gainers = [gainer("AAA", 2.0)]
    desk.lanes = [Lane(trades=["TRD"], near=["NER"])]
    run(auto_record.tick(et(7, 5)))
    assert desk.recording == ["TRD", "NER", "AAA"]
    assert run(auto_record.make_room_for("MINE")) == "AAA"
    desk.operator_lines = ["MINE"]
    assert run(auto_record.make_room_for("MIN2")) == "NER"


def test_a_trade_keeps_its_tape_past_the_windows_until_its_score_ends(desk):
    desk.gainers = [gainer("AAA", 2.0)]
    desk.lanes = [Lane(trades=["TRD"], armed=["ARM"])]
    run(auto_record.tick(et(9, 58)))
    assert set(desk.recording) == {"TRD", "ARM", "AAA"}
    run(auto_record.tick(et(10, 0)))
    assert desk.recording == ["TRD", "ARM"]  # the leaders' window closed; the setups' is open
    assert desk.stops == [("AAA", "auto")]
    run(auto_record.tick(et(15, 30)))     # the last arming window -- the 5-minute flat top's -- closed
    assert desk.recording == ["TRD"] and ("ARM", "auto") in desk.stops  # every arming window closed
    desk.lanes = [Lane()]  # its scoring window ended
    run(auto_record.tick(et(15, 42)))
    assert desk.recording == [] and ("TRD", "auto") in desk.stops


# -- the setups' window follows the arming windows (operator ask 2026-09-30) -----------------------


def test_after_ten_setups_still_get_lines_and_leaders_do_not(desk):
    desk.gainers = [gainer("AAA", 2.0), gainer("BBB", 1.5)]
    desk.lanes = [Lane(near=["R2G"])]
    run(auto_record.tick(et(10, 15)))
    assert desk.recording == ["R2G"]  # a trigger after 10:00 has its tape; no leader is taken
    got = auto_record.status(et(10, 15))
    assert got["active"] is True and got["leaders"] == [] and got["why"] == {"R2G": "near"}
    assert got["windows"]["open"] == "setups" and got["window"].startswith("setups only (setups 07:00-15:30 ET")
    assert got["windows"]["leaders"] == {"open": False, "start": "07:00", "end": "10:00"}
    by_setup = {w["setup"]: w for w in got["windows"]["setups"]["by_setup"]}
    assert by_setup["red_to_green"] == {"setup": "red_to_green", "start": "09:30", "end": "10:30", "open": True}
    assert by_setup["first_pullback"]["open"] is True


def test_the_leaders_window_closing_stops_only_lines_taken_for_leaders(desk):
    desk.gainers = [gainer("AAA", 2.0), gainer("BBB", 1.5)]
    desk.lanes = [Lane(armed=["SET"])]
    run(auto_record.tick(et(9, 50)))
    assert set(desk.recording) == {"SET", "AAA", "BBB"}
    desk.lanes = [Lane()]  # the setup failed: its name left both lists, like a leader that dropped off
    run(auto_record.tick(et(9, 55)))
    assert set(desk.recording) == {"SET", "AAA", "BBB"}  # a line that left is kept until it is needed
    run(auto_record.tick(et(10, 0)))
    assert desk.recording == ["SET"]  # the leaders' lines stop as planned; the setup's stays to 15:30
    assert set(desk.stops) == {("AAA", "auto"), ("BBB", "auto")}
    run(auto_record.tick(et(15, 30)))
    assert desk.recording == [] and ("SET", "auto") in desk.stops


def test_the_setups_window_is_the_template_in_plays_arming_window(desk):
    from setup_templates.store import get_store

    late = get_store().create("first_pullback", name="Late", values={"entry_cutoff": "16:00"})
    get_store().play("first_pullback", late.id)
    desk.lanes = [Lane(armed=["SET"])]
    run(auto_record.tick(et(15, 45)))      # past every pre-registered arming window (15:30 the latest)
    assert desk.recording == ["SET"]
    got = auto_record.status(et(15, 45))
    assert got["windows"]["setups"]["end"] == "16:00" and got["windows"]["open"] == "setups"
    run(auto_record.tick(et(16, 0)))
    assert desk.recording == []


def test_outside_both_windows_and_on_a_weekend_the_status_names_them(desk):
    got = auto_record.status(et(15, 45))
    assert got["active"] is False and got["windows"]["open"] == "none"
    assert got["window"] == "its windows (setups 07:00-15:30 ET, leaders 07:00-10:00 ET)"
    saturday = datetime(2026, 9, 19, 9, 0, tzinfo=ET).timestamp()
    assert auto_record.status(saturday)["windows"]["open"] == "none"
    both = auto_record.status(et(8, 0))
    assert both["windows"]["open"] == "setups_and_leaders" and both["window"].startswith("setups and leaders")


def test_unreadable_templates_fall_back_to_the_pre_registered_windows_and_say_so(desk, monkeypatch):
    from leaderboard import auto_record_windows

    def broken():
        raise RuntimeError("store locked")

    monkeypatch.setattr(auto_record_windows, "arming_windows", broken)
    desk.lanes = [Lane(near=["SET"])]
    run(auto_record.tick(et(10, 30)))
    got = auto_record.status(et(10, 30))
    assert desk.recording == ["SET"] and got["windows"]["setups"]["open"] is True
    assert "RuntimeError: store locked" in got["windows"]["setups"]["error"]
    assert "pre-registered" in got["windows"]["setups"]["error"]


def test_an_unreadable_setup_scanner_is_stated_and_the_leaders_still_record(desk, monkeypatch):
    def broken():
        raise RuntimeError("engine not started")

    monkeypatch.setattr(auto_record, "_live_setup_lanes", broken)
    desk.gainers = [gainer("AAA", 2.0)]
    run(auto_record.tick(et(7, 5)))
    got = auto_record.status(et(7, 5))
    assert desk.recording == ["AAA"]
    assert got["setups"] == [] and got["setups_error"] == "RuntimeError: engine not started"


# -- #698: the operator's Time & Sales, lines given back, and a restart ------------------------


def test_a_refused_time_and_sales_takes_back_the_lowest_ranked_auto_line_at_once(desk):
    desk.gainers = [gainer("AAA", 2.0), gainer("BBB", 1.5)]
    desk.operator_lines = ["MINE"]          # the tab already has its Level 2: Nova counts no line full
    run(auto_record.tick(et(7, 5)))
    assert desk.recording == ["AAA", "BBB"]
    assert run(auto_record.make_room_for("MINE")) is None   # Level 2 alone: nothing to give back
    # IBKR refused its Time & Sales for the tick-by-tick cap: the lines are full whatever Nova counts.
    assert run(auto_record.make_room_for("MINE", tape_refused=True)) == "BBB"
    assert ("BBB", "auto") in desk.stops
    assert ("BBB", True) in desk.released   # cancelled at once, never after the 16 s linger


def test_no_auto_start_takes_the_tick_by_tick_line_back_while_the_operators_tape_waits(desk, monkeypatch):
    up: set[str] = set()
    monkeypatch.setattr(auto_record, "_tape_up", lambda s: s in up)
    desk.gainers = [gainer("AAA", 2.0), gainer("BBB", 1.5)]
    run(auto_record.tick(et(7, 5)))
    assert run(auto_record.make_room_for("MINE", tape_refused=True)) == "BBB"
    desk.gainers.append(gainer("CCC", 1.2))  # a free depth line and a free slot: still not for auto-record
    run(auto_record.tick(et(7, 5, 15)))
    assert desk.recording == ["AAA"]
    up.add("MINE")                           # the operator's Time & Sales is back: free lines are free again
    run(auto_record.tick(et(7, 5, 30)))
    assert desk.recording == ["AAA", "BBB"]  # its best leader first


def test_a_line_given_back_is_not_taken_again_before_the_operators_subscribe_lands(desk):
    desk.gainers = [gainer("AAA", 2.0), gainer("BBB", 1.5), gainer("CCC", 1.0)]
    run(auto_record.tick(et(7, 5)))
    assert desk.recording == ["AAA", "BBB", "CCC"]
    assert run(auto_record.make_room_for("AIXI")) == "CCC"
    # AIXI's depth subscribe has not landed yet (2026-10-02: 6 s): the line stays the operator's.
    run(auto_record.tick(et(7, 5, 5)))
    assert desk.recording == ["AAA", "BBB"]
    desk.operator_lines = ["AIXI"]          # it landed
    run(auto_record.tick(et(7, 5, 10)))
    assert desk.recording == ["AAA", "BBB"]


def test_slots_a_restart_is_resuming_are_left_to_the_resumes(desk):
    desk.gainers = [gainer("AAA", 2.0), gainer("BBB", 1.5), gainer("CCC", 1.0)]
    desk.resuming = ["SSM", "SORA"]         # the keepalive is bringing these back
    run(auto_record.tick(et(7, 53)))
    assert desk.recording == ["AAA"]        # one slot of three; never the resumes'
    desk.recording.append("SSM")
    desk.resuming = ["SORA"]
    run(auto_record.tick(et(7, 54)))
    assert desk.recording == ["AAA", "SSM"]


def test_a_restart_gives_auto_record_back_its_own_recordings(desk, monkeypatch):
    from leaderboard import auto_record_state

    monkeypatch.setattr(auto_record_state, "today", lambda ts=None: "2026-09-18")
    desk.lanes = [Lane(near=["SSM"])]
    desk.gainers = [gainer("TNMG", 2.0)]
    run(auto_record.tick(et(7, 50)))
    assert desk.recording == ["SSM", "TNMG"]
    # The process restarts: memory is gone, the keepalive resumes both; the scanner is still seeding.
    auto_record.reset_for_tests()
    desk.lanes, desk.gainers = [], []
    run(auto_record.tick(et(7, 53, 41)))
    assert auto_record.held_symbols() == ["SSM", "TNMG"]    # its own again, so it can give them back
    assert run(auto_record.make_room_for("AMOD", tape_refused=True)) in ("SSM", "TNMG")


def test_a_symbol_the_operator_stopped_stays_declined_after_a_restart(desk, monkeypatch):
    from leaderboard import auto_record_state

    monkeypatch.setattr(auto_record_state, "today", lambda ts=None: "2026-09-18")
    desk.gainers = [gainer("AAA", 2.0)]
    run(auto_record.tick(et(7, 5)))

    async def record_route_stops_it():      # the Record route runs on the loop, which saves it
        auto_record.operator_stopped("AAA", now=et(7, 6))
        for _ in range(200):
            if auto_record_state.load("2026-09-18")[1] == ["AAA"]:
                return
            await asyncio.sleep(0.01)

    run(record_route_stops_it())
    desk.recording.remove("AAA")
    auto_record.reset_for_tests()
    run(auto_record.tick(et(7, 10)))
    assert desk.recording == []             # not taken again that day


def test_the_state_file_reads_empty_for_another_day_or_an_unknown_version(tmp_path):
    from leaderboard import auto_record_state

    path = tmp_path / "auto-record.json"
    auto_record_state.write("2026-09-18", {"SSM": {"since": 1.0, "why": "near"}}, ["AAA"], at=path)
    assert auto_record_state.load("2026-09-18", at=path) == ({"SSM": {"since": 1.0, "why": "near"}}, ["AAA"], [])
    assert auto_record_state.load("2026-09-19", at=path) == ({}, [], [])
    path.write_text('{"schema_version": 99, "date": "2026-09-18", "held": {"X": {}}}', encoding="utf-8")
    assert auto_record_state.load("2026-09-18", at=path) == ({}, [], [])
    path.write_text("not json", encoding="utf-8")
    assert auto_record_state.load("2026-09-18", at=path) == ({}, [], [])


def test_a_restart_with_no_owner_on_file_gives_the_recordings_to_auto_record(desk, monkeypatch):
    """2026-10-02 10:36: the process before never wrote auto-record.json, so SDEV, SSM and CELU read as
    the operator's and AZTA's Level 2 read "Symbol cap reached" for over an hour."""
    from leaderboard import auto_record_state

    monkeypatch.setattr(auto_record_state, "today", lambda ts=None: "2026-09-18")
    desk.recording = ["SDEV", "SSM", "CELU"]       # the keepalive brought them back
    desk.restarted = ["CELU", "SDEV", "SSM"]
    run(auto_record.tick(et(10, 36, 40)))
    assert auto_record.held_symbols() == ["CELU", "SDEV", "SSM"]
    assert run(auto_record.make_room_for("AZTA")) in ("CELU", "SDEV", "SSM")
    assert len(desk.recording) == 2


def test_a_recording_the_operator_started_stays_theirs_after_a_restart(desk, monkeypatch):
    from leaderboard import auto_record_state

    monkeypatch.setattr(auto_record_state, "today", lambda ts=None: "2026-09-18")

    async def operator_records():           # the Record route runs on the loop, which saves it
        desk.recording.append("MINE")
        auto_record.operator_took("MINE", now=et(9, 0))
        for _ in range(200):
            if auto_record_state.load("2026-09-18")[2] == ["MINE"]:
                return
            await asyncio.sleep(0.01)

    run(operator_records())
    auto_record.reset_for_tests()           # the process restarts; the keepalive resumes MINE
    desk.restarted = ["MINE"]
    run(auto_record.tick(et(9, 1)))
    assert auto_record.held_symbols() == []
    assert run(auto_record.make_room_for("AZTA")) is None
    assert desk.recording == ["MINE"]


def test_unknown_recordings_wait_while_a_resume_brings_them_back(desk, monkeypatch):
    from leaderboard import auto_record_state

    monkeypatch.setattr(auto_record_state, "today", lambda ts=None: "2026-09-18")
    desk.restarted, desk.resuming = ["SSM"], ["SSM"]
    run(auto_record.tick(et(10, 36, 30)))
    assert auto_record.held_symbols() == []
    desk.resuming, desk.recording = [], ["SSM"]
    run(auto_record.tick(et(10, 36, 40)))
    assert auto_record.held_symbols() == ["SSM"]
