"""D-016: yfinance failure must not cache an empty row for the full TTL."""
from __future__ import annotations

import time

import fundamentals as fund
from constants import FUNDAMENTALS_NEGATIVE_CACHE_TTL


def _clear_fundamentals_cache() -> None:
    fund._fundamentals_cache.clear()
    fund._fundamentals_cache_ts.clear()
    fund._fundamentals_cache_ttl.clear()


def test_fetch_fundamentals_failure_retries_after_short_ttl(monkeypatch, caplog):
    calls = {"n": 0}

    def _boom(_symbol):
        calls["n"] += 1
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(fund.yf, "Ticker", _boom)
    _clear_fundamentals_cache()

    first = fund.fetch_fundamentals("XAIR")
    assert first["float_shares"] is None
    assert first["market_cap"] is None
    assert calls["n"] == 1
    assert "yahoo down" in caplog.text

    second = fund.fetch_fundamentals("XAIR")
    assert calls["n"] == 1
    assert second["float_shares"] is None

    fund._fundamentals_cache_ts["XAIR"] = (
        time.monotonic() - FUNDAMENTALS_NEGATIVE_CACHE_TTL - 0.05
    )
    third = fund.fetch_fundamentals("XAIR")
    assert calls["n"] == 2
    assert third["float_shares"] is None


def test_fetch_fundamentals_reuses_module_executor(monkeypatch):
    class _Ticker:
        info = {"longName": "Apple Inc.", "marketCap": 1}

    monkeypatch.setattr(fund.yf, "Ticker", lambda _s: _Ticker())

    def _no_new_pool(*_a, **_k):
        raise AssertionError("must not create a per-call ThreadPoolExecutor")

    monkeypatch.setattr(fund, "ThreadPoolExecutor", _no_new_pool)
    _clear_fundamentals_cache()
    out = fund.fetch_fundamentals("AAPL")
    assert out["company_name"] == "Apple Inc."
    assert out["market_cap"] == 1


def test_successful_fetch_uses_full_ttl_not_negative(monkeypatch):
    class _Ticker:
        info = {"longName": "Apple Inc."}

    monkeypatch.setattr(fund.yf, "Ticker", lambda _s: _Ticker())
    _clear_fundamentals_cache()
    fund.fetch_fundamentals("AAPL")
    assert fund._fundamentals_cache_ttl["AAPL"] > FUNDAMENTALS_NEGATIVE_CACHE_TTL
