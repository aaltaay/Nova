"""Auto-record 07:00-10:00 ET: free lines only, yields to the operator, never touches theirs (ADR 023)."""
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


class Desk:
    """Stand-in for the depth lines, the recorder and the Session Record path."""

    def __init__(self):
        self.operator_lines: list[str] = []
        self.recording: list[str] = []
        self.gainers: list[dict] = []
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
