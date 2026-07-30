"""Tests for IBKR historical bar normalization + chart_bars dispatcher."""
import sys
import os
from datetime import date, datetime, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ibkr.bars import _bar_time_iso, _normalize_bars  # noqa: E402
import chart_bars  # noqa: E402


class _FakeBar:
    def __init__(self, d, o, h, low, c, v):
        self.date = d
        self.open = o
        self.high = h
        self.low = low
        self.close = c
        self.volume = v


def test_bar_time_iso_from_aware_datetime():
    dt = datetime(2026, 7, 14, 14, 30, tzinfo=timezone.utc)
    assert _bar_time_iso(dt) == "2026-07-14T14:30:00Z"


def test_bar_time_iso_from_naive_datetime_assumes_utc():
    dt = datetime(2026, 7, 14, 14, 30)
    assert _bar_time_iso(dt) == "2026-07-14T14:30:00Z"


def test_bar_time_iso_from_date():
    assert _bar_time_iso(date(2026, 7, 14)) == "2026-07-14T00:00:00Z"


def test_normalize_bars_trims_to_limit_keeping_newest():
    raw = [
        _FakeBar(datetime(2026, 7, 14, 14, i, tzinfo=timezone.utc), 1, 2, 0.5, 1.5, 100 + i)
        for i in range(5)
    ]
    bars = _normalize_bars(raw, limit=2)
    assert len(bars) == 2
    assert bars[0]["t"] == "2026-07-14T14:03:00Z"
    assert bars[1]["t"] == "2026-07-14T14:04:00Z"
    assert bars[1]["v"] == 104


def test_10sec_timeframe_maps_and_warm_set():
    from constants_scanner import (
        CHART_TIMEFRAMES,
        IBKR_10SEC_FETCH_BARS,
        IBKR_BAR_DURATION,
        IBKR_BAR_SIZE,
        IBKR_BARS_WARM_TIMEFRAMES,
    )

    assert "10Sec" in CHART_TIMEFRAMES
    assert IBKR_BAR_SIZE["10Sec"] == "10 secs"
    assert IBKR_BAR_DURATION["10Sec"] == "14400 S"
    assert IBKR_10SEC_FETCH_BARS == 1500
    assert "10Sec" not in IBKR_BARS_WARM_TIMEFRAMES
    assert "15Min" not in IBKR_BARS_WARM_TIMEFRAMES
    assert IBKR_BARS_WARM_TIMEFRAMES == ("1Min", "5Min", "1Day")


def test_fetch_bars_async_clamps_10sec_limit():
    """Default limit=500 must still store/return the full 10Sec window."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    from ibkr import bars as ibkr_bars

    captured: dict = {}

    async def fake_get_or_fetch(symbol, timeframe, limit, *, interactive, fetch_fn):
        captured["limit"] = limit
        captured["timeframe"] = timeframe
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": [],
            "source": "ibkr",
        }

    async def _run():
        with patch("ibkr.bars_cache.get_or_fetch", new=AsyncMock(side_effect=fake_get_or_fetch)):
            await ibkr_bars.fetch_bars_async("AAPL", "10Sec", 500, interactive=True)

    asyncio.run(_run())
    assert captured["timeframe"] == "10Sec"
    assert captured["limit"] == 1500


def test_fetch_chart_bars_ibkr_mode_errors_when_disconnected():
    from fastapi import HTTPException

    with patch.object(chart_bars._ibkr_client, "is_connected", return_value=False):
        with patch.object(chart_bars, "fetch_alpaca_bars") as alpaca:
            try:
                chart_bars.fetch_chart_bars("AAPL", "1Min", 10, discovery_provider="ibkr")
                assert False, "expected HTTPException"
            except HTTPException as exc:
                assert exc.status_code == 503
                assert "Alpaca" in str(exc.detail)
    alpaca.assert_not_called()


def test_fetch_chart_bars_alpaca_mode_uses_alpaca():
    with patch.object(chart_bars, "fetch_alpaca_bars", return_value={
        "symbol": "AAPL", "timeframe": "1Min", "bars": [{"t": "x", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}],
    }) as alpaca:
        out = chart_bars.fetch_chart_bars("AAPL", "1Min", 10, discovery_provider="alpaca")
    alpaca.assert_called_once()
    assert out["source"] == "alpaca"
    assert out["symbol"] == "AAPL"


def test_describe_exc_never_empty_for_timeout():
    from ibkr.errors import describe_exc, is_transient_historical_failure

    empty = TimeoutError()
    assert describe_exc(empty) == "TimeoutError"
    assert is_transient_historical_failure(empty) is True
    assert is_transient_historical_failure(RuntimeError("Error 162: Historical Market Data Service query cancelled"))


def test_fetch_chart_bars_ibkr_timeout_is_503_with_clear_detail():
    from fastapi import HTTPException

    def _timeout_bridge(coro, timeout):
        coro.close()
        raise TimeoutError()

    with patch.object(chart_bars._ibkr_client, "is_connected", return_value=True):
        with patch.object(chart_bars._ibkr_client, "run_coro", side_effect=_timeout_bridge):
            with patch.object(chart_bars, "fetch_alpaca_bars") as alpaca:
                try:
                    chart_bars.fetch_chart_bars("AAPL", "1Min", 10, discovery_provider="ibkr")
                    assert False, "expected HTTPException"
                except HTTPException as exc:
                    assert exc.status_code == 503
                    detail = str(exc.detail)
                    assert "timed out" in detail.lower() or "cancelled" in detail.lower()
                    assert "TimeoutError" in detail
                    assert "Alpaca" in detail  # honesty: no silent fallback
    alpaca.assert_not_called()
