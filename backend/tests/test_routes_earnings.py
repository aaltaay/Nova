"""GET /api/earnings -- thin route delegates to earnings_calendar (no logic here)."""
from __future__ import annotations

from fastapi.testclient import TestClient

import routes.earnings as earnings_route
from main import app

client = TestClient(app)


def test_get_earnings_defaults_to_today_range(monkeypatch):
    seen = {}

    def _fake_view(range_key):
        seen["range"] = range_key
        return {"range": range_key, "as_of": 123.0, "error": None, "days": []}

    monkeypatch.setattr(earnings_route, "build_earnings_view", _fake_view)
    res = client.get("/api/earnings")
    assert res.status_code == 200
    body = res.json()
    assert seen["range"] == "today"
    assert body["range"] == "today"
    assert body["days"] == []
    assert "rev" in body


def test_get_earnings_passes_through_range_param(monkeypatch):
    seen = {}

    def _fake_view(range_key):
        seen["range"] = range_key
        return {"range": range_key, "as_of": 0.0, "error": None, "days": []}

    monkeypatch.setattr(earnings_route, "build_earnings_view", _fake_view)
    res = client.get("/api/earnings", params={"range": "week"})
    assert res.status_code == 200
    assert seen["range"] == "week"
