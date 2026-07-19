"""SEC-001 — GET /api/config must not return plaintext Alpaca secrets."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _stub_env(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "PKREALSECRET1234567890")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "sk_live_supersecretalpacakeyvalue")
    monkeypatch.delenv("NOVA_API_KEY", raising=False)
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")


def test_get_config_masks_secrets():
    res = client.get("/api/config")
    assert res.status_code == 200
    body = res.json()
    assert "api_key" not in body or body.get("api_key") in ("", None)
    assert "api_secret" not in body or body.get("api_secret") in ("", None)
    assert body["api_key_set"] is True
    assert body["api_secret_set"] is True
    assert "PKREAL" not in body["api_key_masked"]
    assert "sk_live" not in body["api_secret_masked"]
    dumped = str(body)
    assert "PKREALSECRET1234567890" not in dumped
    assert "sk_live_supersecretalpacakeyvalue" not in dumped
