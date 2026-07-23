"""IB discovery must raise on transport failure — never disguise as []."""
from __future__ import annotations

import asyncio

import pytest

from ibkr import discovery as discovery
from ibkr.errors import IbkrDiscoveryError
import hod_momo_universe as uni


@pytest.mark.asyncio
async def test_scan_symbols_raises_when_disconnected(monkeypatch):
    monkeypatch.setattr(discovery._client, "get_ib", lambda: None)
    with pytest.raises(IbkrDiscoveryError, match="not connected"):
        await discovery.scan_symbols("TOP_PERC_GAIN")


@pytest.mark.asyncio
async def test_scan_symbols_raises_on_scanner_request_timeout(monkeypatch):
    """One-shot scanner must time out without leaking the IBKR subscription.

    Wrapping ``reqScannerDataAsync`` in ``asyncio.wait_for`` used to abandon
    the await on timeout *before* ib_async's cancel ran — leaking toward
    Error 322 (max 10 simultaneous API scanner subscriptions).
    """
    cancelled: list[object] = []

    class _DataList:
        def __init__(self):
            self.reqId = 42

    class _Wrapper:
        def startReq(self, req_id, container=None):
            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            # Never complete — forces the local wait_for timeout path.
            return fut

    class _HangingIB:
        def __init__(self):
            self.wrapper = _Wrapper()
            self.client = self

        def reqScannerSubscription(self, _subscription, *_a, **_k):
            return _DataList()

        def cancelScannerSubscription(self, data_list):
            cancelled.append(data_list.reqId)

        def cancelScannerSubscription_client(self, req_id):
            cancelled.append(req_id)

    monkeypatch.setattr(discovery._client, "get_ib", lambda: _HangingIB())
    monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)
    monkeypatch.setattr(discovery, "IBKR_SCAN_REQUEST_TIMEOUT_SEC", 0.05)

    class _Sub:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.belowPrice = None

    monkeypatch.setattr(discovery, "_ScannerSubscription", _Sub)
    discovery.reset_scan_cache()
    discovery._scan_lock = None

    with pytest.raises(IbkrDiscoveryError, match="timed out"):
        await discovery.scan_symbols("TOP_PERC_GAIN")

    assert cancelled == [42], "timeout must cancel the scanner subscription"


@pytest.mark.asyncio
async def test_scan_symbols_cancels_subscription_on_success(monkeypatch):
    cancelled: list[int] = []

    class _Row:
        class contractDetails:
            class contract:
                symbol = "AAA"

    class _DataList:
        def __init__(self):
            self.reqId = 7

    class _Wrapper:
        def startReq(self, req_id, container=None):
            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            fut.set_result([_Row()])
            return fut

    class _IB:
        def __init__(self):
            self.wrapper = _Wrapper()

        def reqScannerSubscription(self, _subscription, *_a, **_k):
            return _DataList()

        def cancelScannerSubscription(self, data_list):
            cancelled.append(data_list.reqId)

    monkeypatch.setattr(discovery._client, "get_ib", lambda: _IB())
    monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)

    class _Sub:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.belowPrice = None

    monkeypatch.setattr(discovery, "_ScannerSubscription", _Sub)
    discovery.reset_scan_cache()
    discovery._scan_lock = None

    symbols = await discovery.scan_symbols("TOP_PERC_GAIN")
    assert symbols == ["AAA"]
    assert cancelled == [7]


@pytest.mark.asyncio
async def test_snapshot_require_success_raises_on_qualify_timeout(monkeypatch):
    """qualifyContractsAsync must be locally bounded too — an unbounded batch
    qualify on the discovery/table-reprice path is the same wedge risk
    ibkr/ticks.py already guards against for single-symbol L1 subscribes."""

    class _HangingIB:
        async def qualifyContractsAsync(self, *_contracts):
            await asyncio.sleep(60)

    monkeypatch.setattr(discovery._client, "get_ib", lambda: _HangingIB())
    monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)
    monkeypatch.setattr(discovery, "IBKR_DISCOVERY_QUALIFY_TIMEOUT_SEC", 0.05)
    monkeypatch.setattr(discovery, "_Stock", lambda *a, **k: object())
    discovery._qualified_contracts.clear()

    with pytest.raises(IbkrDiscoveryError, match="qualify batch timed out"):
        await discovery.snapshot_quotes(["AAA"], require_success=True)


@pytest.mark.asyncio
async def test_snapshot_require_success_raises_on_timeout(monkeypatch):
    class _IB:
        async def reqTickersAsync(self, *_a, **_k):
            raise asyncio.TimeoutError()

    monkeypatch.setattr(discovery._client, "get_ib", lambda: _IB())
    monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)
    discovery._qualified_contracts.clear()
    discovery._qualified_contracts["AAA"] = object()

    class _Lock:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

    monkeypatch.setattr(discovery, "_get_snapshot_lock", lambda: _Lock())

    with pytest.raises(IbkrDiscoveryError, match="snapshot timeout"):
        await discovery.snapshot_quotes(["AAA"], require_success=True)


def test_set_seed_symbols_refuses_empty_wipe():
    uni.set_seed_symbols(["AAA", "BBB"], allow_empty=True)
    assert uni.get_seed_symbols() == ["AAA", "BBB"]
    assert uni.set_seed_symbols([]) is False
    assert uni.get_seed_symbols() == ["AAA", "BBB"]
    assert uni.set_seed_symbols([], allow_empty=True) is True
    assert uni.get_seed_symbols() == []
