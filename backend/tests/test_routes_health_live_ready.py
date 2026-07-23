"""/livez, /readyz, and the instance-identity fields on /api/health."""
from __future__ import annotations

from fastapi.testclient import TestClient

import app_lifespan
import instance_identity
from ibkr import session_state as session
from main import app

client = TestClient(app)


def test_livez_never_depends_on_ibkr_or_bootstrap():
    res = client.get("/livez")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "alive"
    assert body["instance_id"] == instance_identity.INSTANCE_ID
    assert body["pid"] == instance_identity.PID
    assert body["uptime_sec"] >= 0


def test_readyz_reports_503_before_bootstrap_completes(monkeypatch):
    monkeypatch.setattr(app_lifespan, "_bootstrap_complete", False)
    res = client.get("/readyz")
    assert res.status_code == 503
    body = res.json()
    assert body["ready"] is False
    assert body["bootstrap_complete"] is False
    assert "ibkr" in body
    assert body["instance_id"] == instance_identity.INSTANCE_ID


def test_readyz_reports_200_once_bootstrap_completes(monkeypatch):
    monkeypatch.setattr(app_lifespan, "_bootstrap_complete", True)
    res = client.get("/readyz")
    assert res.status_code == 200
    assert res.json()["ready"] is True


def test_readyz_surfaces_ibkr_session_snapshot(monkeypatch):
    monkeypatch.setattr(app_lifespan, "_bootstrap_complete", True)
    session.reset_for_testing()
    session.set_connecting()
    session.set_synchronizing()
    session.set_ready()
    try:
        res = client.get("/readyz")
        body = res.json()
        assert body["ibkr"]["state"] == "ready"
        assert body["ibkr"]["generation"] == 1
    finally:
        session.reset_for_testing()


def test_api_health_includes_instance_identity_and_loop_lag():
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["instance_id"] == instance_identity.INSTANCE_ID
    assert body["pid"] == instance_identity.PID
    assert "loop_lag_ms" in body
    assert set(body["loop_lag_ms"]) == {"last_ms", "max_ms", "samples"}
