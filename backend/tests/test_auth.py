"""SEC-002 / SEC-004 — mutating API key guard."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nova_os.events_db as events_db
from constants import NOVA_API_KEY_HEADER
from main import app
from nova_os import control_mode

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(events_db, "cache_dir", lambda: tmp_path)
    events_db.init_db()
    control_mode.reset_for_tests()
    yield
    control_mode.reset_for_tests()


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("NOVA_API_KEY", "test-secret-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    return "test-secret-key"


def test_executor_post_rejects_missing_key(api_key):
    res = client.post("/api/strategy/executor/disarm")
    assert res.status_code == 401


def test_executor_post_accepts_valid_key(api_key):
    res = client.post(
        "/api/strategy/executor/disarm",
        headers={NOVA_API_KEY_HEADER: api_key},
    )
    assert res.status_code == 200


def test_loopback_without_key_allows_mutating(monkeypatch):
    monkeypatch.delenv("NOVA_API_KEY", raising=False)
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    res = client.post("/api/strategy/executor/disarm")
    assert res.status_code == 200


def test_public_bind_without_key_rejects(monkeypatch):
    monkeypatch.delenv("NOVA_API_KEY", raising=False)
    monkeypatch.setenv("NOVA_API_HOST", "0.0.0.0")
    res = client.post("/api/strategy/executor/disarm")
    assert res.status_code == 503


def _config_payload() -> dict:
    return {
        "api_key": "",
        "api_secret": "",
        "base_url": "https://api.alpaca.markets",
        "data_feed": "iex",
        "discovery_provider": "ibkr",
    }


def test_config_post_loopback_without_key_rejects(monkeypatch):
    monkeypatch.delenv("NOVA_API_KEY", raising=False)
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    res = client.post("/api/config", json=_config_payload())
    assert res.status_code == 503
    assert "NOVA_API_KEY" in res.json()["detail"]


def test_config_post_loopback_wrong_key_rejects(api_key):
    res = client.post(
        "/api/config",
        json=_config_payload(),
        headers={NOVA_API_KEY_HEADER: "wrong"},
    )
    assert res.status_code == 401


def test_bot_mutate_loopback_without_key_rejects(monkeypatch):
    monkeypatch.delenv("NOVA_API_KEY", raising=False)
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    for path in ("/api/bot/session", "/bot/session", "/bot/action"):
        res = client.patch(path, json={"level": 1}) if path.endswith("session") else client.post(
            path, json={"kind": "buy_market", "symbol": "ABCD"}
        )
        assert res.status_code == 503
        assert "NOVA_API_KEY" in str(res.json()["detail"])


def test_bot_get_session_open_without_key(monkeypatch):
    monkeypatch.delenv("NOVA_API_KEY", raising=False)
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    assert client.get("/api/bot/session").status_code == 200
    assert client.get("/bot/session").status_code == 200


def test_sensor_memory_post_rejects_missing_key(api_key):
    res = client.post("/sensors/memory", json={"symbol": "AAPL", "decision": "go"})
    assert res.status_code == 401


def test_sensor_memory_get_stays_open_with_key_configured(api_key):
    assert client.get("/sensors/memory", params={"symbol": "AAPL"}).status_code == 200


def test_config_post_loopback_valid_key_accepted(api_key, monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("NOVA_DISCOVERY_PROVIDER=ibkr\n", encoding="utf-8")
    monkeypatch.setattr("routes.health.env_file_path", lambda: env_path)
    res = client.post(
        "/api/config",
        json=_config_payload(),
        headers={NOVA_API_KEY_HEADER: api_key},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "success"
