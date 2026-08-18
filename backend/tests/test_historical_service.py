"""Paced historical service: concurrency, dedup, background shed."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from ibkr.historical_service import (
    HistoricalShed,
    open_chart_busy,
    request_bars,
    reset_for_testing,
)


def _payload(symbol, timeframe="1Min"):
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": [{"t": "2026-08-18T14:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}],
        "source": "ibkr",
    }


@pytest.fixture(autouse=True)
def _reset():
    reset_for_testing()
    yield
    reset_for_testing()


def test_allows_three_concurrent_and_dedupes_same_key():
    current = 0
    max_current = 0
    release = asyncio.Event()
    calls = {"n": 0}

    async def fake_fetch(symbol, timeframe, limit, *, interactive=False):
        nonlocal current, max_current
        calls["n"] += 1
        current += 1
        max_current = max(max_current, current)
        await release.wait()
        current -= 1
        return _payload(symbol, timeframe)

    async def _run():
        with (
            patch("bars_store.read", return_value=None),
            patch("bars_store.write_payload"),
            patch("bars_store.coverage_from_bars", return_value={"filling": False}),
            patch("ticker_bars_push.broadcast_bars_patch"),
            patch("ibkr.bars.fetch_bars_async", new=AsyncMock(side_effect=fake_fetch)),
            patch("ibkr.historical_service._persist_derived"),
        ):
            tasks = [
                asyncio.create_task(request_bars(f"S{i}", "1Min", 10, priority="open_chart"))
                for i in range(3)
            ]
            dup = asyncio.create_task(request_bars("S0", "1Min", 10, priority="open_chart"))
            fourth = asyncio.create_task(request_bars("S9", "1Min", 10, priority="open_chart"))
            await asyncio.sleep(0.05)
            assert max_current == 3
            assert open_chart_busy()
            release.set()
            await asyncio.gather(*tasks, dup, fourth)
        return calls["n"], max_current

    n, peak = asyncio.run(_run())
    assert peak == 3
    # S0 coalesced; S1 S2 S9 each fetch -- 4 sends, not 5
    assert n == 4


def test_background_shed_while_open_chart_inflight():
    release = asyncio.Event()
    started = asyncio.Event()

    async def fake_fetch(symbol, timeframe, limit, *, interactive=False):
        started.set()
        await release.wait()
        return _payload(symbol, timeframe)

    async def _run():
        with (
            patch("bars_store.read", return_value=None),
            patch("bars_store.write_payload"),
            patch("bars_store.coverage_from_bars", return_value={"filling": False}),
            patch("ticker_bars_push.broadcast_bars_patch"),
            patch("ibkr.bars.fetch_bars_async", new=AsyncMock(side_effect=fake_fetch)),
            patch("ibkr.historical_service._persist_derived"),
        ):
            chart = asyncio.create_task(
                request_bars("AIXC", "1Min", 10, priority="open_chart"),
            )
            await started.wait()
            with pytest.raises(HistoricalShed):
                await request_bars("SEED", "1Min", 10, priority="background")
            release.set()
            await chart

    asyncio.run(_run())
