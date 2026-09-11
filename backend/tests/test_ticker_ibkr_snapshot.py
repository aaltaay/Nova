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


def test_snapshot_uses_store_bars_when_cold_snapshot_fails(monkeypatch):
    """D-009 / XAIR: 1Min store already has bars; reqTickersAsync times out blank."""
    monkeypatch.setattr(ticker_ibkr, "find_ibkr_cache_row", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_price_from_l1_stream", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_prev_close_from_daily_bars", lambda _s: 5.0)

    def _read(symbol, timeframe, limit):
        assert symbol == "XAIR"
        assert timeframe == "1Min"
        return {"bars": [{"c": 5.7, "v": 302768}]}

    monkeypatch.setattr("bars_store.read", _read)
    monkeypatch.setattr(
        "ibkr.client.run_coro",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("snapshot_quotes should be skipped")),
    )
    snap = ticker_ibkr.fetch_ticker_snapshot_ibkr("XAIR")
    assert snap["latest_trade"]["price"] == 5.7
    assert snap["prev_close"] == 5.0


def test_snapshot_failure_logs_exception_type(monkeypatch, caplog):
    monkeypatch.setattr(ticker_ibkr, "find_ibkr_cache_row", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_price_from_l1_stream", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_price_from_chart_bars", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_prev_close_from_daily_bars", lambda _s: None)
    def _timeout(coro, timeout=None):
        if hasattr(coro, "close"):
            coro.close()
        raise TimeoutError()

    monkeypatch.setattr("ibkr.client.run_coro", _timeout)
    snap = ticker_ibkr.fetch_ticker_snapshot_ibkr("XAIR")
    assert snap == {}
    assert "TimeoutError" in caplog.text
    assert "XAIR" in caplog.text


def test_snapshot_retries_store_after_cold_snapshot_fails(monkeypatch):
    """Store can fill while snapshot_quotes is dying (chart HTTP already working)."""
    reads = {"n": 0}

    def _read(_symbol, _timeframe, _limit):
        reads["n"] += 1
        if reads["n"] == 1:
            return {"bars": []}
        return {"bars": [{"c": 5.7}]}

    monkeypatch.setattr(ticker_ibkr, "find_ibkr_cache_row", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_price_from_l1_stream", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_prev_close_from_daily_bars", lambda _s: None)
    monkeypatch.setattr("bars_store.read", _read)
    def _timeout(coro, timeout=None):
        if hasattr(coro, "close"):
            coro.close()
        raise TimeoutError()

    monkeypatch.setattr("ibkr.client.run_coro", _timeout)
    snap = ticker_ibkr.fetch_ticker_snapshot_ibkr("XAIR")
    assert snap["latest_trade"]["price"] == 5.7
    assert reads["n"] >= 2
