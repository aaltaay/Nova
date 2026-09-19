"""Connect-time accountValue / updatePortfolio push (#182)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from ib_async import IB
from ib_async._requests import SingletonKey

import ibkr.account_stream as stream


def test_ensure_account_updates_noop_when_disconnected():
    assert asyncio.run(stream.ensure_account_updates(None)) is False


def test_ensure_account_updates_sends_subscription():
    ib = MagicMock()
    ib.managedAccounts.return_value = ["DU123"]
    assert asyncio.run(stream.ensure_account_updates(ib)) is True
    ib.client.reqAccountUpdates.assert_called_once_with(True, "DU123")


def test_ensure_account_updates_swallows_failure():
    ib = MagicMock()
    ib.managedAccounts.return_value = []
    ib.client.reqAccountUpdates.side_effect = RuntimeError("socket closed")
    assert asyncio.run(stream.ensure_account_updates(ib)) is False


def test_resubscribe_does_not_wait_for_download_end():
    """IB never re-sends accountDownloadEnd for an already-subscribed account
    (live probe 2026-09-19), so waiting cost the full timeout on every connect.
    Real ib_async IB: must return at once and leave no pending request behind."""
    ib = IB()
    sent: list[tuple] = []
    ib.client.send = lambda *fields: sent.append(fields)
    ib.wrapper.accounts = ["U123"]

    async def run():
        for _ in range(2):  # connect path, then e.g. a 1102 restore
            assert await asyncio.wait_for(stream.ensure_account_updates(ib), 0.5) is True

    asyncio.run(run())

    assert sent == [(6, 2, True, "U123"), (6, 2, True, "U123")]
    assert SingletonKey("accountValues") not in ib.wrapper.requests
