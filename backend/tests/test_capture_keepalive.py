"""Resume, then say so: a Session Record gets back up on its own (operator decision, 2026-09-21).

The market only happens once. A restart, a recorder failure or a lost IBKR line
must cost a gap, not the rest of the session -- bounded, never across a day,
never onto another symbol, cancelled by the operator's own Stop -- and with up
to three symbols recording, one dying must not touch the others.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from capture import keepalive
from capture.constants_capture import (
    CAPTURE_KEEPALIVE_INTERVAL_SEC,
    CAPTURE_RESUME_BACKOFF_SEC,
    CAPTURE_RESUME_MAX_ATTEMPTS,
    CAPTURE_RESUME_RESTART_WINDOW_SEC,
    CAPTURE_STOP_FAILURE,
    CAPTURE_STOP_RESTART,
)

ET = ZoneInfo("America/New_York")
# A weekday noon, Eastern, well inside one session day.
NOON = datetime(2026, 9, 21, 12, 0, tzinfo=ET).timestamp()


class Desk:
    """Fakes for the four things a tick touches; records what it asked for."""

    def __init__(self, *, ready=True, acquire_error=None, start_ok=True):
        self.ready_flag, self.acquire_error, self.start_ok = ready, acquire_error, start_ok
        self.acquired, self.released, self.started = [], [], []
        self.recording: list[str] = []
        self.producer_state: dict[str, str] = {}
        self.errors: dict[str, str | None] = {}

    def ready(self) -> bool:
        return self.ready_flag

    async def acquire(self, symbol):
        self.acquired.append(symbol)
        return self.acquire_error

    async def release(self, symbol):
        self.released.append(symbol)

    async def start(self, symbol):
        self.started.append(symbol)
        if self.start_ok:
            if symbol not in self.recording:
                self.recording.append(symbol)
            return {"capture": True, "capture_symbol": self.recording[0], "capture_symbols": list(self.recording)}
        return {"capture": False, "error": "Recorder start failed"}

    def payload(self):
        return {
            "capture": bool(self.recording),
            "capture_symbol": self.recording[0] if self.recording else None,
            "capture_symbols": list(self.recording),
            "sessions": {sym: {"producer": {"state": self.producer_state.get(sym, "receiving")}}
                         for sym in self.recording},
            "error": next((e for e in self.errors.values() if e), None),
        }

    def recorder(self):
        def one(sym):
            return {"symbol": sym, "session_date": "2026-09-21", "dir": f"F:/x/2026-09-21/{sym}",
                    "counts": {"prints": 2439}, "error": self.errors.get(sym),
                    "started_et": "2026-09-21T11:46:35-04:00", "segment_started_et": "2026-09-21T11:46:35-04:00",
                    "segment": 1, "last_write_ts": NOON - 1}
        known = set(self.recording) | set(self.errors)
        primary = self.recording[0] if self.recording else (next(iter(known)) if known else "GRML")
        return {**one(primary), "sessions": {sym: one(sym) for sym in known}}

    def tick(self, now):
        asyncio.run(keepalive.tick(now=now, payload=self.payload(), recorder_status=self.recorder(),
                                   ready=self.ready, acquire=self.acquire, release=self.release,
                                   start=self.start))


def fields(desk: Desk):
    return keepalive.status_fields(desk.recorder(), list(desk.recording))


def resume_of(desk: Desk, symbol: str):
    return next((r for r in fields(desk)["capture_resume"] if r["symbol"] == symbol), None)


def stopped_of(desk: Desk, symbol: str):
    return next((r for r in fields(desk)["capture_stopped"] if r["symbol"] == symbol), None)


@pytest.fixture(autouse=True)
def fresh():
    keepalive.reset_for_tests()
    yield
    keepalive.reset_for_tests()


def test_a_recording_that_dies_is_shouted_about_and_resumed():
    desk = Desk()
    desk.recording = ["GRML"]
    desk.tick(NOON)                                    # watched
    desk.recording, desk.errors = [], {"GRML": "Capture writer backlog full"}
    desk.tick(NOON + 5)                                # gone, and the operator did not stop it
    stopped, resume = stopped_of(desk, "GRML"), resume_of(desk, "GRML")
    assert stopped["reason"] == CAPTURE_STOP_FAILURE
    assert "backlog full" in stopped["error"] and stopped["resumed"] is False
    assert resume["pending"] and resume["attempt"] == 0
    assert resume["next_at"] == NOON + 5 + CAPTURE_RESUME_BACKOFF_SEC[0]
    desk.tick(resume["next_at"])                       # due: lines, then start
    assert desk.acquired == ["GRML"] and desk.started == ["GRML"]
    assert resume_of(desk, "GRML") is None
    assert stopped_of(desk, "GRML")["resumed"] is True  # the shout now says it healed
    assert fields(desk)["capture_sessions"][0]["symbol"] == "GRML"


def test_one_symbol_dying_leaves_the_others_alone():
    desk = Desk()
    desk.recording = ["GRML", "F", "IMCC"]
    desk.tick(NOON)
    desk.recording, desk.errors = ["GRML", "IMCC"], {"F": "disk gone"}
    desk.tick(NOON + 5)
    assert [r["symbol"] for r in fields(desk)["capture_stopped"]] == ["F"]
    assert [r["symbol"] for r in fields(desk)["capture_resume"]] == ["F"]
    assert [s["symbol"] for s in fields(desk)["capture_sessions"]] == ["GRML", "IMCC"]
    desk.tick(resume_of(desk, "F")["next_at"])
    assert desk.started == ["F"]                       # only the dead one is restarted
    assert desk.recording == ["GRML", "IMCC", "F"]


def test_an_operator_stop_is_not_a_death():
    desk = Desk()
    desk.recording = ["GRML", "F"]
    desk.tick(NOON)
    keepalive.operator_stopped("GRML")                 # the route says so before the stop runs
    desk.recording = ["F"]
    desk.tick(NOON + 5)
    assert fields(desk)["capture_stopped"] == [] and fields(desk)["capture_resume"] == []
    assert desk.started == []
    keepalive.operator_stopped(None)                   # stop everything
    desk.recording = []
    desk.tick(NOON + 10)
    assert fields(desk)["capture_stopped"] == [] and desk.started == []


def test_resume_is_bounded_and_backs_off():
    desk = Desk(acquire_error="IBKR tape transport down")
    desk.recording = ["GRML"]
    desk.tick(NOON)
    desk.recording = []
    desk.tick(NOON + 5)
    now = NOON + 5
    for attempt in range(1, CAPTURE_RESUME_MAX_ATTEMPTS + 1):
        now = resume_of(desk, "GRML")["next_at"]
        desk.tick(now)
        resume = resume_of(desk, "GRML")
        assert resume["attempt"] == attempt
        if attempt < CAPTURE_RESUME_MAX_ATTEMPTS:
            assert resume["next_at"] == now + CAPTURE_RESUME_BACKOFF_SEC[attempt]
    assert resume["gave_up"] and "transport down" in resume["gave_up_reason"]
    assert len(desk.acquired) == CAPTURE_RESUME_MAX_ATTEMPTS
    desk.tick(now + 3600)                              # given up means given up
    assert len(desk.acquired) == CAPTURE_RESUME_MAX_ATTEMPTS


def test_ibkr_being_down_costs_no_attempt():
    desk = Desk(ready=False)
    desk.recording = ["GRML"]
    desk.tick(NOON)
    desk.recording = []
    desk.tick(NOON + 5)
    due = resume_of(desk, "GRML")["next_at"]
    desk.tick(due)
    resume = resume_of(desk, "GRML")
    assert resume["attempt"] == 0 and desk.acquired == []
    assert resume["next_at"] == due + CAPTURE_KEEPALIVE_INTERVAL_SEC
    desk.ready_flag = True
    desk.tick(resume["next_at"])
    assert desk.started == ["GRML"]


def test_resume_never_crosses_the_session_day():
    desk = Desk()
    desk.recording = ["GRML"]
    desk.tick(NOON)
    desk.recording = []
    desk.tick(NOON + 5)
    tomorrow = datetime(2026, 9, 22, 4, 0, tzinfo=ET).timestamp()
    desk.tick(tomorrow)
    resume = resume_of(desk, "GRML")
    assert resume["gave_up"] and "day ended" in resume["gave_up_reason"]
    assert desk.started == []


def test_a_gateway_drop_reacquires_the_lines_without_a_new_segment():
    desk = Desk()
    desk.recording = ["GRML", "F"]
    desk.tick(NOON)
    desk.producer_state["GRML"] = "disconnected"
    desk.ready_flag = False
    desk.tick(NOON + 5)                                # Gateway still down: nothing to take
    assert desk.acquired == []
    desk.ready_flag = True
    desk.tick(NOON + 10)                               # back: take the lines again, for that symbol only
    assert desk.released == ["GRML"] and desk.acquired == ["GRML"]
    assert desk.started == []                          # the recorder never stopped
    sessions = {s["symbol"]: s for s in fields(desk)["capture_sessions"]}
    assert sessions["GRML"]["reacquired"] == 1 and sessions["F"]["reacquired"] == 0


def test_a_restart_resumes_todays_recent_recordings():
    for symbol, prints in (("GRML", 2439), ("F", 12)):
        summary = {"symbol": symbol, "session_date": "2026-09-21", "dir": f"F:/x/{symbol}",
                   "counts": {"prints": prints}, "last_write_ts": NOON - 60}
        assert keepalive.note_restart(summary, now=NOON) is True
    out = keepalive.status_fields({}, [])
    assert [r["reason"] for r in out["capture_stopped"]] == [CAPTURE_STOP_RESTART, CAPTURE_STOP_RESTART]
    assert all(r["next_at"] == NOON for r in out["capture_resume"])  # no backoff: nothing failed
    desk = Desk()
    desk.tick(NOON)
    assert desk.started == ["GRML", "F"]


@pytest.mark.parametrize("summary", [
    None,
    {"symbol": "GRML", "session_date": "2026-09-21", "last_write_ts": NOON - CAPTURE_RESUME_RESTART_WINDOW_SEC - 1},
    {"symbol": "GRML", "session_date": "2026-09-18", "last_write_ts": NOON - 60},
])
def test_a_restart_leaves_an_old_or_other_day_recording_alone(summary):
    assert keepalive.note_restart(summary, now=NOON) is False
    assert keepalive.status_fields({}, [])["capture_resume"] == []


def test_the_operator_starting_a_symbol_supersedes_its_pending_resume():
    desk = Desk()
    desk.recording = ["GRML"]
    desk.tick(NOON)
    desk.recording = []
    desk.tick(NOON + 5)
    keepalive.operator_started("GRML")
    assert fields(desk)["capture_resume"] == [] and fields(desk)["capture_stopped"] == []
