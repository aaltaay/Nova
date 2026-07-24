"""Market-data operation metrics add no broker requests and count failures."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from ibkr import bars, discovery, scanner_hydrate, scanner_stream
from metrics import op_metrics


@pytest.fixture(autouse=True)
def reset_metrics_and_caches():
    op_metrics.reset_for_tests()
    discovery.reset_scan_cache()
    discovery._qualified_contracts.clear()
    discovery._scan_lock = None
    discovery._snapshot_lock = None
    yield
    op_metrics.reset_for_tests()


class _ScannerSubscription:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_persistent_scanner_subscribe_is_measured_once(monkeypatch):
    class _Event:
        def __iadd__(self, _listener):
            return self

        def __isub__(self, _listener):
            return self

    class _DataList(list):
        reqId = 77
        updateEvent = _Event()

    class _IB:
        def __init__(self):
            self.calls = 0

        def reqScannerSubscription(self, _sub):
            self.calls += 1
            return _DataList()

    async def skip_first_batch_wait(awaitable, **_kwargs):
        awaitable.close()
        return None

    ib = _IB()
    scanner_stream._leases.clear()
    scanner_stream._persistent_reqids.clear()
    monkeypatch.setattr(scanner_stream, "_load_types", lambda: True)
    monkeypatch.setattr(scanner_stream, "_ScannerSubscription", _ScannerSubscription)
    monkeypatch.setattr(scanner_stream._client, "get_ib", lambda: ib)
    monkeypatch.setattr(scanner_stream._client, "is_ready", lambda: True)
    monkeypatch.setattr(scanner_stream._client, "current_generation", lambda: 1)
    monkeypatch.setattr(scanner_stream._session, "session_key_et", lambda: "2026-07-23")
    monkeypatch.setattr(scanner_stream.asyncio, "wait_for", skip_first_batch_wait)

    lease = asyncio.run(scanner_stream._open_lease("gainers", "TOP_PERC_GAIN"))

    assert lease is not None
    assert ib.calls == 1
    stats = op_metrics.snapshot()["operations"]["ibkr.scanner.persistent_subscribe"]
    assert stats["count"] == 1
    assert stats["error_count"] == 0
    scanner_stream._leases.clear()
    scanner_stream._persistent_reqids.clear()


def test_snapshot_request_measured_once(monkeypatch):
    contract = SimpleNamespace(symbol="AAPL")
    calls = 0

    class _IB:
        async def reqTickersAsync(self, *contracts):
            nonlocal calls
            calls += 1
            assert contracts == (contract,)
            return [SimpleNamespace(
                contract=contract, last=10.0, close=9.0, open=9.5,
                volume=100, exchange="NASDAQ",
            )]

    discovery._qualified_contracts["AAPL"] = contract
    monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)
    monkeypatch.setattr(discovery._client, "get_ib", lambda: _IB())

    result = asyncio.run(discovery.snapshot_quotes(["AAPL"], require_success=True))
    assert result["AAPL"]["price"] == 10.0
    assert calls == 1
    assert op_metrics.snapshot()["operations"]["ibkr.snapshot_quotes"]["count"] == 1


def test_historical_request_failure_measured_once(monkeypatch):
    calls = 0
    contract = SimpleNamespace(symbol="AAPL")

    class _IB:
        async def qualifyContractsAsync(self, _contract):
            return [contract]

        async def reqHistoricalDataAsync(self, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            raise RuntimeError("historical failed")

    monkeypatch.setattr(bars, "_load_ib_types", lambda: True)
    monkeypatch.setattr(bars, "_Stock", lambda *_args: contract)
    monkeypatch.setattr(bars._client, "get_ib", lambda: _IB())

    with pytest.raises(HTTPException):
        asyncio.run(bars.fetch_bars_async("AAPL"))
    assert calls == 1
    assert op_metrics.snapshot()["operations"]["ibkr.historical_bars"]["error_count"] == 1


def test_hydration_and_pipeline_metrics_include_error_paths(monkeypatch):
    state = SimpleNamespace()
    monkeypatch.setattr(scanner_hydrate, "get_runtime_state", lambda: state)
    monkeypatch.setattr(scanner_hydrate._client, "current_generation", lambda: 1)
    monkeypatch.setattr(scanner_hydrate._session, "can_commit_roster", lambda *_a, **_k: True)
    monkeypatch.setattr(scanner_hydrate._session, "is_persistent_authoritative", lambda: False)

    async def hydrate(*_args, **_kwargs):
        return [{"symbol": "AAPL"}]

    monkeypatch.setattr(scanner_hydrate, "hydrate_rows", hydrate)
    committed = asyncio.run(scanner_hydrate.commit_table(
        table="gainers",
        symbols=["AAPL"],
        lease_generation=1,
        lease_epoch=1,
        lease_session_key="2026-07-23",
        epoch=1,
        shadow={},
    ))
    assert committed is True
    assert op_metrics.snapshot()["operations"]["ibkr.scanner.hydrate"]["count"] == 1

    scanner_stream._leases["gainers"] = SimpleNamespace(
        generation=1, epoch=1, session_key="2026-07-23",
    )
    scanner_stream._pending_hydrate["gainers"] = (
        ["AAPL"], scanner_stream.time.perf_counter_ns(),
    )

    async def commit_ok(**_kwargs):
        return True

    monkeypatch.setattr(scanner_stream._hydrate, "commit_table", commit_ok)
    asyncio.run(scanner_stream._hydrate_pending())

    scanner_stream._pending_hydrate["gainers"] = (
        ["MSFT"], scanner_stream.time.perf_counter_ns(),
    )

    async def fail_commit(**_kwargs):
        raise RuntimeError("hydrate failed")

    monkeypatch.setattr(scanner_stream._hydrate, "commit_table", fail_commit)
    asyncio.run(scanner_stream._hydrate_pending())
    pipeline = op_metrics.snapshot()["operations"]["ibkr.scanner.pipeline"]
    assert pipeline["count"] == 2
    assert pipeline["error_count"] == 1
    scanner_stream._leases.clear()
    scanner_stream._pending_hydrate.clear()
