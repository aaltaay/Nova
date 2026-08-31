"""Earnings logo cache: profile2 fetch, TTL, cache-only reads."""
from __future__ import annotations

import time

import pytest

import earnings_logos as el


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(el, "EARNINGS_LOGO_CACHE_FILE", str(tmp_path / "earnings-logos.json"))
    monkeypatch.setattr(el, "EARNINGS_LOGO_FETCH_PACING_SEC", 0.0)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    el.reset_for_testing()
    yield
    el.reset_for_testing()


def test_get_cached_logo_url_empty_without_warm():
    assert el.get_cached_logo_url("AAPL") is None


def test_fetch_one_maps_logo_url(monkeypatch):
    monkeypatch.setattr(
        el.requests,
        "get",
        lambda *a, **k: _FakeResponse(200, {"logo": "https://static.example/aapl.png"}),
    )
    assert el._fetch_one("AAPL", "key") == "https://static.example/aapl.png"


def test_fetch_one_rejects_non_http_logo(monkeypatch):
    monkeypatch.setattr(
        el.requests, "get", lambda *a, **k: _FakeResponse(200, {"logo": "/relative.png"}),
    )
    assert el._fetch_one("AAPL", "key") is None


def test_warm_writes_cache_then_get_cached(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "key")
    monkeypatch.setattr(
        el.requests,
        "get",
        lambda *a, **k: _FakeResponse(200, {"logo": "https://static.example/nvda.png"}),
    )
    el.warm(["nvda"])
    # Drain is a daemon thread -- wait briefly for single-symbol fetch.
    deadline = time.time() + 2.0
    url = None
    while time.time() < deadline:
        url = el.get_cached_logo_url("NVDA")
        if url:
            break
        time.sleep(0.05)
    assert url == "https://static.example/nvda.png"


def test_warm_noop_without_api_key(monkeypatch):
    calls = []
    monkeypatch.setattr(el.requests, "get", lambda *a, **k: calls.append(1) or _FakeResponse(200, {}))
    el.warm(["AAPL"])
    time.sleep(0.1)
    assert calls == []
    assert el.get_cached_logo_url("AAPL") is None
