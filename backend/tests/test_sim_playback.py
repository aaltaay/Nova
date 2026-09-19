"""Pause freezes the Sim clock/feed; play resumes without wall-time catch-up."""
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sim import feed, market, mode, replay, session_clock as clock
from sim.routes import router


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    clock.reset_for_tests()
    wall = [datetime(2026, 9, 19, 10, 0, tzinfo=clock.ET)]
    mono = [100.0]
    monkeypatch.setattr(clock, "_wall_et_now", lambda: wall[0])
    monkeypatch.setattr(clock.time_mod, "monotonic", lambda: mono[0])
    monkeypatch.setattr(market, "rebuild_for_scrub", Mock())
    yield wall, mono
    clock.reset_for_tests()


@pytest.mark.parametrize("scrubbed", [False, True])
def test_pause_and_resume_from_exact_position(frozen_clock, scrubbed):
    wall, mono = frozen_clock
    if scrubbed:
        clock.scrub_to_second(125.5)
    start = clock.now_et()
    assert clock.set_paused(True)["paused"]
    wall[0] += timedelta(days=1)
    mono[0] += 86400
    assert clock.now_et() == start
    clock.set_paused(True)  # duplicate pause is harmless
    assert clock.now_et() == start
    assert not clock.set_paused(False)["paused"]
    assert clock.now_et() == start
    mono[0] += 3
    clock.set_paused(False)  # duplicate play must not reset its anchor
    assert clock.now_et() == start + timedelta(seconds=3)
    clock.clear_scrub()
    assert clock.now_et() == wall[0]


def test_scrub_while_paused_stays_paused(frozen_clock):
    _, mono = frozen_clock
    clock.set_paused(True)
    clock.scrub_to_minute(90)
    mono[0] += 60
    assert clock.status_payload()["second_from_open"] == 5400
    assert clock.is_paused()
    clock.set_session_date("2026-09-18")
    clock.scrub_to_second(100.5)
    assert clock.now_et() == datetime(2026, 9, 18, 4, 1, 40, 500000, tzinfo=clock.ET)
    clock.set_paused(False)
    mono[0] += 2
    assert clock.status_payload()["second_from_open"] == 102


@pytest.mark.parametrize("capture", [False, True])
def test_paused_feed_does_not_step_match_or_publish(monkeypatch, capture):
    monkeypatch.setattr(replay, "is_capture_replay", lambda: capture)
    step = Mock(return_value={"type": "print"})
    match, inject = Mock(), Mock()
    monkeypatch.setattr(market, "step", step)
    monkeypatch.setattr(feed._broker, "try_fill_working", match)
    monkeypatch.setattr(feed, "_inject", inject)
    clock.set_paused(True)
    assert feed.tick() == {}
    step.assert_not_called()
    match.assert_not_called()
    inject.assert_not_called()
    clock.set_paused(False)
    # Both branches can resume; exercise the deterministic synthetic path here.
    monkeypatch.setattr(replay, "is_capture_replay", lambda: False)
    feed.tick()
    step.assert_called_once()
    match.assert_called_once()
    inject.assert_called_once()


def test_api_pause_only_in_sim_and_validates_boolean(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    monkeypatch.setattr(mode, "is_sim_mode", lambda: False)
    assert client.post("/api/sim/clock", json={"paused": True}).status_code == 409
    assert not clock.is_paused()
    monkeypatch.setattr(mode, "is_sim_mode", lambda: True)
    assert client.post("/api/sim/clock", json={"paused": "false"}).status_code == 422
    assert client.post("/api/sim/clock", json={"paused": True}).json()["paused"]
    assert client.get("/api/sim/clock").json()["paused"]
    assert not client.post("/api/sim/clock", json={"paused": False}).json()["paused"]
    client.post("/api/sim/clock", json={"paused": True})
    assert not client.post("/api/sim/clock", json={"follow_wall": True}).json()["paused"]


def test_default_extended_session_and_custom_window(frozen_clock):
    wall, _ = frozen_clock
    wall[0] = wall[0].replace(hour=2)
    assert clock.now_et().hour == 4
    status = clock.status_payload()
    assert status["minute_max"] == 960
    assert status["second_max"] == 57600
    clock.scrub_to_minute(9999)
    assert clock.now_et().hour == 20
    assert clock.phase() == "postmarket"
    clock.set_window("04:00", "09:30")
    clock.scrub_to_minute(9999)
    assert clock.status_payload()["minute_max"] == 330
    assert (clock.now_et().hour, clock.now_et().minute) == (9, 30)
