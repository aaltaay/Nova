"""A one-shot scan always cancels the subscription it sent.

Regression 2026-10-23: the Market page's movers scan called
``discovery._one_shot_scanner`` before anything had run ``_load_ib_types``.
``_open_scan_future`` raised after ``reqScannerSubscription`` had gone out and
before the ``try`` whose ``finally`` cancels it, so every refresh leaked one of
IBKR's ten scanner slots; by 04:00 the Gainers lease was refused (Error 322).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from ibkr import discovery
from ibkr.errors import IbkrDiscoveryError


class _IB:
    def __init__(self, wrapper) -> None:
        self.wrapper = wrapper
        self.cancelled: list[int] = []

    def reqScannerSubscription(self, _sub):
        return SimpleNamespace(reqId=77)

    def cancelScannerSubscription(self, data_list) -> None:
        self.cancelled.append(data_list.reqId)


@pytest.mark.asyncio
async def test_subscription_is_cancelled_when_opening_its_future_raises(monkeypatch):
    monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)
    monkeypatch.setattr(discovery, "_ReqIdKey", None)
    ib = _IB(SimpleNamespace())   # neither requests.open nor startReq

    with pytest.raises(IbkrDiscoveryError, match="neither requests.open nor startReq"):
        await discovery._one_shot_scanner(ib, object())

    assert ib.cancelled == [77]
    assert 77 not in discovery._inflight_scan_reqids


@pytest.mark.asyncio
async def test_a_cold_caller_gets_the_registry_key_loaded(monkeypatch):
    """Called before any desk scan ran, the scan still opens its future."""
    monkeypatch.setattr(discovery, "_Stock", None)
    monkeypatch.setattr(discovery, "_ReqIdKey", None)
    opened: list[object] = []

    class _Registry:
        def open(self, key, *, container=None):
            opened.append(key)
            future = asyncio.get_running_loop().create_future()
            future.set_result([])
            return SimpleNamespace(future=future), True

    ib = _IB(SimpleNamespace(requests=_Registry()))
    assert await discovery._one_shot_scanner(ib, object()) == []
    assert len(opened) == 1 and isinstance(opened[0], discovery._ReqIdKey)
    assert ib.cancelled == [77]
