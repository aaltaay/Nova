"""Connect-time accountValue / updatePortfolio push (#182)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import ibkr.account_stream as stream


def test_ensure_account_updates_noop_when_disconnected():
    assert asyncio.run(stream.ensure_account_updates(None)) is False


def test_ensure_account_updates_sends_singleton_request():
    calls: list[str] = []

    async def req(account: str):
        calls.append(account)

    ib = MagicMock()
    ib.managedAccounts.return_value = ["DU123"]
    ib.reqAccountUpdatesAsync = req
    assert asyncio.run(stream.ensure_account_updates(ib)) is True
    assert calls == ["DU123"]


def test_ensure_account_updates_swallows_failure():
    async def req(_account: str):
        raise RuntimeError("timeout")

    ib = MagicMock()
    ib.managedAccounts.return_value = []
    ib.reqAccountUpdatesAsync = req
    assert asyncio.run(stream.ensure_account_updates(ib)) is False
