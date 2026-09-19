"""ibkr/completed_orders_health.py -- D-058 "completed orders not answering
since HH:MM" (PROBLEM_LOG 2026-09-19)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from ib_async import IB

import ibkr.account as account_mod
import ibkr.client as client_mod
import ibkr.completed_orders_health as health
from ibkr.errors import StaleIbRequestError
from ibkr.ib_scheduler import reset_for_testing as reset_cold_slot


@pytest.fixture(autouse=True)
def _isolate():
    health.reset_for_testing()
    reset_cold_slot()
    account_mod.reset_completed_orders_cooldown_for_testing()
    yield
    health.reset_for_testing()
    reset_cold_slot()
    account_mod.reset_completed_orders_cooldown_for_testing()


@pytest.mark.parametrize("exc", [TimeoutError(), StaleIbRequestError("stale")])
def test_no_answer_failures_stamp_the_first_attempt(monkeypatch, exc):
    monkeypatch.setattr(health.time, "time", lambda: 1000.0)
    health.note_failed(exc)
    monkeypatch.setattr(health.time, "time", lambda: 2000.0)
    health.note_failed(exc)
    assert health.unanswered_since() == 1000.0


def test_other_failures_are_not_the_gateway_refusing():
    health.note_failed(ConnectionError("Socket disconnect"))
    health.note_failed(RuntimeError("boom"))
    assert health.unanswered_since() is None


def test_an_answer_clears_the_stamp():
    health.note_failed(TimeoutError())
    health.note_answered()
    assert health.unanswered_since() is None


def test_warning_waits_out_a_merely_slow_connect(monkeypatch):
    import constants_ibkr as cibkr

    monkeypatch.setattr(cibkr, "IBKR_COMPLETED_ORDERS_WARN_AFTER_SEC", 120.0)
    monkeypatch.setattr(health.time, "time", lambda: 1000.0)
    health.note_failed(TimeoutError())
    assert health.warn_since(now=1119.0) is None
    assert health.warn_since(now=1120.0) == 1000.0


def test_refresh_with_stale_future_stamps_then_answer_clears():
    """The 2026-09-19 shape end to end through account.refresh_completed_orders_cache."""

    async def stale_run(ib):
        stale = asyncio.get_running_loop().create_future()
        stale.cancel()
        ib.reqCompletedOrdersAsync = lambda _api_only: stale
        await account_mod.refresh_completed_orders_cache(ib, force=True)

    asyncio.run(stale_run(MagicMock()))
    assert health.unanswered_since() is not None

    async def ok(_api_only):
        return []

    answering = MagicMock()
    answering.reqCompletedOrdersAsync = ok
    asyncio.run(account_mod.refresh_completed_orders_cache(answering, force=True))
    assert health.unanswered_since() is None


def test_reprobe_clears_once_a_late_gateway_answer_settles_the_stale_request(monkeypatch):
    """Review finding: Gateway answers ~1s after connectAsync's 7.5s sync gave up.
    Without the re-probe the warning stayed up until the next reconnect."""

    async def run():
        ib = IB()
        sent: list[bool] = []
        ib.client.reqCompletedOrders = lambda api_only: sent.append(api_only)
        monkeypatch.setattr(client_mod, "get_ib", lambda: ib)
        with pytest.raises(TimeoutError):  # connectAsync's startup sync
            await asyncio.wait_for(ib.reqCompletedOrdersAsync(False), 0.01)
        await account_mod.refresh_completed_orders_cache(ib, force=True)
        assert health.unanswered_since() is not None  # stale -> stamped

        await health.reprobe_once()  # still stale: no wire traffic, still stamped
        assert sent == [False]
        assert health.unanswered_since() is not None

        ib.wrapper.completedOrdersEnd()  # the late Gateway answer lands
        ib.client.reqCompletedOrders = lambda _api_only: ib.wrapper.completedOrdersEnd()
        await health.reprobe_once()
        assert health.unanswered_since() is None

    asyncio.run(run())


def test_reprobe_is_idle_when_answering_or_not_ready(monkeypatch):
    calls: list[object] = []

    async def spy(ib, *, force=False):
        calls.append(ib)

    monkeypatch.setattr(account_mod, "refresh_completed_orders_cache", spy)
    monkeypatch.setattr(client_mod, "get_ib", lambda: MagicMock())
    asyncio.run(health.reprobe_once())  # nothing stamped
    health.note_failed(TimeoutError())
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    asyncio.run(health.reprobe_once())  # stamped, but session not READY
    assert calls == []
