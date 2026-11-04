"""Paced historical service: concurrency, dedup, background shed."""
from __future__ import annotations

import asyncio
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, patch

import pytest

from constants import (
    IBKR_HISTORICAL_PACE_MAX,
    IBKR_HISTORICAL_SLOW_COUNT,
    IBKR_HISTORICAL_SMALL_PACE_MAX,
    IBKR_HISTORY_WARM_RESERVE,
)
from ibkr.historical_service import (
    HistoricalShed,
    budget,
    open_chart_busy,
    pacing_refusals,
    pacing_snapshot,
    refused_for_pacing,
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


def test_open_chart_reschedules_short_pacing_wait_instead_of_sleeping():
    """A 2s same-contract wait reschedules -- it must not sleep on the IB loop."""
    fetched = {"n": 0}
    rescheduled: list[tuple[str, str, float]] = []
    slept: list[float] = []

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

    async def fake_sleep(delay, *args, **kwargs):
        slept.append(float(delay))

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
            patch(
                "ibkr.historical_service._reschedule_after_wait",
                side_effect=lambda sym, tf, lim, pri, wait: rescheduled.append(
                    (sym, tf, wait),
                ),
            ),
            patch("asyncio.sleep", new=fake_sleep),
        ):
            with pytest.raises(HistoricalShed):
                await request_bars("AAPL", "1Hour", 400, priority="open_chart")

    asyncio.run(_run())
    assert fetched["n"] == 0
    assert rescheduled == [("AAPL", "1Hour", 2.0)]
    assert slept == []


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
    """Warm prefetch must not burn the 10-minute bucket when pacing says wait."""
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


def test_a_pair_waiting_out_a_pacing_wait_gets_one_wake():
    """A waiting pane asks again every few seconds; each ask used to queue its own wake, and a series the
    fill leaves short (a quiet name's 10-second bars) was sent once per wake when the window freed."""
    import ibkr.historical_service as hs

    class _Loop:
        def __init__(self):
            self.wakes = []

        def is_running(self):
            return True

        def call_later(self, delay, callback):
            self.wakes.append((delay, callback))

    loop = _Loop()
    with patch("ibkr.loop_supervisor.get_loop", return_value=loop), \
            patch("ibkr.historical_service.schedule_fill") as fill:
        for _ in range(3):
            hs._reschedule_after_wait("riox", "10Sec", 1500, "open_chart", 40.0)
        hs._reschedule_after_wait("RIOX", "1Min", 1000, "open_chart", 40.0)
        assert [delay for delay, _ in loop.wakes] == [40.0, 40.0]
        loop.wakes[0][1]()
        fill.assert_called_once_with("riox", "10Sec", 1500, priority="open_chart")
        hs._reschedule_after_wait("RIOX", "10Sec", 1500, "open_chart", 5.0)  # woken: a new wait waits again
    assert len(loop.wakes) == 3


def test_historical_pacing_snapshot():
    import ibkr.historical_service as hs

    hs._pacing.record("AAPL", "1Day", "5 Y")
    hs._pacing.record("MSFT", "1Day", "5 Y")
    hs._pacing.record("TSLA", "1Day", "5 Y")

    snap = hs.pacing_snapshot()
    assert snap["window_used"] == 3
    assert snap["window_max"] == IBKR_HISTORICAL_PACE_MAX
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
        asyncio.run(_persist_derived("AAPL", one_min))

    assert writes == []


def test_rth_daily_closes_are_paced_and_read_the_regular_session():
    """ADR 040: regular-hours daily closes go through the same pacing, and a repeat inside the window sheds."""
    from datetime import date
    from types import SimpleNamespace

    import ibkr.historical_service as hs

    calls = []

    class _IB:
        async def qualifyContractsAsync(self, contract):
            return [None, contract]

        async def reqHistoricalDataAsync(self, contract, **kwargs):
            calls.append(kwargs)
            return [SimpleNamespace(date=date(2026, 9, 28), close=20.5),
                    SimpleNamespace(date=date(2026, 9, 29), close=21.34),
                    SimpleNamespace(date=date(2026, 9, 30), close=float("nan"))]

    with patch("ibkr.client.get_ib", return_value=_IB()):
        rows = asyncio.run(hs.request_rth_daily_closes("mara", "6 M"))
        assert rows == [("2026-09-28", 20.5), ("2026-09-29", 21.34)]
        assert calls[0]["useRTH"] is True and calls[0]["barSizeSetting"] == "1 day"
        with pytest.raises(HistoricalShed):
            asyncio.run(hs.request_rth_daily_closes("MARA", "6 M"))   # the identical request, too soon


