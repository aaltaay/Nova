"""HTTP capture ownership and server status reconciliation (#316, #339)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import time

from capture import feed_hold, mode, recorder, worker
from capture.routes import router
from sim.status import overlay_ibkr_status


HOLDS: dict = {}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_CAPTURE_DIR", str(tmp_path))
    from capture import bridge_ibkr
    monkeypatch.setattr(bridge_ibkr, "admission_error", lambda symbol: None)
    # Record opens its own IBKR lines (capture.feed_hold); tests have no Gateway,
    # so stand in for the hold and keep a log of what the route asked for.
    feed_hold.reset_for_tests()
    HOLDS.update(acquired=[], released=[], refuse=None)

    async def acquire(symbol):
        HOLDS["acquired"].append(symbol)
        if HOLDS["refuse"]:
            return HOLDS["refuse"]
        feed_hold._held[symbol] = {"tape": True, "depth": True}
        return None

    async def release(symbol):
        HOLDS["released"].append(symbol)
        feed_hold._held.pop(symbol, None)

    monkeypatch.setattr(feed_hold, "acquire", acquire)
    monkeypatch.setattr(feed_hold, "release", release)
    mode.set_capture_mode(False)
    recorder.reset_for_tests()
    mode.reset_for_tests()
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        yield client
    mode.set_capture_mode(False)
    recorder.reset_for_tests()
    mode.reset_for_tests()


def toggle(client, enabled, symbol=None):
    return client.post("/api/capture", json={"enabled": enabled, "symbol": symbol})


def test_http_ownership_conflicts_preserve_active_session(client, monkeypatch):
    started = toggle(client, True, " aapl ")
    assert started.status_code == 200
    assert started.json()["capture_symbol"] == "AAPL"
    start = Mock(wraps=recorder.start_recorder)
    stop = Mock(wraps=recorder.stop_recorder)
    monkeypatch.setattr(recorder, "start_recorder", start)
    monkeypatch.setattr(recorder, "stop_recorder", stop)
    assert toggle(client, True, "AAPL").status_code == 200
    for enabled in (True, False):
        conflict = toggle(client, enabled, "TSLA")
        assert conflict.status_code == 409
        assert "Already recording AAPL" in conflict.json()["detail"]
        state = client.get("/api/capture").json()
        assert state["capture_symbol"] == "AAPL"
        assert state["recorder"]["recording"] is True
    start.assert_not_called()
    stop.assert_not_called()
    assert toggle(client, False, "AAPL").json()["capture"] is False
    assert toggle(client, True, "TSLA").json()["capture_symbol"] == "TSLA"


def test_concurrent_http_starts_have_one_owner(client):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda sym: toggle(client, True, sym), ["AAPL", "TSLA"]))
    assert sorted(result.status_code for result in results) == [200, 409]
    winner = next(result.json()["capture_symbol"] for result in results if result.status_code == 200)
    assert client.get("/api/capture").json()["capture_symbol"] == winner


def test_invalid_empty_start_does_not_record(client):
    result = toggle(client, True, " ").json()
    assert result["capture"] is False
    assert result["error"] == "Pick a symbol tab before Record"
    assert recorder.is_recording() is False


def test_start_failure_is_returned_without_false_recording(client, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("disk unavailable")
    monkeypatch.setattr(recorder, "start_recorder", fail)
    result = toggle(client, True, "AAPL").json()
    assert result["capture"] is False
    assert result["capture_symbol"] is None
    assert result["error"] == "Recorder start failed"


def test_status_poll_reconciles_self_stopped_writer(client):
    toggle(client, True, "AAPL")
    worker.transition(lambda: recorder.fail_recorder("disk full"))
    payload = overlay_ibkr_status({"mode": "paper", "connected": False, "trading_allowed": False})
    assert payload["capture"] is False
    assert payload["recording"] is False
    assert payload["capture_symbol"] is None
    assert payload["capture_error"] == "disk full"
    assert payload["trading_allowed"] is False
    assert payload["mode"] == "paper"
    assert overlay_ibkr_status({})["capture_error"] == "disk full"


def test_recording_status_never_changes_gateway_or_spend(client):
    toggle(client, True, "AAPL")
    state = overlay_ibkr_status({"mode": "live", "connected": False, "trading_allowed": False})
    assert state["capture_symbol"] == "AAPL"
    assert state["recording"] is True
    assert state["connected"] is False
    assert state["trading_allowed"] is False
    assert state["mode"] == "live"

def test_stop_failure_keeps_actual_recording_owner(client, monkeypatch):
    toggle(client, True, "AAPL")
    with monkeypatch.context() as patch:
        patch.setattr(recorder, "stop_recorder", Mock(side_effect=OSError("flush failed")))
        result = toggle(client, False, "AAPL").json()
        assert result["error"] == "Recorder stop failed"
        assert result["capture"] is True
        assert result["capture_symbol"] == "AAPL"
    assert toggle(client, False, "AAPL").json()["capture"] is False



def eventually(check, timeout=2.0):
    """Releases run as background tasks so a stop answers without waiting on depth's grace."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.02)
    return check()


def test_record_holds_its_own_lines_until_it_stops(client):
    started = toggle(client, True, "aapl").json()
    assert started["capture"] is True
    assert HOLDS["acquired"] == ["AAPL"] and feed_hold.held("AAPL")
    toggle(client, False, "AAPL")
    assert eventually(lambda: HOLDS["released"] == ["AAPL"])
    assert feed_hold.held("AAPL") is None


def test_a_refused_tape_line_refuses_the_recording(client):
    HOLDS["refuse"] = "IBKR tape transport down -- Gateway not connected"
    result = toggle(client, True, "AAPL").json()
    assert result["error"] == "IBKR tape transport down -- Gateway not connected"
    assert result["capture"] is False
    assert recorder.is_recording() is False
    assert feed_hold.held("AAPL") is None


def test_a_second_symbol_is_refused_before_any_line_is_opened(client):
    toggle(client, True, "AAPL")
    assert toggle(client, True, "TSLA").status_code == 409
    assert HOLDS["acquired"] == ["AAPL"]  # never touched TSLA's tape (15 s resubscribe guard)


def test_a_recorder_that_stopped_itself_gives_its_lines_back(client):
    toggle(client, True, "AAPL")
    worker.transition(lambda: recorder.fail_recorder("disk full"))
    assert client.get("/api/capture").json()["capture"] is False
    assert eventually(lambda: HOLDS["released"] == ["AAPL"])
