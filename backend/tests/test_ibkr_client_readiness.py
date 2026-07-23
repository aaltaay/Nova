"""IBKR readiness gate + run_coro cancellation/staleness hardening.

Covers the PROBLEM_LOG 2026-07-23 remediation: get_ib() must not hand out a
client before Nova's own session_state says READY, and run_coro() must
cancel a timed-out bridge future and refuse a result from a stale
generation instead of silently applying it.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from ibkr import client as ibkr_client
from ibkr import session_state as session


@pytest.fixture(autouse=True)
def _isolate():
    session.reset_for_testing()
    yield
    session.reset_for_testing()


def test_get_ib_gated_on_session_ready(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True
    monkeypatch.setattr(ibkr_client, "_ib", fake_ib)

    assert ibkr_client.get_ib() is None  # transport "connected" but session not READY

    session.set_connecting()
    assert ibkr_client.get_ib() is None
    session.set_synchronizing()
    assert ibkr_client.get_ib() is None

    session.set_ready()
    assert ibkr_client.get_ib() is fake_ib
    assert ibkr_client.is_ready() is True


def test_get_ib_none_when_transport_drops_even_if_state_stale(monkeypatch):
    """Safety net: is_ready() ANDs session_state with the raw socket check so
    a dead connection cannot serve get_ib() just because reconnect_loop
    has not yet processed the drop."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True
    monkeypatch.setattr(ibkr_client, "_ib", fake_ib)
    session.set_connecting()
    session.set_synchronizing()
    session.set_ready()
    assert ibkr_client.get_ib() is fake_ib

    fake_ib.isConnected.return_value = False
    assert ibkr_client.get_ib() is None
    assert ibkr_client.is_ready() is False


def test_run_coro_cancels_future_on_timeout(monkeypatch):
    async def _main():
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(ibkr_client, "_loop", loop)
        cancelled = asyncio.Event()

        async def _hang():
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        def _call():
            with pytest.raises(TimeoutError):
                ibkr_client.run_coro(_hang(), timeout=0.05, label="test")

        await loop.run_in_executor(None, _call)
        await asyncio.wait_for(cancelled.wait(), timeout=2.0)

    asyncio.run(_main())


def test_run_coro_raises_stale_session_error_when_generation_changes(monkeypatch):
    async def _main():
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(ibkr_client, "_loop", loop)

        async def _slow():
            await asyncio.sleep(0.05)
            return "ok"

        def _call():
            return ibkr_client.run_coro(_slow(), timeout=2.0)

        fut = loop.run_in_executor(None, _call)
        await asyncio.sleep(0.01)
        # Simulate a disconnect/reconnect completing while the bridged call
        # is still in flight.
        session.set_connecting()
        session.set_synchronizing()
        session.set_ready()

        with pytest.raises(ibkr_client.StaleIbkrSessionError):
            await fut

    asyncio.run(_main())


def test_run_coro_returns_result_when_generation_unchanged(monkeypatch):
    async def _main():
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(ibkr_client, "_loop", loop)

        async def _quick():
            return "ok"

        def _call():
            return ibkr_client.run_coro(_quick(), timeout=2.0)

        result = await loop.run_in_executor(None, _call)
        assert result == "ok"

    asyncio.run(_main())
