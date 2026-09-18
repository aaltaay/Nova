"""Thin HTTP door for bot.flatten.flatten_account_with_retry."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_flatten_account_reuses_breaker_ssot():
    fake = AsyncMock(return_value={"ok": True, "attempt": 1, "results": [], "cancels": []})
    with patch("bot.flatten.flatten_account_with_retry", fake):
        res = client.post("/api/ibkr/flatten-account")
    assert res.status_code == 200
    assert res.json() == {"ok": True, "attempt": 1, "results": [], "cancels": []}
    fake.assert_awaited_once()


def test_flatten_account_returns_breaker_failure():
    fake = AsyncMock(
        return_value={"ok": False, "error": "IBKR not connected -- cannot flatten", "results": []},
    )
    with patch("bot.flatten.flatten_account_with_retry", fake):
        res = client.post("/api/ibkr/flatten-account")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert "IBKR not connected" in body["error"]
