"""GET /api/halts/desk -- MWCB banner payload, display only."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ibkr import nasdaq_halt_feed
from main import app

client = TestClient(app)
FIXTURE = Path(__file__).with_name("fixtures") / "nasdaq_trade_halts.xml"


def setup_function(_fn):
    nasdaq_halt_feed.reset()


def test_desk_endpoint_empty_before_poll():
    res = client.get("/api/halts/desk")
    assert res.status_code == 200
    body = res.json()
    assert body["mwcb"] is None
    assert body["feed"]["source"] == "nasdaq_trade_halt_rss"
    assert body["feed"]["status"] == "pending"


def test_desk_endpoint_reports_mwcb_level_from_fixture():
    nasdaq_halt_feed.refresh(
        now=10.0, xml_text=FIXTURE.read_text(encoding="utf-8"),
    )
    res = client.get("/api/halts/desk")
    assert res.status_code == 200
    body = res.json()
    assert body["mwcb"]["level"] == 2
    assert body["mwcb"]["reason_code"] == "MWC2"
    assert body["mwcb"]["source"] == "nasdaq_trade_halt_rss"
    assert body["mwcb"]["stale"] is False
