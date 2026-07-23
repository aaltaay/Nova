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
    """reqScannerDataAsync must be locally bounded — an unbounded hang used
    to be indistinguishable from any other cause of the outer bridge
    timeout (see PROBLEM_LOG 2026-07-23)."""

    class _HangingIB:
        async def reqScannerDataAsync(self, _subscription):
            await asyncio.sleep(60)

    monkeypatch.setattr(discovery._client, "get_ib", lambda: _HangingIB())
    monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)
    monkeypatch.setattr(discovery, "IBKR_SCAN_REQUEST_TIMEOUT_SEC", 0.05)

    class _Sub:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.belowPrice = None

    monkeypatch.setattr(discovery, "_ScannerSubscription", _Sub)
    discovery.reset_scan_cache()

    with pytest.raises(IbkrDiscoveryError, match="timed out"):
        await discovery.scan_symbols("TOP_PERC_GAIN")


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
