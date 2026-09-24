"""IBKR ticker snapshot — price without prev_close must still populate header."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import ticker_ibkr


def _today_iso(days_ago: int = 0) -> str:
    """A minute from today's Eastern session, or ``days_ago`` sessions back."""
    at = datetime.now(ticker_ibkr.ET).replace(hour=10, minute=0, second=0, microsecond=0)
    return (at - timedelta(days=days_ago)).astimezone(timezone.utc).isoformat()


def test_snapshot_with_price_only_no_prev_close(monkeypatch):
    monkeypatch.setattr(ticker_ibkr, "find_ibkr_cache_row", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_price_from_l1_stream", lambda _s: (None, None))
    monkeypatch.setattr(ticker_ibkr, "_price_from_chart_bars", lambda _s: (None, None))
    monkeypatch.setattr(ticker_ibkr, "_prev_close_recorded", lambda _s: None)
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
    monkeypatch.setattr(ticker_ibkr, "_price_from_l1_stream", lambda _s: (3.33, None))
    monkeypatch.setattr(ticker_ibkr, "_price_from_chart_bars", lambda _s: (None, None))
    monkeypatch.setattr(ticker_ibkr, "_prev_close_recorded", lambda _s: None)
    # Should not need slow snapshot when L1 has a print.
    monkeypatch.setattr(
        "ibkr.client.run_coro",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("snapshot_quotes should be skipped")),
    )
    snap = ticker_ibkr.fetch_ticker_snapshot_ibkr("CJMB")
    assert snap["latest_trade"]["price"] == 3.33


