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
