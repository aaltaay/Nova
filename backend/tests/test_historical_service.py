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


def test_open_chart_fetches_when_pacing_wait_and_store_has_stub():
    """A 9-bar derived stub must not cancel the real IB fill on pacing wait."""
    fetched = {"n": 0}

    async def fake_fetch(symbol, timeframe, limit, *, interactive=False):
        fetched["n"] += 1
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": [
                {"t": f"2026-07-14T{i:02d}:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}
                for i in range(24)
            ],
            "source": "ibkr",
        }

    stub = {
        "symbol": "AAPL",
        "timeframe": "1Hour",
        "bars": [{"t": "2026-08-18T14:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}] * 9,
        "source": "ibkr",
        "coverage": {"filling": True, "fetched_ts": 1.0, "fresh": False},
    }

    async def _run():
        with (
            patch("bars_store.read", return_value=stub),
            patch("bars_store.store_series_complete", return_value=True),
            patch("bars_store.is_coverage_fresh", return_value=False),
            patch("bars_store.write_payload"),
            patch("bars_store.coverage_from_bars", return_value={"filling": False}),
            patch("ticker_bars_push.broadcast_bars_patch"),
            patch(
                "ibkr.historical_service._pacing.wait_seconds",
                return_value=2.0,
            ),
            patch("ibkr.bars.fetch_bars_async", new=AsyncMock(side_effect=fake_fetch)),
            patch("ibkr.historical_service._persist_derived"),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            await request_bars("AAPL", "1Hour", 400, priority="open_chart")

    asyncio.run(_run())
    assert fetched["n"] == 1


def test_background_sheds_when_pacing_wait_and_store_has_bars():
    fetched = {"n": 0}

    async def fake_fetch(symbol, timeframe, limit, *, interactive=False):
        fetched["n"] += 1
        return _payload(symbol, timeframe)

    stub = {
        "symbol": "AAPL",
        "timeframe": "1Hour",
        "bars": [{"t": "2026-08-18T14:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}],
        "source": "ibkr",
        "coverage": {"filling": True, "fetched_ts": 1.0},
    }

    async def _run():
        with (
            patch("bars_store.read", return_value=stub),
            patch("bars_store.store_series_complete", return_value=True),
            patch("bars_store.is_coverage_fresh", return_value=False),
            patch("ibkr.historical_service._pacing.wait_seconds", return_value=2.0),
            patch("ibkr.bars.fetch_bars_async", new=AsyncMock(side_effect=fake_fetch)),
        ):
            with pytest.raises(HistoricalShed):
                await request_bars("AAPL", "1Hour", 400, priority="background")

    asyncio.run(_run())
    assert fetched["n"] == 0


def test_warm_sheds_when_pacing_wait_and_store_has_bars():
    """Warm prefetch must not burn the 60/10-min bucket when pacing says wait."""
    fetched = {"n": 0}

    async def fake_fetch(symbol, timeframe, limit, *, interactive=False):
        fetched["n"] += 1
        return _payload(symbol, timeframe)

    stub = {
        "symbol": "AAPL",
        "timeframe": "1Hour",
        "bars": [{"t": "2026-08-18T14:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}],
        "source": "ibkr",
        "coverage": {"filling": True, "fetched_ts": 1.0},
    }

    async def _run():
        with (
            patch("bars_store.read", return_value=stub),
            patch("bars_store.store_series_complete", return_value=True),
            patch("bars_store.is_coverage_fresh", return_value=False),
            patch("ibkr.historical_service._pacing.wait_seconds", return_value=2.0),
            patch("ibkr.bars.fetch_bars_async", new=AsyncMock(side_effect=fake_fetch)),
        ):
            with pytest.raises(HistoricalShed):
                await request_bars("AAPL", "1Hour", 400, priority="warm")

    asyncio.run(_run())
    assert fetched["n"] == 0


def test_open_chart_does_not_send_when_global_bucket_wait_exceeds_cap():
    """A 333s pacing debt must not become sleep(16) + send. Reschedule instead."""
    fetched = {"n": 0}
    rescheduled: list[tuple[str, str]] = []

    async def fake_fetch(symbol, timeframe, limit, *, interactive=False):
        fetched["n"] += 1
        return _payload(symbol, timeframe)

    stub = {
        "symbol": "AAPL",
        "timeframe": "1Hour",
        "bars": [{"t": "2026-08-18T14:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}] * 9,
        "source": "ibkr",
        "coverage": {"filling": True, "fetched_ts": 1.0, "fresh": False},
    }

    async def _run():
        with (
            patch("bars_store.read", return_value=stub),
            patch("bars_store.store_series_complete", return_value=True),
            patch("bars_store.is_coverage_fresh", return_value=False),
            patch("ibkr.historical_service._pacing.wait_seconds", return_value=333.0),
            patch("ibkr.bars.fetch_bars_async", new=AsyncMock(side_effect=fake_fetch)),
            patch(
                "ibkr.historical_service._reschedule_after_wait",
                side_effect=lambda sym, tf, lim, pri, wait: rescheduled.append((sym, tf)),
            ),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            with pytest.raises(HistoricalShed):
                await request_bars("AAPL", "1Hour", 400, priority="open_chart")

    asyncio.run(_run())
    assert fetched["n"] == 0
    assert rescheduled == [("AAPL", "1Hour")]


def test_historical_pacing_snapshot():
    import ibkr.historical_service as hs

    hs._pacing.record("AAPL", "1Day", "5 Y")
    hs._pacing.record("MSFT", "1Day", "5 Y")
    hs._pacing.record("TSLA", "1Day", "5 Y")

    snap = hs.pacing_snapshot()
    assert snap["window_used"] == 3
    assert snap["window_max"] == 60
    assert snap["next_token_wait_sec"] == 0.0
    assert snap["identical_keys"] == 3
    assert snap["contract_hot"] == []


def test_persist_derived_skips_when_store_already_longer():
    from ibkr.historical_service import _persist_derived

    one_min = {
        "symbol": "AAPL",
        "bars": [
            {
                "t": f"2026-08-18T14:{i:02d}:00Z",
                "o": 1, "h": 1, "l": 1, "c": 1, "v": 1,
            }
            for i in range(60)
        ],
    }
    stored = [{"t": f"t{i}", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1} for i in range(200)]
    writes: list[dict] = []

    def fake_read(_symbol, _timeframe, limit):
        return {"bars": stored[: max(1, int(limit))]}

    with (
        patch("bars_store.read", side_effect=fake_read),
        patch("bars_store.write_payload", side_effect=writes.append),
        patch("bars_store.coverage_from_bars", return_value={"filling": True}),
        patch("ticker_bars_push.broadcast_bars_patch"),
    ):
        _persist_derived("AAPL", one_min)

    assert writes == []
