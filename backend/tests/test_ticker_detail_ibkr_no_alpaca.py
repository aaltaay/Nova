"""IBKR ticker detail must not require Alpaca keys (Trader quote path)."""
from __future__ import annotations

import ticker_detail


def test_ibkr_discovery_does_not_block_on_missing_alpaca_keys(monkeypatch):
    monkeypatch.setattr(ticker_detail, "_get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(ticker_detail, "_alpaca_headers", lambda: None)
    assert ticker_detail.ticker_alpaca_required_error("spy") is None


def test_non_ibkr_discovery_still_blocks_without_alpaca_keys(monkeypatch):
    monkeypatch.setattr(ticker_detail, "_get_discovery_provider", lambda: "alpaca")
    monkeypatch.setattr(ticker_detail, "_alpaca_headers", lambda: None)
    blocked = ticker_detail.ticker_alpaca_required_error("spy")
    assert blocked == {"error": "API keys not configured", "symbol": "SPY"}


def test_build_ticker_detail_ibkr_without_alpaca_keys(monkeypatch):
    monkeypatch.setattr(ticker_detail, "_get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(ticker_detail, "_alpaca_headers", lambda: None)
    monkeypatch.setattr(ticker_detail, "_env", lambda *_a, **_k: "https://api.alpaca.markets")
    monkeypatch.setattr(ticker_detail, "_get_feed", lambda: "iex")
    monkeypatch.setattr(
        ticker_detail,
        "build_ticker_fast",
        lambda *_a, **_k: {
            "symbol": "SPY",
            "asset": {},
            "snapshot": {"latest_trade": {"price": 500.0}},
            "avg_volume": None,
            "rel_volume": None,
            "news": [],
            "fundamentals": {},
            "mode": "afterhours",
            "volume_in_5min": None,
            "rvol_5min": None,
        },
    )
    monkeypatch.setattr(
        ticker_detail,
        "build_ticker_slow",
        lambda *_a, **_k: {"news": [], "avg_volume": None, "fundamentals": {}},
    )
    monkeypatch.setattr(
        ticker_detail,
        "build_listing_compare",
        lambda symbol, _asset: {"symbol": symbol, "alpaca": None, "ibkr": None},
    )
    monkeypatch.setattr(
        "news.enrich.build_ticker_news_impact",
        lambda *_a, **_k: None,
    )

    out = ticker_detail.build_ticker_detail("SPY")
    assert out["symbol"] == "SPY"
    assert "error" not in out
    assert out["snapshot"]["latest_trade"]["price"] == 500.0
    assert out.get("halt") is None
