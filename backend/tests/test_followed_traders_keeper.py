"""The keeper starts the feed again when it stops (operator ask 2026-10-14: "What do we do in the situations where the
server shuts down? We need an auto-recovery, a part of the backend with Nova"). Schema:
architecture/schema/followed-traders.md ("Starting the feed again when it stops").
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from followed_traders import feed, keeper, routes
from followed_traders.constants_followed import (
    FOLLOWED_FEED_TASK_ENV,
    FOLLOWED_FEED_URL_ENV,
    FOLLOWED_KEEPER_COOLDOWN_SEC,
    FOLLOWED_KEEPER_STALE_SEC,
)

ET = ZoneInfo("America/New_York")
TASK = "Feed Task"


def _et(text: str) -> float:
    return datetime.fromisoformat(text).replace(tzinfo=ET).timestamp()


@pytest.fixture(autouse=True)
def _desk(monkeypatch):
    keeper.reset_for_tests()
    monkeypatch.setenv(FOLLOWED_FEED_URL_ENV, "http://127.0.0.1:8787")
    monkeypatch.setenv(FOLLOWED_FEED_TASK_ENV, TASK)
    monkeypatch.setattr(keeper, "_is_windows", lambda: True)  # never sys.platform: asyncio reads it too
    yield
    keeper.reset_for_tests()


@pytest.fixture
def runs(monkeypatch):
    got: list[str] = []

    def run_task(name):
        got.append(name)
        return None

    monkeypatch.setattr(keeper, "run_task", run_task)
    return got


def _feed(monkeypatch, answer):
    """The feed answers ``answer`` (a status dict, or a FeedError to raise)."""
    def fetch_day(base, date):
        if isinstance(answer, feed.FeedError):
            raise answer
        return {"status": answer, "trades": []}

    monkeypatch.setattr(keeper.feed, "fetch_day", fetch_day)


# -- the gate --------------------------------------------------------------------------------------------------


def test_no_task_set_starts_nothing(monkeypatch):
    monkeypatch.delenv(FOLLOWED_FEED_TASK_ENV)
    assert keeper.task_name() is None
    assert keeper.view() is None


def test_a_feed_on_another_machine_is_not_ours_to_start(monkeypatch):
    monkeypatch.setenv(FOLLOWED_FEED_URL_ENV, "http://192.168.1.20:8787")
    assert keeper.task_name() is None


def test_only_windows_has_scheduled_tasks(monkeypatch):
    monkeypatch.setattr(keeper, "_is_windows", lambda: False)
    assert keeper.task_name() is None


def test_the_task_is_named_as_set():
    assert keeper.task_name() == TASK
    assert keeper.view(0.0) == {"task": TASK, "last": None, "next_at": None}


# -- the rule --------------------------------------------------------------------------------------------------


def test_a_feed_that_stops_answering_is_started_on_the_second_ask():
    now = 1_000_000.0
    assert keeper.decide(now, down_since=now, beat=None, capture_hours=False, last_run_at=None) is None
    why = keeper.decide(now + 30, down_since=now, beat=None, capture_hours=False, last_run_at=None)
    assert why == "the feed did not answer for 30 s"


def test_a_quiet_capture_is_started_only_in_its_hours():
    now = 1_000_000.0
    old = now - FOLLOWED_KEEPER_STALE_SEC - 120
    assert keeper.decide(now, down_since=None, beat=old, capture_hours=False, last_run_at=None) is None
    assert keeper.decide(now, down_since=None, beat=old, capture_hours=True,
                         last_run_at=None) == "the capture has read nothing for 12 min"
    assert keeper.decide(now, down_since=None, beat=now - 60, capture_hours=True, last_run_at=None) is None
    assert keeper.decide(now, down_since=None, beat=None, capture_hours=True,
                         last_run_at=None) == "the capture has not reported yet"


def test_one_run_per_cooldown_however_down():
    now = 1_000_000.0
    last = now - FOLLOWED_KEEPER_COOLDOWN_SEC + 1
    assert keeper.decide(now, down_since=now - 300, beat=None, capture_hours=True, last_run_at=last) is None
    assert keeper.decide(now + 1, down_since=now - 300, beat=None, capture_hours=True, last_run_at=last) is not None


def test_capture_hours_are_weekdays_from_just_after_the_tasks_start_to_the_captures_end():
    assert not keeper.in_capture_hours(_et("2026-10-15T07:55:30"))
    assert keeper.in_capture_hours(_et("2026-10-15T07:56:00"))
    assert keeper.in_capture_hours(_et("2026-10-15T16:29:59"))
    assert not keeper.in_capture_hours(_et("2026-10-15T16:30:00"))
    assert not keeper.in_capture_hours(_et("2026-10-17T10:00:00"))  # a Saturday


def test_the_heartbeat_is_the_newer_of_the_last_read_and_the_last_problem():
    assert keeper.heartbeat(None) is None
    assert keeper.heartbeat({"updated_at": 100.0, "problem_at": None}) == 100.0
    assert keeper.heartbeat({"updated_at": 100.0, "problem_at": 250.0}) == 250.0
    assert keeper.heartbeat({"updated_at": None, "problem_at": None}) is None


# -- a tick ----------------------------------------------------------------------------------------------------


def test_a_stopped_server_is_started_and_the_page_is_told(monkeypatch, runs):
    _feed(monkeypatch, feed.FeedError("unreachable", "could not connect"))
    night = _et("2026-10-14T21:11:00")
    keeper.tick(night)
    assert runs == []
    keeper.tick(night + 30)
    assert runs == [TASK]
    view = keeper.view(night + 31)
    assert view["last"] == {"at": night + 30, "why": "the feed did not answer for 30 s", "ok": True, "error": None}
    assert view["next_at"] == night + 30 + FOLLOWED_KEEPER_COOLDOWN_SEC
    keeper.tick(night + 60)  # still down, inside the cooldown
    assert runs == [TASK]


def test_an_answer_ends_the_streak(monkeypatch, runs):
    night = _et("2026-10-14T21:11:00")
    _feed(monkeypatch, feed.FeedError("unreachable", "could not connect"))
    keeper.tick(night)
    _feed(monkeypatch, {"updated_at": night - 20_000, "problem_at": None})
    keeper.tick(night + 30)  # answered: after hours, a quiet capture is fine
    _feed(monkeypatch, feed.FeedError("unreachable", "timed out after 3 s"))
    keeper.tick(night + 60)
    assert runs == []


def test_an_unreadable_answer_ends_the_streak(monkeypatch, runs):
    night = _et("2026-10-14T21:11:00")
    _feed(monkeypatch, feed.FeedError("unreachable", "could not connect"))
    keeper.tick(night)
    _feed(monkeypatch, feed.FeedError("bad_answer", "status.live is not a boolean"))
    keeper.tick(night + 30)  # the server answered
    _feed(monkeypatch, feed.FeedError("unreachable", "could not connect"))
    keeper.tick(night + 600)  # one unanswered ask after it is the start of a new streak, not the old one
    assert runs == []
    keeper.tick(night + 630)
    assert runs == [TASK]


def test_an_unreadable_answer_starts_nothing(monkeypatch, runs):
    _feed(monkeypatch, feed.FeedError("bad_answer", "status.live is not a boolean"))
    morning = _et("2026-10-15T10:00:00")
    for i in range(5):
        keeper.tick(morning + 30 * i)
    assert runs == []


def test_a_capture_quiet_in_its_hours_is_started(monkeypatch, runs):
    morning = _et("2026-10-15T10:00:00")
    _feed(monkeypatch, {"updated_at": morning - 1500, "problem_at": None})
    keeper.tick(morning)
    assert runs == [TASK]
    assert keeper.view(morning)["last"]["why"] == "the capture has read nothing for 25 min"


def test_a_task_scheduler_refusal_is_said(monkeypatch):
    monkeypatch.setattr(keeper, "run_task", lambda name: "ERROR: The system cannot find the file specified.")
    _feed(monkeypatch, feed.FeedError("unreachable", "could not connect"))
    night = _et("2026-10-14T21:11:00")
    keeper.tick(night)
    keeper.tick(night + 30)
    last = keeper.view(night + 31)["last"]
    assert last["ok"] is False
    assert last["error"] == "ERROR: The system cannot find the file specified."


def test_run_task_reads_schtasks_words(monkeypatch):
    class Done:
        returncode = 1
        stdout = ""
        stderr = "ERROR: The system cannot find the file specified.\r\n"

    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return Done()

    monkeypatch.setattr(keeper.subprocess, "run", fake_run)
    assert keeper.run_task(TASK) == "ERROR: The system cannot find the file specified."
    assert calls == [["schtasks", "/Run", "/TN", TASK]]
    Done.returncode = 0
    assert keeper.run_task(TASK) is None


def test_the_day_says_what_the_keeper_did_while_the_feed_is_down(monkeypatch, runs):
    _feed(monkeypatch, feed.FeedError("unreachable", "could not connect"))
    night = _et("2026-10-14T21:11:00")
    keeper.tick(night)
    keeper.tick(night + 30)
    monkeypatch.setattr(routes.feed, "fetch_day", lambda base, date: (_ for _ in ()).throw(
        feed.FeedError("unreachable", "could not connect")))
    app = FastAPI()
    app.include_router(routes.router)
    body = TestClient(app).get("/api/followed-traders/day").json()
    assert body["feed"] == {"state": "unreachable", "error": "could not connect"}
    assert body["keeper"]["task"] == TASK
    assert body["keeper"]["last"]["why"] == "the feed did not answer for 30 s"