def test_snapshot_falls_back_to_chart_bars(monkeypatch):
    monkeypatch.setattr(ticker_ibkr, "find_ibkr_cache_row", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_price_from_l1_stream", lambda _s: (None, None))
    monkeypatch.setattr(ticker_ibkr, "_price_from_chart_bars", lambda _s: (1.2902, None))
    monkeypatch.setattr(ticker_ibkr, "_prev_close_recorded", lambda _s: 1.10)
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
    monkeypatch.setattr(ticker_ibkr, "_price_from_l1_stream", lambda _s: (None, None))
    monkeypatch.setattr(ticker_ibkr, "_prev_close_recorded", lambda _s: 5.0)

    def _read(symbol, timeframe, limit):
        assert symbol == "XAIR"
        assert timeframe == "1Min"
        return {"bars": [{"t": _today_iso(), "c": 5.7, "v": 302768}]}

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
    monkeypatch.setattr(ticker_ibkr, "_price_from_l1_stream", lambda _s: (None, None))
    monkeypatch.setattr(ticker_ibkr, "_price_from_chart_bars", lambda _s: (None, None))
    monkeypatch.setattr(ticker_ibkr, "_prev_close_recorded", lambda _s: None)
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
        return {"bars": [{"t": _today_iso(), "c": 5.7}]}

    monkeypatch.setattr(ticker_ibkr, "find_ibkr_cache_row", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_price_from_l1_stream", lambda _s: (None, None))
    monkeypatch.setattr(ticker_ibkr, "_prev_close_recorded", lambda _s: None)
    monkeypatch.setattr("bars_store.read", _read)
    def _timeout(coro, timeout=None):
        if hasattr(coro, "close"):
            coro.close()
        raise TimeoutError()

    monkeypatch.setattr("ibkr.client.run_coro", _timeout)
    snap = ticker_ibkr.fetch_ticker_snapshot_ibkr("XAIR")
    assert snap["latest_trade"]["price"] == 5.7
    assert reads["n"] >= 2


# --- #541: a snapshot never passes an old price or the prior close off as today's last ---


def _no_live_sources(monkeypatch):
    monkeypatch.setattr(ticker_ibkr, "_prev_close_recorded", lambda _s: None)
    monkeypatch.setattr(
        "ibkr.client.run_coro",
        lambda coro, timeout=None: (coro.close() if hasattr(coro, "close") else None, {})[1],
    )


def test_a_row_repriced_before_the_first_trade_is_not_a_last(monkeypatch):
    monkeypatch.setattr(ticker_ibkr, "find_ibkr_cache_row", lambda _s: {
        "symbol": "APLX", "price": 9.52, "previous_close": 9.52, "volume": None,
        "quote_quality": "close_fallback",
    })
    monkeypatch.setattr(ticker_ibkr, "_price_from_l1_stream", lambda _s: (None, None))
    monkeypatch.setattr(ticker_ibkr, "_price_from_chart_bars", lambda _s: (None, None))
    _no_live_sources(monkeypatch)
    snap = ticker_ibkr.fetch_ticker_snapshot_ibkr("APLX")
    assert snap["latest_trade"] is None and snap["daily_bar"] is None
    assert snap["prev_close"] == 9.52


def test_the_l1_line_before_its_first_trade_has_no_last(monkeypatch):
    from ibkr import ticks

    monkeypatch.setattr(ticks, "last_quotes", lambda symbols=None: {
        "APLX": {"price": 9.52, "quote_quality": "close_fallback", "last_trade_ts": None},
    })
    assert ticker_ibkr._price_from_l1_stream("APLX") == (None, None)
    monkeypatch.setattr(ticks, "last_quotes", lambda symbols=None: {
        "APLX": {"price": 8.60, "quote_quality": None, "last_trade_ts": 1_790_193_683.0},
    })
    assert ticker_ibkr._price_from_l1_stream("APLX") == (8.60, 1_790_193_683.0)


def test_last_nights_bar_is_not_todays_last(monkeypatch):
    monkeypatch.setattr("bars_store.read", lambda *_a, **_k: {"bars": [{"t": _today_iso(days_ago=1), "c": 7.0}]})
    assert ticker_ibkr._price_from_chart_bars("APLX") == (None, None)
    monkeypatch.setattr("bars_store.read", lambda *_a, **_k: {"bars": [{"c": 7.0}]})  # no minute: unknown
    assert ticker_ibkr._price_from_chart_bars("APLX") == (None, None)


def test_the_last_carries_its_own_time_and_unknown_volume_is_null(monkeypatch):
    monkeypatch.setattr(ticker_ibkr, "find_ibkr_cache_row", lambda _s: None)
    monkeypatch.setattr(ticker_ibkr, "_price_from_l1_stream", lambda _s: (None, None))
    minute = _today_iso()
    monkeypatch.setattr("bars_store.read", lambda *_a, **_k: {"bars": [{"t": minute, "c": 5.7}]})
    _no_live_sources(monkeypatch)
    snap = ticker_ibkr.fetch_ticker_snapshot_ibkr("XAIR")
    stamp = datetime.fromisoformat(minute).timestamp()
    assert datetime.fromisoformat(snap["latest_trade"]["timestamp"]).timestamp() == stamp
    assert snap["daily_bar"]["volume"] is None


# --- #542: the prior close is IBKR's tick 9 or the leaderboard's, never a daily bar ---


def test_the_prior_close_is_the_l1_lines_tick9(monkeypatch):
    from ibkr import ticks

    monkeypatch.setattr(ticks, "last_quotes", lambda symbols=None: {
        "WHLR": {"price": 2.10, "quote_quality": None, "prev_close": 1.87},
    })
    monkeypatch.setattr("chart_bars.fetch_chart_bars", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("the extended-hours daily bars are never a prior close")))
    assert ticker_ibkr._prev_close_recorded("whlr") == 1.87


def test_without_tick9_todays_leaderboard_answers_and_else_none(monkeypatch):
    from ibkr import ticks
    from leaderboard import store as lb_store
    from leaderboard.rows import make_row

    monkeypatch.setattr(ticks, "last_quotes", lambda symbols=None: {})
    assert ticker_ibkr._prev_close_recorded("WHLR") is None
    minute = int(datetime.now(ticker_ibkr.ET).replace(hour=9, minute=30, second=0, microsecond=0).timestamp())
    with lb_store.connect() as db:
        lb_store.write_batch(db, rows=[make_row(symbol="WHLR", minute_ts=minute, board="gainers",
                                                source="recorded", rank=1, price=2.1, prev_close=1.87)])
    assert ticker_ibkr._prev_close_recorded("WHLR") == 1.87
