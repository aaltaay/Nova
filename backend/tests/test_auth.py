"""SEC-002 / SEC-004 — mutating API key guard."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from constants import NOVA_API_KEY_HEADER
from main import app

client = TestClient(app)


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
