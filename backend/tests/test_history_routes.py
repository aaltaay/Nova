"""Historical replay API stays scoped to SIM and exposes acquisition errors."""
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sim import history_playback, history_store, mode, session_clock
from sim import history_routes
from sim.routes import router as sim_router


def client_for(router):
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_api_window_selection_and_download_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path))
    client = client_for(history_routes.router)
    spec = dict(symbol="F", date="2026-09-18", start="04:00", end="20:00")
    monkeypatch.setattr(mode, "is_sim_mode", lambda: False)
    assert client.post("/api/sim/history/select", json=spec).status_code == 409
    monkeypatch.setattr(mode, "is_sim_mode", lambda: True)
    try:
        result = client.post("/api/sim/history/select", json=spec)
        assert result.status_code == 200
        assert result.json()["symbol"] == "F"
        assert session_clock.status_payload()["minute_max"] == 960
        assert client.get("/api/sim/history/snapshot/SPY").json()["prints"] == []
        assert client.post("/api/sim/history", json=dict(spec, kind="quotes")).status_code == 422
        assert client.post("/api/sim/history/select", json=dict(spec, start="20:00", end="04:00")).status_code == 422
        assert client.post("/api/sim/history/missing/resume").status_code == 422
        listing = client.get("/api/sim/history").json()
        assert listing["jobs"] == [] and len(listing["default_date"]) == 10
    finally:
        history_playback.clear()
        session_clock.reset_for_tests()


def test_busy_download_refuses_without_creating_an_orphan_job(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path))
    client = client_for(history_routes.router)
    running = history_store.create(history_store.window("IMCC", "2026-09-18", "04:00", "09:30"), "trades")
    history_store.update(running["id"], status="running", updated=time.time())
    wanted = dict(symbol="IMCC", date="2026-09-18", start="04:00", end="20:00", kind="trades")
    response = client.post("/api/sim/history", json=wanted)
    assert response.status_code == 422 and "pause it first" in response.json()["detail"]
    assert history_store.find(history_store.window("IMCC", "2026-09-18", "04:00", "20:00"), "trades") is None


def test_clock_second_from_open_is_validated(monkeypatch):
    client = client_for(sim_router)
    monkeypatch.setattr(mode, "is_sim_mode", lambda: True)
    try:
        for bad in ("60", None, True, float("nan")):
            body = {"second_from_open": bad} if bad == bad else '{"second_from_open": NaN}'
            response = (client.post("/api/sim/clock", json=body) if isinstance(body, dict)
                        else client.post("/api/sim/clock", content=body,
                                         headers={"Content-Type": "application/json"}))
            assert response.status_code == 422, bad
        assert client.post("/api/sim/clock", json={"second_from_open": 90}).json()["second_from_open"] == 90
    finally:
        session_clock.reset_for_tests()


def test_corrupt_archive_returns_clean_service_error(tmp_path, monkeypatch):
    monkeypatch.setenv('NOVA_SIM_HISTORY_DIR', str(tmp_path))
    (tmp_path / 'replay.sqlite3').write_bytes(b'not a sqlite database')
    client = client_for(history_routes.router)
    response = client.get('/api/sim/history')
    assert response.status_code == 503
    assert response.json()['detail'] == 'Historical archive is unavailable; check storage and retry'


def test_missing_and_empty_download_are_distinguishable(tmp_path, monkeypatch):
    monkeypatch.setenv('NOVA_SIM_HISTORY_DIR', str(tmp_path))
    spec = history_store.window('F', '2026-09-18', '04:00', '20:00')
    try:
        missing = history_playback.select(spec)
        job = history_store.create(spec, 'trades')
        history_store.update(job['id'], status='failed', error='empty page before end')
        empty = history_playback.select(spec)
        assert missing['download_status'] == 'missing' and missing['job_id'] is None
        assert empty['download_status'] == 'failed' and empty['job_id'] == job['id']
        assert missing['trade_count'] == empty['trade_count'] == 0
    finally:
        history_playback.clear()
        session_clock.reset_for_tests()
