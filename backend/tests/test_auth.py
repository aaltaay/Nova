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
