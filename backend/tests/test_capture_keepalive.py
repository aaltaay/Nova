"""Resume, then say so: a Session Record gets back up on its own (operator decision, 2026-09-21).

The market only happens once. A restart, a recorder failure or a lost IBKR line
must cost a gap, not the rest of the session -- bounded, never across a day,
never onto another symbol, and cancelled by the operator's own Stop.
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
        self.recording: str | None = None
        self.producer_state = "receiving"
        self.error: str | None = None

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
            self.recording = symbol
            return {"capture": True, "capture_symbol": symbol}
        return {"capture": False, "error": "Recorder start failed"}

    def payload(self):
        if self.recording:
            return {"capture": True, "capture_symbol": self.recording,
                    "producer": {"state": self.producer_state}}
        return {"capture": False, "capture_symbol": None, "error": self.error}

    def recorder(self):
        return {"symbol": self.recording or "GRML", "session_date": "2026-09-21",
                "dir": "F:/x/2026-09-21/GRML", "counts": {"prints": 2439}, "error": self.error,
                "started_et": "2026-09-21T11:46:35-04:00", "segment_started_et": "2026-09-21T11:46:35-04:00",
                "segment": 1, "last_write_ts": NOON - 1}

    def tick(self, now):
        asyncio.run(keepalive.tick(now=now, payload=self.payload(), recorder_status=self.recorder(),
                                   ready=self.ready, acquire=self.acquire, release=self.release,
                                   start=self.start))


@pytest.fixture(autouse=True)
def fresh():
    keepalive.reset_for_tests()
    yield
    keepalive.reset_for_tests()


def test_a_recording_that_dies_is_shouted_about_and_resumed():
    desk = Desk()
    desk.recording = "GRML"
    desk.tick(NOON)                                    # watched
    desk.recording, desk.error = None, "Capture writer backlog full"
    desk.tick(NOON + 5)                                # gone, and the operator did not stop it
    fields = keepalive.status_fields(desk.recorder(), False)
    stopped, resume = fields["capture_stopped"], fields["capture_resume"]
    assert stopped["symbol"] == "GRML" and stopped["reason"] == CAPTURE_STOP_FAILURE
    assert "backlog full" in stopped["error"] and stopped["resumed"] is False
    assert resume["pending"] and resume["attempt"] == 0
    assert resume["next_at"] == NOON + 5 + CAPTURE_RESUME_BACKOFF_SEC[0]
    desk.tick(resume["next_at"])                       # due: lines, then start
    assert desk.acquired == ["GRML"] and desk.started == ["GRML"]
    fields = keepalive.status_fields(desk.recorder(), True)
    assert fields["capture_resume"] is None
    assert fields["capture_stopped"]["resumed"] is True  # the shout now says it healed
    assert fields["capture_session"]["symbol"] == "GRML"


def test_an_operator_stop_is_not_a_death():
    desk = Desk()
    desk.recording = "GRML"
    desk.tick(NOON)
    keepalive.operator_stopped("GRML")                 # the route says so before the stop runs
    desk.recording = None
    desk.tick(NOON + 5)
    fields = keepalive.status_fields(desk.recorder(), False)
    assert fields["capture_stopped"] is None and fields["capture_resume"] is None
    assert desk.started == []


def test_resume_is_bounded_and_backs_off():
    desk = Desk(acquire_error="IBKR tape transport down")
    desk.recording = "GRML"
    desk.tick(NOON)
    desk.recording = None
    desk.tick(NOON + 5)
    now = NOON + 5
    for attempt in range(1, CAPTURE_RESUME_MAX_ATTEMPTS + 1):
        resume = keepalive.status_fields(desk.recorder(), False)["capture_resume"]
        now = resume["next_at"]
        desk.tick(now)
        resume = keepalive.status_fields(desk.recorder(), False)["capture_resume"]
        assert resume["attempt"] == attempt
        if attempt < CAPTURE_RESUME_MAX_ATTEMPTS:
            assert resume["next_at"] == now + CAPTURE_RESUME_BACKOFF_SEC[attempt]
    assert resume["gave_up"] and "transport down" in resume["gave_up_reason"]
    assert len(desk.acquired) == CAPTURE_RESUME_MAX_ATTEMPTS
    desk.tick(now + 3600)                              # given up means given up
    assert len(desk.acquired) == CAPTURE_RESUME_MAX_ATTEMPTS


def test_ibkr_being_down_costs_no_attempt():
    desk = Desk(ready=False)
    desk.recording = "GRML"
    desk.tick(NOON)
    desk.recording = None
    desk.tick(NOON + 5)
    due = keepalive.status_fields(desk.recorder(), False)["capture_resume"]["next_at"]
    desk.tick(due)
    resume = keepalive.status_fields(desk.recorder(), False)["capture_resume"]
    assert resume["attempt"] == 0 and desk.acquired == []
    assert resume["next_at"] == due + CAPTURE_KEEPALIVE_INTERVAL_SEC
    desk.ready_flag = True
    desk.tick(resume["next_at"])
    assert desk.started == ["GRML"]


def test_resume_never_crosses_the_session_day():
    desk = Desk()
    desk.recording = "GRML"
    desk.tick(NOON)
    desk.recording = None
    desk.tick(NOON + 5)
    tomorrow = datetime(2026, 9, 22, 4, 0, tzinfo=ET).timestamp()
    desk.tick(tomorrow)
    resume = keepalive.status_fields(desk.recorder(), False)["capture_resume"]
    assert resume["gave_up"] and "day ended" in resume["gave_up_reason"]
    assert desk.started == []


def test_a_gateway_drop_reacquires_the_lines_without_a_new_segment():
    desk = Desk()
    desk.recording = "GRML"
    desk.tick(NOON)
    desk.producer_state = "disconnected"
    desk.ready_flag = False
    desk.tick(NOON + 5)                                # Gateway still down: nothing to take
    assert desk.acquired == []
    desk.ready_flag = True
    desk.tick(NOON + 10)                               # back: take the lines again
    assert desk.released == ["GRML"] and desk.acquired == ["GRML"]
    assert desk.started == []                          # the recorder never stopped
    assert keepalive.status_fields(desk.recorder(), True)["capture_session"]["reacquired"] == 1


def test_a_restart_resumes_todays_recent_recording():
    summary = {"symbol": "GRML", "session_date": "2026-09-21", "dir": "F:/x",
               "counts": {"prints": 2439}, "last_write_ts": NOON - 60}
    assert keepalive.note_restart(summary, now=NOON) is True
    fields = keepalive.status_fields({}, False)
    assert fields["capture_stopped"]["reason"] == CAPTURE_STOP_RESTART
    assert fields["capture_resume"]["next_at"] == NOON  # no backoff: nothing failed
    desk = Desk()
    desk.tick(NOON)
    assert desk.started == ["GRML"]


@pytest.mark.parametrize("summary", [
    None,
    {"symbol": "GRML", "session_date": "2026-09-21", "last_write_ts": NOON - CAPTURE_RESUME_RESTART_WINDOW_SEC - 1},
    {"symbol": "GRML", "session_date": "2026-09-18", "last_write_ts": NOON - 60},
])
def test_a_restart_leaves_an_old_or_other_day_recording_alone(summary):
    assert keepalive.note_restart(summary, now=NOON) is False
    assert keepalive.status_fields({}, False)["capture_resume"] is None


def test_the_operator_starting_a_recording_supersedes_a_pending_resume():
    desk = Desk()
    desk.recording = "GRML"
    desk.tick(NOON)
    desk.recording = None
    desk.tick(NOON + 5)
    keepalive.operator_started("IMCC")
    fields = keepalive.status_fields(desk.recorder(), False)
    assert fields["capture_resume"] is None and fields["capture_stopped"] is None
