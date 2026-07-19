"""Tests for /api/alerts routes."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alerts import channels_store, dispatch
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    store_file = tmp_path / "alerts_channels.json"
    monkeypatch.setattr(channels_store, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(
        channels_store,
        "_store_path",
        lambda: store_file,
    )
    # Avoid real DNS in SSRF validator during route tests.
    monkeypatch.setattr(
        "alerts.webhook_url.socket.getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", ("8.8.8.8", 0))],
    )
    monkeypatch.delenv("NOVA_API_KEY", raising=False)
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    dispatch._status_ring.clear()
    store_file.write_text(json.dumps({"channels": []}), encoding="utf-8")
    yield


def test_list_channels_empty():
    res = client.get("/api/alerts/channels")
    assert res.status_code == 200
    assert res.json()["channels"] == []


def test_create_rejects_ssrf_target():
    res = client.post(
        "/api/alerts/channels",
        json={
            "type": "webhook",
            "name": "Bad",
            "webhook_url": "https://127.0.0.1/hook",
        },
    )
    assert res.status_code == 400


def test_create_and_list_masks_secrets():
    res = client.post(
        "/api/alerts/channels",
        json={
            "type": "discord",
            "name": "My Discord",
            "enabled": True,
            "webhook_url": "https://discord.com/api/webhooks/abc/secret12345",
        },
    )
    assert res.status_code == 200
    ch = res.json()["channel"]
    assert ch["webhook_url_set"] is True
    assert ch["webhook_url_masked"].endswith("2345")
    assert "https://discord" not in json.dumps(ch)

    listed = client.get("/api/alerts/channels").json()["channels"]
    assert len(listed) == 1
    assert listed[0]["id"] == ch["id"]


def test_update_channel():
    created = client.post(
        "/api/alerts/channels",
        json={"type": "webhook", "name": "Hook", "webhook_url": "https://example.com/h"},
    ).json()["channel"]
    cid = created["id"]
    res = client.put(f"/api/alerts/channels/{cid}", json={"enabled": False, "name": "Renamed"})
    assert res.status_code == 200
    assert res.json()["channel"]["enabled"] is False
    assert res.json()["channel"]["name"] == "Renamed"


def test_delete_channel():
    created = client.post(
        "/api/alerts/channels",
        json={"type": "webhook", "name": "Hook", "webhook_url": "https://example.com/h"},
    ).json()["channel"]
    res = client.delete(f"/api/alerts/channels/{created['id']}")
    assert res.status_code == 200
    assert client.get("/api/alerts/channels").json()["channels"] == []


def test_test_endpoint_monkeypatched_dispatcher():
    created = client.post(
        "/api/alerts/channels",
        json={"type": "discord", "name": "D", "webhook_url": "https://discord.com/api/webhooks/x/y"},
    ).json()["channel"]
    with patch.object(dispatch, "dispatch_test", return_value={"ok": True, "channel_id": created["id"]}) as mock_test:
        res = client.post("/api/alerts/test", json={"channel_id": created["id"]})
    assert res.status_code == 200
    assert res.json()["ok"] is True
    mock_test.assert_called_once()


def test_status_endpoint():
    dispatch.record_status({"ok": False, "error": "timeout", "channel_id": "x"})
    res = client.get("/api/alerts/status")
    assert res.status_code == 200
    body = res.json()
    assert body["error_count"] >= 1
    assert body["recent_errors"][0]["error"] == "timeout"
