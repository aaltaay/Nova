"""Chart drawing routes (ADR 015) -- wiring, round-trip, and 400 on bad input."""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

_LINE = {
    "id": "horizontal-line-1",
    "type": "horizontal-line",
    "anchors": [{"time": 1_756_000_000, "price": 231.5}],
    "style": {"lineColor": "#3b82f6", "lineWidth": 1},
    "options": {"visible": True},
}


def test_get_unknown_symbol_returns_empty_list():
    res = client.get("/api/chart-drawings/NVDA")
    assert res.status_code == 200
    assert res.json() == {"symbol": "NVDA", "drawings": []}


def test_put_then_get_round_trips():
    put = client.put("/api/chart-drawings/aapl", json={"drawings": [_LINE]})
    assert put.status_code == 200
    assert put.json()["symbol"] == "AAPL"

    got = client.get("/api/chart-drawings/AAPL")
    assert got.status_code == 200
    drawings = got.json()["drawings"]
    assert len(drawings) == 1
    assert drawings[0]["type"] == "horizontal-line"
    assert drawings[0]["anchors"][0]["price"] == 231.5


def test_delete_clears_the_symbol():
    client.put("/api/chart-drawings/AAPL", json={"drawings": [_LINE]})
    res = client.delete("/api/chart-drawings/AAPL")
    assert res.status_code == 200
    assert client.get("/api/chart-drawings/AAPL").json()["drawings"] == []


def test_put_rejects_a_drawing_without_anchors():
    res = client.put(
        "/api/chart-drawings/AAPL",
        json={"drawings": [{"id": "x", "type": "horizontal-line", "anchors": []}]},
    )
    assert res.status_code == 400
    assert "anchor" in res.json()["detail"]
