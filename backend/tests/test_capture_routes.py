"""HTTP capture ownership and server status reconciliation (#316, #339)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from capture import mode, recorder, worker
from capture.routes import router
from sim.status import overlay_ibkr_status


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_CAPTURE_DIR", str(tmp_path))
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
