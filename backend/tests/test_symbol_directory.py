"""Listed-symbol directory behind the header ticker search."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import symbol_directory
from main import app

client = TestClient(app)

ASSETS = [
    {"symbol": "aapl", "name": "Apple  Inc. Common Stock", "exchange": "NASDAQ", "status": "active", "class": "us_equity"},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "exchange": "ARCA", "status": "active", "class": "us_equity"},
    {"symbol": "BRK.B", "name": "Berkshire Hathaway Inc.", "exchange": "NYSE", "status": "active", "class": "us_equity"},
    {"symbol": "OTCX", "name": "Pink Sheet Co", "exchange": "OTC", "status": "active", "class": "us_equity"},
    {"symbol": "GONE", "name": "Delisted Co", "exchange": "NYSE", "status": "inactive", "class": "us_equity"},
    {"symbol": "BTCUSD", "name": "Bitcoin", "exchange": "NASDAQ", "status": "active", "class": "crypto"},
    {"symbol": "", "name": "Blank", "exchange": "NYSE"},
    "not-a-dict",
]


class _Resp:
    def __init__(self, status: int, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    symbol_directory.reset_for_tests()
    monkeypatch.setenv("APCA_API_KEY_ID", "k")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "s")
    monkeypatch.setenv("APCA_API_BASE_URL", "https://paper-api.example")
    yield
    symbol_directory.reset_for_tests()


def test_normalize_keeps_desk_listings_of_every_kind_sorted():
    rows = symbol_directory.normalize_assets(ASSETS)
    assert rows == [
        ("AAPL", "Apple Inc. Common Stock", "NASDAQ"),
        ("BRK.B", "Berkshire Hathaway Inc.", "NYSE"),
        ("SPY", "SPDR S&P 500 ETF Trust", "ARCA"),
    ]


def test_route_serves_the_directory_and_caches_it(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs["params"]))
        return _Resp(200, ASSETS)

    monkeypatch.setattr(symbol_directory.requests, "get", fake_get)
    body = client.get("/api/symbols/directory").json()
    assert body["schema_version"] == 1
    assert body["source"] == "alpaca_assets"
    assert body["error"] is None
    assert body["count"] == 3
    assert body["symbols"][0] == ["AAPL", "Apple Inc. Common Stock", "NASDAQ"]
    assert isinstance(body["fetched_at"], float)
    assert calls == [("https://paper-api.example/v2/assets", {"status": "active", "asset_class": "us_equity"})]
    client.get("/api/symbols/directory")
    assert len(calls) == 1


def test_failed_refresh_keeps_the_last_good_directory_and_says_why(monkeypatch):
    monkeypatch.setattr(symbol_directory.requests, "get", lambda url, **kw: _Resp(200, ASSETS))
    symbol_directory.refresh()
    monkeypatch.setattr(symbol_directory.requests, "get", lambda url, **kw: _Resp(503, None))
    symbol_directory.refresh(force=True)
    snap = symbol_directory.snapshot()
    assert snap["count"] == 3
    assert snap["error"] == "Alpaca /v2/assets answered HTTP 503"


def test_no_keys_is_a_stated_error_not_a_request(monkeypatch):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)

    def boom(*a, **k):
        raise AssertionError("no request without keys")

    monkeypatch.setattr(symbol_directory.requests, "get", boom)
    body = client.get("/api/symbols/directory").json()
    assert body["count"] == 0
    assert body["symbols"] == []
    assert body["fetched_at"] is None
    assert "not configured" in body["error"]


def test_a_failure_backs_off_before_asking_again(monkeypatch):
    calls = []

    def failing(url, **kw):
        calls.append(url)
        raise OSError("offline")

    monkeypatch.setattr(symbol_directory.requests, "get", failing)
    symbol_directory.refresh()
    symbol_directory.refresh()
    assert len(calls) == 1
    assert symbol_directory.snapshot()["error"] == "offline"
