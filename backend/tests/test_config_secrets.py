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


def test_update_config_audit_redacts_secrets(monkeypatch, tmp_path, caplog):
    import logging

    from constants import NOVA_API_KEY_HEADER

    env_path = tmp_path / ".env"
    env_path.write_text("NOVA_DISCOVERY_PROVIDER=ibkr\n", encoding="utf-8")
    monkeypatch.setenv("NOVA_API_KEY", "test-secret-key")
    monkeypatch.setattr("routes.health.env_file_path", lambda: env_path)

    caplog.set_level(logging.INFO, logger="routes.health")
    res = client.post(
        "/api/config",
        headers={NOVA_API_KEY_HEADER: "test-secret-key"},
        json={
            "api_key": "PKSHOULDNOTLOG",
            "api_secret": "sk_should_not_log_either",
            "base_url": "https://api.alpaca.markets",
            "data_feed": "iex",
            "discovery_provider": "ibkr",
        },
    )
    assert res.status_code == 200
    joined = "\n".join(r.message for r in caplog.records)
    assert "update_config wrote .env" in joined
    assert "APCA_API_KEY_ID" in joined
    assert "PKSHOULDNOTLOG" not in joined
    assert "sk_should_not_log_either" not in joined
