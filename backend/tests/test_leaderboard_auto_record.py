"""Auto-record 07:00-10:00 ET: setups then leaders, free lines only, yields to the operator (ADR 023, ADR 040)."""
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

    def busy(self):
        return sorted(set(self.operator_lines) | set(self.recording))


@pytest.fixture
def desk(monkeypatch):
    d = Desk()
    auto_record.reset_for_tests()
    monkeypatch.setattr(auto_record, "_busy_lines", d.busy)
    monkeypatch.setattr(auto_record, "_recording", lambda: list(d.recording))
    monkeypatch.setattr(auto_record, "_live_gainers", lambda: list(d.gainers))
    monkeypatch.setattr(auto_record, "_live_setup_lanes", lambda: list(d.lanes))
    from capture import feed_hold, keepalive, mode
    from ibkr import client

    async def acquire(symbol):
        return None

    async def release(symbol):
        return None

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


def test_a_trade_keeps_its_tape_past_the_window_until_its_score_ends(desk):
    desk.gainers = [gainer("AAA", 2.0)]
    desk.lanes = [Lane(trades=["TRD"], armed=["ARM"])]
    run(auto_record.tick(et(9, 58)))
    assert set(desk.recording) == {"TRD", "ARM", "AAA"}
    run(auto_record.tick(et(10, 0)))
    assert desk.recording == ["TRD"]  # the armed setup and the leader stop as planned
    assert {("ARM", "auto"), ("AAA", "auto")} <= set(desk.stops)
    desk.lanes = [Lane()]  # its scoring window ended
    run(auto_record.tick(et(10, 12)))
    assert desk.recording == [] and ("TRD", "auto") in desk.stops


def test_an_unreadable_setup_scanner_is_stated_and_the_leaders_still_record(desk, monkeypatch):
    def broken():
        raise RuntimeError("engine not started")

    monkeypatch.setattr(auto_record, "_live_setup_lanes", broken)
    desk.gainers = [gainer("AAA", 2.0)]
    run(auto_record.tick(et(7, 5)))
    got = auto_record.status(et(7, 5))
    assert desk.recording == ["AAA"]
    assert got["setups"] == [] and got["setups_error"] == "RuntimeError: engine not started"
