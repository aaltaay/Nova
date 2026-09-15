"""Advise HTTP routes -- book reopen and estimate. Worker is stubbed."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from advise import book, pool, service
from constants_advise import ADVISE_GRAPH_VERSION, advise_model_id
from main import app

client = TestClient(app)


@pytest.fixture
def advise_iso(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    pool.reset_for_tests()
    book.init_db()
    return tmp_path


def test_estimate_ok(advise_iso):
    res = client.get("/api/advise/estimate", params={"symbol": "aapl", "depth": 2})
    assert res.status_code == 200
    body = res.json()
    assert body["symbol"] == "AAPL"
    assert body["depth"] == 2
    assert "est_usd" in body
    assert "not auto-trading" in body["disclaimer"]
    deep = client.get("/api/advise/estimate", params={"symbol": "aapl", "depth": 99})
    assert deep.status_code == 200
    assert deep.json()["depth"] == 5
    assert deep.json()["est_usd"] > body["est_usd"]


def test_latest_empty(advise_iso):
    res = client.get("/api/advise/latest", params={"symbol": "AAPL"})
    assert res.status_code == 200
    assert res.json()["run"] is None


def test_latest_and_history(advise_iso, monkeypatch):
    monkeypatch.setattr(service, "session_key_et", lambda: "2026-09-15")
    run = book.create_run(
        symbol="AAPL",
        model=advise_model_id(),
        graph_version=ADVISE_GRAPH_VERSION,
        depth=2,
        session_date="2026-09-15",
    )
    book.update_status(run["id"], "complete", finished=True)
    latest = client.get("/api/advise/latest", params={"symbol": "AAPL", "depth": 2})
    assert latest.status_code == 200
    assert latest.json()["run"]["id"] == run["id"]
    hist = client.get("/api/advise/history", params={"symbol": "AAPL"})
    assert hist.json()["count"] == 1
    got = client.get(f"/api/advise/runs/{run['id']}")
    assert got.json()["id"] == run["id"]


def test_run_without_key_400(advise_iso):
    res = client.post("/api/advise/run", json={"symbol": "AAPL", "depth": 2, "force_refresh": True})
    assert res.status_code == 400
    assert "OPENROUTER_API_KEY" in res.json()["detail"]


def test_bad_symbol_400(advise_iso):
    res = client.get("/api/advise/estimate", params={"symbol": "???"})
    assert res.status_code == 400


def test_cancel_and_retry_routes(advise_iso, monkeypatch):
    monkeypatch.setenv("ADVISE_STUB", "1")
    monkeypatch.setenv("ADVISE_STUB_HANG_SEC", "20")
    run = book.create_run(
        symbol="F",
        model=advise_model_id(),
        graph_version=ADVISE_GRAPH_VERSION,
        depth=2,
        session_date="2026-09-15",
    )
    book.append_event(run["id"], {"type": "message", "agent": "news", "content": "partial"})
    book.update_status(run["id"], "failed", fail_reason="boom", finished=True)
    failed = client.get(f"/api/advise/runs/{run['id']}")
    assert failed.json()["fail_reason"] == "boom"
    assert failed.json()["transcript"][0]["content"] == "partial"
    retried = client.post(f"/api/advise/runs/{run['id']}/retry")
    assert retried.status_code == 200
    assert retried.json()["id"] != run["id"]
    cancel = client.post(f"/api/advise/runs/{retried.json()['id']}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"
