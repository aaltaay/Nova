"""Tests for IBKR bars TTL cache + single-flight (no stale serving)."""
from __future__ import annotations

import asyncio
import os
import sys
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ibkr import bars_cache  # noqa: E402
import chart_bars  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_cache():
    bars_cache.clear_for_tests()
    yield
    bars_cache.clear_for_tests()


def _payload(symbol="AAPL", timeframe="1Min", n=3):
    bars = [
        {"t": f"2026-07-29T14:0{i}:00Z", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 100 + i}
        for i in range(n)
    ]
    return {"symbol": symbol, "timeframe": timeframe, "bars": bars, "source": "ibkr"}


def test_get_cached_miss_when_empty():
    assert bars_cache.get_cached("AAPL", "1Min", 10) is None


def test_put_and_get_hit_trims_to_limit():
    bars_cache.put_cached(_payload(n=5))
    hit = bars_cache.get_cached("AAPL", "1Min", 2)
    assert hit is not None
    assert hit["cache"] == "hit"
    assert len(hit["bars"]) == 2
    assert hit["bars"][-1]["v"] == 104


def test_expired_entry_never_served():
    bars_cache.put_cached(_payload())
    key = bars_cache._cache_key("AAPL", "1Min")
    with bars_cache._store_lock:
        payload = bars_cache._entries[key][1]
        bars_cache._entries[key] = (time.monotonic() - 1.0, payload)
    assert bars_cache.get_cached("AAPL", "1Min", 10) is None


def test_insufficient_bars_is_miss():
    bars_cache.put_cached(_payload(n=2))
    assert bars_cache.get_cached("AAPL", "1Min", 10) is None


def test_get_or_fetch_hits_cache_without_calling_fetch():
    bars_cache.put_cached(_payload(n=5))
    fetch_fn = AsyncMock(side_effect=AssertionError("must not fetch"))

    async def _run():
        return await bars_cache.get_or_fetch(
            "AAPL", "1Min", 3, interactive=True, fetch_fn=fetch_fn,
        )

    out = asyncio.run(_run())
    assert out["cache"] == "hit"
    assert len(out["bars"]) == 3
    fetch_fn.assert_not_called()


def test_get_or_fetch_miss_calls_fetch_and_caches():
    fetch_fn = AsyncMock(return_value=_payload(n=4))

    async def _run():
        return await bars_cache.get_or_fetch(
            "AAPL", "1Min", 4, interactive=True, fetch_fn=fetch_fn,
        )

    out = asyncio.run(_run())
    assert out["cache"] == "miss"
    fetch_fn.assert_awaited_once()
    hit = bars_cache.get_cached("AAPL", "1Min", 4)
    assert hit is not None
    assert hit["cache"] == "hit"


def test_get_or_fetch_single_flight_coalesces():
    started = asyncio.Event()
    release = asyncio.Event()
    calls = {"n": 0}

    async def slow_fetch(symbol, timeframe, limit, *, interactive=False):
        calls["n"] += 1
        started.set()
        await release.wait()
        return _payload(symbol=symbol, timeframe=timeframe, n=limit)

    async def _run():
        t1 = asyncio.create_task(
            bars_cache.get_or_fetch(
                "AAPL", "1Min", 3, interactive=True, fetch_fn=slow_fetch,
            )
        )
        await started.wait()
        t2 = asyncio.create_task(
            bars_cache.get_or_fetch(
                "AAPL", "1Min", 3, interactive=True, fetch_fn=slow_fetch,
            )
        )
        # Let the second task attach to inflight before releasing the winner.
        await asyncio.sleep(0)
        release.set()
        a, b = await asyncio.gather(t1, t2)
        return a, b

    a, b = asyncio.run(_run())
    assert calls["n"] == 1
    assert a["cache"] == "miss"
    assert b["cache"] == "coalesce"
    assert len(a["bars"]) == 3
    assert len(b["bars"]) == 3


def test_get_or_fetch_failure_not_cached_and_reraises():
    async def boom(*_a, **_k):
        raise HTTPException(status_code=503, detail="IBKR historical busy")

    async def _run():
        with pytest.raises(HTTPException) as ei:
            await bars_cache.get_or_fetch(
                "AAPL", "1Min", 3, interactive=True, fetch_fn=boom,
            )
        return ei.value

    exc = asyncio.run(_run())
    assert exc.status_code == 503
    assert bars_cache.get_cached("AAPL", "1Min", 3) is None


def test_parse_batch_timeframes_default_and_invalid():
    assert chart_bars.parse_batch_timeframes(None) == [
        "1Min", "5Min", "15Min", "1Day",
    ]
    assert chart_bars.parse_batch_timeframes("1Min,5Min,1Min") == ["1Min", "5Min"]
    with pytest.raises(HTTPException) as ei:
        chart_bars.parse_batch_timeframes("1Min,nope")
    assert ei.value.status_code == 400


def test_fetch_chart_bars_batch_collects_errors_without_stale_fill():
    def _fake(symbol, timeframe, limit, *, discovery_provider, interactive=False):
        if timeframe == "5Min":
            raise HTTPException(status_code=503, detail="timed out")
        return _payload(symbol=symbol, timeframe=timeframe, n=2)

    with patch.object(chart_bars, "fetch_chart_bars", side_effect=_fake):
        out = chart_bars.fetch_chart_bars_batch(
            "NUWE",
            ["1Min", "5Min"],
            10,
            discovery_provider="ibkr",
            interactive=True,
        )
    assert "1Min" in out["results"]
    assert out["results"]["1Min"]["source"] == "ibkr"
    assert out["errors"]["5Min"]["status_code"] == 503
    assert "5Min" not in out["results"]
