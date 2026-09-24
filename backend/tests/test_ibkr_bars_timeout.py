"""An IBKR historical timeout is a failure, never "no bars" (2026-09-23).

ib_async answers a timed-out ``reqHistoricalDataAsync`` with an empty list.
Nova used to take that as IBKR's answer: the empty payload was cached (15 min
for 1Day), written to the store as a finished fill and pushed as an empty
``bars_patch`` that wiped a painted pane.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from ibkr import bars, bars_cache
from ibkr.historical_service import request_bars, reset_for_testing


@pytest.fixture(autouse=True)
def _reset():
    bars_cache.clear_for_tests()
    reset_for_testing()
    yield
    bars_cache.clear_for_tests()
    reset_for_testing()


def _fake_ib(monkeypatch, answer_after_sec: float):
    contract = SimpleNamespace(symbol="AAPL")

    class _IB:
        async def qualifyContractsAsync(self, _contract):
            return [contract]

        async def reqHistoricalDataAsync(self, *_args, **_kwargs):
            await asyncio.sleep(answer_after_sec)
            return []

    monkeypatch.setattr(bars, "_load_ib_types", lambda: True)
    monkeypatch.setattr(bars, "_Stock", lambda *_args: contract)
    monkeypatch.setattr(bars._client, "get_ib", lambda: _IB())


def test_timed_out_only_when_the_empty_answer_took_the_whole_timeout():
    assert bars.historical_timed_out(20.0, 20.0)
    assert bars.historical_timed_out(19.6, 20.0)
    assert not bars.historical_timed_out(19.0, 20.0)
    assert not bars.historical_timed_out(0.3, 20.0)
    assert not bars.historical_timed_out(5.0, 0.0)  # no timeout set: nothing timed out


def test_timeout_raises_and_is_not_cached(monkeypatch):
    _fake_ib(monkeypatch, answer_after_sec=0.06)
    monkeypatch.setattr(bars, "IBKR_HISTORICAL_BACKGROUND_TIMEOUT_SEC", 0.05)
    monkeypatch.setattr(bars, "IBKR_HISTORICAL_TIMEOUT_SLACK_SEC", 0.01)

    with pytest.raises(HTTPException) as err:
        asyncio.run(bars.fetch_bars_async("AAPL", "1Day"))

    assert err.value.status_code == 504
    assert bars_cache.get_cached("AAPL", "1Day", 500) is None


def test_quick_empty_answer_is_still_no_bars(monkeypatch):
    """A real "no data" answer comes back fast: that stays a stated absence."""
    _fake_ib(monkeypatch, answer_after_sec=0.0)

    payload = asyncio.run(bars.fetch_bars_async("AAPL", "1Day"))

    assert payload["bars"] == []


def test_failed_fill_writes_nothing_and_pushes_nothing():
    timeout = HTTPException(status_code=504, detail="IBKR historical data did not answer within 20s")

    async def _run():
        with (
            patch("bars_store.read", return_value=None),
            patch("bars_store.write_payload") as write,
            patch("ticker_bars_push.broadcast_bars_patch") as push,
            patch("ibkr.bars.fetch_bars_async", new=AsyncMock(side_effect=timeout)),
        ):
            with pytest.raises(HTTPException):
                await request_bars("AAPL", "1Day", 500, priority="open_chart")
            return write.call_count, push.call_count

    writes, pushes = asyncio.run(_run())
    assert writes == 0
    assert pushes == 0
