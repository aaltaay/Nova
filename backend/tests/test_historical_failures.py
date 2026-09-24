"""A chart pane says IBKR history stopped answering, and a failed pair backs off (#555).

2026-09-23 21:46 ET: IBKR's HMDS farm dropped. Every ``reqHistoricalData``
timed out, the pane said "Loading IBKR historical..." for the whole outage, and
each retry (the 15 s identical-request cooldown is shorter than the 20 s
timeout) spent the 60 / 10 min budget again -- 51 of 60 used by 21:50.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import chart_bars
from constants import (
    IBKR_HISTORICAL_FAILURE_BACKOFF_SEC,
    IBKR_HISTORICAL_FAILURE_MEMORY_SEC,
)
from ibkr import historical_failures
from ibkr.historical_service import HistoricalShed, request_bars, reset_for_testing

TIMEOUT_DETAIL = "IBKR historical data did not answer within 20s"
T0 = 1_790_000_000.0


@pytest.fixture(autouse=True)
def _reset():
    reset_for_testing()
    yield
    reset_for_testing()


class _Clock:
    def __init__(self, now: float = T0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def _payload(symbol: str, timeframe: str) -> dict:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": [{"t": "2026-09-23T14:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}],
        "source": "ibkr",
    }


def _request(fetch: AsyncMock, *, symbol: str = "TLSA", timeframe: str = "5Min"):
    """One open-chart request with the store empty and the IBKR fetch stubbed."""
    pushes: list[dict] = []

    async def _run():
        with (
            patch("bars_store.read", return_value=None),
            patch("bars_store.write_payload"),
            patch("ticker_bars_push.broadcast_bars_patch", side_effect=lambda _s, p: pushes.append(p)),
            patch("ibkr.bars.fetch_bars_async", new=fetch),
            patch("ibkr.historical_service._pacing.wait_seconds", return_value=0.0),
            patch("ibkr.historical_service._persist_derived"),
            patch("ibkr.historical_service._reschedule_after_wait") as reschedule,
        ):
            try:
                return await request_bars(symbol, timeframe, 500, priority="open_chart"), pushes
            finally:
                assert reschedule.call_count == 0

    return asyncio.run(_run())


def test_a_timeout_is_remembered_with_its_reason_and_time():
    clock = _Clock()
    fetch = AsyncMock(side_effect=HTTPException(status_code=504, detail=TIMEOUT_DETAIL))

    with patch.object(historical_failures, "_now", clock), pytest.raises(HTTPException):
        _request(fetch)

    with patch.object(historical_failures, "_now", clock):
        assert historical_failures.coverage_fields("tlsa", "5Min") == {
            "last_error": TIMEOUT_DETAIL,
            "last_error_ts": T0,
        }
        # Another timeframe of the same symbol has nothing to state.
        assert historical_failures.coverage_fields("TLSA", "1Min") == {
            "last_error": None,
            "last_error_ts": None,
        }


def test_a_retry_inside_the_backoff_is_shed_without_asking_ibkr():
    clock = _Clock()
    fetch = AsyncMock(side_effect=HTTPException(status_code=504, detail=TIMEOUT_DETAIL))

    with patch.object(historical_failures, "_now", clock):
        with pytest.raises(HTTPException):
            _request(fetch)
        clock.now += IBKR_HISTORICAL_FAILURE_BACKOFF_SEC - 1.0
        with pytest.raises(HistoricalShed, match="did not answer"):
            _request(fetch)

    assert fetch.await_count == 1


def test_after_the_backoff_the_pair_is_sent_and_a_success_clears_the_failure():
    clock = _Clock()
    fetch = AsyncMock(side_effect=[
        HTTPException(status_code=504, detail=TIMEOUT_DETAIL),
        _payload("TLSA", "5Min"),
    ])

    with patch.object(historical_failures, "_now", clock):
        with pytest.raises(HTTPException):
            _request(fetch)
        clock.now += IBKR_HISTORICAL_FAILURE_BACKOFF_SEC + 0.1
        result, pushes = _request(fetch)
        cleared = historical_failures.coverage_fields("TLSA", "5Min")

    assert fetch.await_count == 2
    assert cleared == {"last_error": None, "last_error_ts": None}
    # The push that lands the fill states there is no failure any more.
    assert result["coverage"]["last_error"] is None
    assert pushes[0]["coverage"]["last_error"] is None
    assert pushes[0]["coverage"]["last_error_ts"] is None


def test_an_error_answer_is_remembered_but_a_gateway_outage_is_not():
    clock = _Clock()
    with patch.object(historical_failures, "_now", clock):
        with pytest.raises(HTTPException):
            _request(AsyncMock(side_effect=HTTPException(
                status_code=502, detail="IBKR historical data failed: ConnectionError",
            )))
        assert historical_failures.backoff_remaining("TLSA", "5Min") > 0

        reset_for_testing()
        with pytest.raises(HTTPException):
            _request(AsyncMock(side_effect=HTTPException(
                status_code=503, detail="IBKR bars unavailable",
            )))
        # The session's own state, not IBKR failing this pair: no memory, no backoff.
        assert historical_failures.backoff_remaining("TLSA", "5Min") == 0.0
        assert historical_failures.coverage_fields("TLSA", "5Min")["last_error"] is None


def test_the_failure_is_forgotten_after_the_memory_window():
    clock = _Clock()
    with patch.object(historical_failures, "_now", clock):
        historical_failures.note("TLSA", "5Min", TIMEOUT_DETAIL)
        clock.now += IBKR_HISTORICAL_FAILURE_MEMORY_SEC + 1.0
        assert historical_failures.coverage_fields("TLSA", "5Min")["last_error"] is None
        assert historical_failures.backoff_remaining("TLSA", "5Min") == 0.0


def test_a_derived_push_carries_the_derived_panes_own_failure():
    from ibkr.historical_service import _persist_derived

    historical_failures.note("TLSA", "5Min", TIMEOUT_DETAIL)
    one_min = {
        "symbol": "TLSA",
        "bars": [
            {"t": f"2026-09-23T14:{i:02d}:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}
            for i in range(30)
        ],
    }
    pushes: list[dict] = []
    with (
        patch("bars_store.read", return_value=None),
        patch("bars_store.write_payload"),
        patch("ticker_bars_push.broadcast_bars_patch", side_effect=lambda _s, p: pushes.append(p)),
    ):
        asyncio.run(_persist_derived("TLSA", one_min))

    by_tf = {p["timeframe"]: p["coverage"] for p in pushes}
    assert by_tf["5Min"]["last_error"] == TIMEOUT_DETAIL
    assert by_tf["15Min"]["last_error"] is None


def test_bars_coverage_states_the_failure_on_an_empty_pane():
    historical_failures.note("TLSA", "5Min", TIMEOUT_DETAIL)
    with (
        patch.object(chart_bars._ibkr_client, "is_ready", return_value=True),
        patch.object(chart_bars, "_store_read", return_value=None),
        patch.object(chart_bars, "_schedule_ibkr_fill"),
    ):
        out = chart_bars.fetch_chart_bars(
            "TLSA", "5Min", 500, discovery_provider="ibkr", interactive=True,
        )

    assert out["bars"] == []
    assert out["coverage"]["filling"] is True
    assert out["coverage"]["last_error"] == TIMEOUT_DETAIL
    assert isinstance(out["coverage"]["last_error_ts"], float)


def test_bars_coverage_states_the_failure_on_a_painted_pane_and_null_otherwise():
    stored = {
        "symbol": "TLSA",
        "timeframe": "1Hour",
        "bars": [{"t": "2026-09-23T14:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}],
        "source": "ibkr",
        "coverage": {"filling": False, "fresh": False, "fetched_ts": 0.0},
    }
    with (
        patch.object(chart_bars._ibkr_client, "is_ready", return_value=True),
        patch.object(chart_bars, "_store_read", side_effect=lambda *_a: {**stored}),
        patch.object(chart_bars, "_schedule_ibkr_fill"),
    ):
        quiet = chart_bars.fetch_chart_bars(
            "TLSA", "1Hour", 400, discovery_provider="ibkr", interactive=True,
        )
        historical_failures.note("TLSA", "1Hour", TIMEOUT_DETAIL)
        failing = chart_bars.fetch_chart_bars(
            "TLSA", "1Hour", 400, discovery_provider="ibkr", interactive=True,
        )

    assert quiet["coverage"]["last_error"] is None
    assert quiet["coverage"]["last_error_ts"] is None
    assert failing["coverage"]["filling"] is True
    assert failing["coverage"]["last_error"] == TIMEOUT_DETAIL
