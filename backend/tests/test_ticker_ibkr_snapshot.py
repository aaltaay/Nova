"""IBKR ticker snapshot — price without prev_close must still populate header."""
from __future__ import annotations

import ticker_ibkr


def test_snapshot_with_price_only_no_prev_close(monkeypatch):
    monkeypatch.setattr(ticker_ibkr, "find_ibkr_cache_row", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_price_from_l1_stream", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_price_from_chart_bars", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_prev_close_from_daily_bars", lambda _s: None)
    monkeypatch.setattr(
        "ibkr.client.run_coro",
        lambda coro, timeout=None: (
            coro.close() if hasattr(coro, "close") else None,
            {
                "CJMB": {
                    "price": 1.47,
                    "prev_close": None,
                    "volume": 100,
                    "exchange": "NASDAQ",
                }
            },
        )[1],
    )

    snap = ticker_ibkr.fetch_ticker_snapshot_ibkr("CJMB")
    assert snap.get("latest_trade", {}).get("price") == 1.47
    assert snap.get("prev_close") is None
    assert snap.get("daily_bar", {}).get("close") == 1.47


def test_snapshot_uses_scanner_cache_price(monkeypatch):
    monkeypatch.setattr(
        ticker_ibkr,
        "find_ibkr_cache_row",
        lambda _s: {
            "symbol": "CJMB",
            "current_price": 2.05,
            "previous_close": 1.20,
            "volume": 50,
            "exchange": "NASDAQ",
        },
    )
    snap = ticker_ibkr.fetch_ticker_snapshot_ibkr("CJMB")
    assert snap["latest_trade"]["price"] == 2.05
    assert snap["prev_close"] == 1.20


def test_snapshot_falls_back_to_l1_stream(monkeypatch):
    monkeypatch.setattr(ticker_ibkr, "find_ibkr_cache_row", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_price_from_l1_stream", lambda _s: 3.33)
    monkeypatch.setattr(ticker_ibkr, "_price_from_chart_bars", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_prev_close_from_daily_bars", lambda _s: None)
    # Should not need slow snapshot when L1 has a print.
    monkeypatch.setattr(
        "ibkr.client.run_coro",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("snapshot_quotes should be skipped")),
    )
    snap = ticker_ibkr.fetch_ticker_snapshot_ibkr("CJMB")
    assert snap["latest_trade"]["price"] == 3.33


def test_snapshot_falls_back_to_chart_bars(monkeypatch):
    monkeypatch.setattr(ticker_ibkr, "find_ibkr_cache_row", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_price_from_l1_stream", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_price_from_chart_bars", lambda _s: 1.2902)
    monkeypatch.setattr(ticker_ibkr, "_prev_close_from_daily_bars", lambda _s: 1.10)
    monkeypatch.setattr(
        "ibkr.client.run_coro",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("snapshot_quotes should be skipped")),
    )
    snap = ticker_ibkr.fetch_ticker_snapshot_ibkr("CJMB")
    assert snap["latest_trade"]["price"] == 1.2902
    assert snap["prev_close"] == 1.10