@contextmanager
def _ibkr_answers():
    """An empty store, and IBKR answering every fill."""
    async def fetch(symbol, timeframe, limit, *, interactive=False):
        return _payload(symbol, timeframe)

    with ExitStack() as stack:
        stack.enter_context(patch("bars_store.read", return_value=None))
        stack.enter_context(patch("bars_store.write_payload"))
        stack.enter_context(patch("bars_store.coverage_from_bars", return_value={"filling": False}))
        stack.enter_context(patch("ticker_bars_push.broadcast_bars_patch"))
        stack.enter_context(patch("ibkr.bars.fetch_bars_async", new=AsyncMock(side_effect=fetch)))
        stack.enter_context(patch("ibkr.historical_service._persist_derived"))
        yield


def _spent(key, count):
    pacing, _slots = budget()
    for k in range(count):
        pacing.record(f"S{k}", key, "1 D")
    return pacing


def test_a_painted_chart_refreshes_past_the_published_sixty():
    """2026-11-04: Nova's own 60 held a chart back 683 s while IBKR answered in 0.2 s; 1-minute bars are not its 60."""
    _spent("1Min", IBKR_HISTORICAL_SMALL_PACE_MAX)
    with _ibkr_answers():
        got = asyncio.run(request_bars("AAPL", "1Min", 10, priority="warm"))
    assert got["bars"]


def test_a_painted_ten_second_chart_leaves_the_end_of_the_sixty():
    _spent("10Sec", IBKR_HISTORICAL_SMALL_PACE_MAX - IBKR_HISTORY_WARM_RESERVE)
    with _ibkr_answers(), pytest.raises(HistoricalShed, match="the trades read back"):
        asyncio.run(request_bars("AAPL", "10Sec", 10, priority="warm"))


def test_a_stock_opened_on_the_busiest_desk_still_sends_at_once():
    """2026-11-04 08:24: CRIS's 1-minute chart landed 683 s after it opened, behind the desk's own refreshes."""
    _spent("1Min", IBKR_HISTORICAL_PACE_MAX - IBKR_HISTORY_WARM_RESERVE)     # where every painted chart has stopped
    with _ibkr_answers():
        with pytest.raises(HistoricalShed, match="the trades read back"):
            asyncio.run(request_bars("AAPL", "1Min", 10, priority="warm"))
        got = asyncio.run(request_bars("CRIS", "1Min", 10, priority="open_chart"))
    assert got["bars"]


def test_a_hold_stops_a_painted_chart_and_never_an_open_one():
    _spent("1Min", IBKR_HISTORICAL_SMALL_PACE_MAX)
    refused_for_pacing("Historical data request pacing violation")
    with _ibkr_answers():
        with pytest.raises(HistoricalShed, match="the trades read back"):
            asyncio.run(request_bars("AAPL", "1Min", 10, priority="warm"))
        got = asyncio.run(request_bars("AAPL", "1Min", 10, priority="open_chart"))
    assert got["bars"]
    assert pacing_refusals() == 1


def test_answers_that_slow_hold_the_window_as_ibkrs_word_does():
    async def _run():
        for k in range(IBKR_HISTORICAL_SLOW_COUNT):
            assert pacing_snapshot()["held_sec"] == 0
            await request_bars(f"S{k}", "1Min", 10, priority="open_chart")

    with _ibkr_answers(), patch("ibkr.historical_pacing.IBKR_HISTORICAL_SLOW_SEC", 0.0):
        asyncio.run(_run())
    assert pacing_snapshot()["held_sec"] > 0
    assert pacing_snapshot()["window_max"] == IBKR_HISTORICAL_SMALL_PACE_MAX
    assert pacing_refusals() == 0
