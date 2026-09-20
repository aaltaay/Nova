"""Completed orders are fetched after READY, never on the connect path (D-057).

The 2026-09-17 / 2026-09-19 shape: the Gateway answers positions, open orders,
executions and account updates in under a second but never answers
``reqCompletedOrders``. Before this, that stalled ``connectAsync`` and
``earn_usable``, and the desk told the trader to log into a Gateway that was
already logged in.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibkr import client_connect
from ibkr import completed_orders_state as co_state
from ibkr import completed_orders_warm as warm
from ibkr import session_state as session


@pytest.fixture(autouse=True)
def _clean():
    warm.reset_for_testing()
    co_state.reset_for_testing()
    yield
    warm.reset_for_testing()
    co_state.reset_for_testing()


def test_connect_fetch_fields_drops_only_completed_orders():
    from ib_async import StartupFetch

    fields = client_connect.connect_fetch_fields()
    assert fields is not None
    assert not (fields & StartupFetch.ORDERS_COMPLETE)
    for member in StartupFetch:
        if member is StartupFetch.ORDERS_COMPLETE:
            continue
        assert fields & member, f"{member} must still be fetched at connect"


def test_attempt_connect_passes_fetch_fields_without_completed_orders():
    from ib_async import StartupFetch

    seen: dict = {}

    async def _connect(_host, _port, **kwargs):
        seen.update(kwargs)

    ib = MagicMock()
    ib.connectAsync = _connect

    ok, reason = asyncio.run(client_connect.attempt_connect(ib, "127.0.0.1", 4001, 17))
    assert (ok, reason) == (True, "ok")
    assert not (seen["fetchFields"] & StartupFetch.ORDERS_COMPLETE)
    assert seen["clientId"] == 17


def test_earn_usable_reaches_ready_while_completed_orders_never_answer(monkeypatch):
    """The acceptance for #305: a wedged reqCompletedOrders must not hold READY."""
    from ibkr import client as ibkr_client
    from ibkr import session_errors as se
    from ibkr import session_usable as su

    se.reset_for_tests()
    su.reset_for_tests()
    session.reset_for_testing()

    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    async def _warm_pos(ib=None):
        return None

    never_answered = asyncio.Event()

    async def _never_answers(ib=None, force=False):
        never_answered.set()
        await asyncio.sleep(3600)

    async def _on_ready(ib, *, reason: str):
        return None

    monkeypatch.setattr("ibkr.account.refresh_positions_cache", _warm_pos)
    monkeypatch.setattr("ibkr.account.refresh_completed_orders_cache", _never_answers)
    monkeypatch.setattr(ibkr_client, "_on_session_ready", _on_ready)
    monkeypatch.setattr(ibkr_client, "_clear_sticky_bridge_error_on_ready", lambda: None)
    monkeypatch.setattr("ibkr.account_stream.ensure_account_updates", _warm_pos)
    monkeypatch.setattr("constants_ibkr.IBKR_EARN_USABLE_TIMEOUT_SEC", 1.0)

    async def _run():
        ok, detail = await asyncio.wait_for(su.earn_usable(fake_ib, "test"), timeout=2.0)
        # The background warm is running (and stuck) while the desk is READY.
        await asyncio.sleep(0)
        return ok, detail

    ok, detail = asyncio.run(_run())
    assert (ok, detail) == (True, "ok")
    assert session.is_ready() is True
    assert never_answered.is_set(), "post-READY warm never asked for completed orders"
    su.reset_for_tests()
    session.reset_for_testing()


def _run_scheduled_warm(ib) -> None:
    async def _go():
        warm.schedule(ib)
        task = warm._task
        assert task is not None
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(_go())


def test_warm_retries_until_the_gateway_answers(monkeypatch):
    monkeypatch.setattr("constants_ibkr.IBKR_COMPLETED_ORDERS_WARM_BACKOFF_SEC", (0.0, 0.0))
    ib = MagicMock()
    ib.isConnected.return_value = True
    attempts: list[int] = []

    async def _refresh(target=None, force=False):
        attempts.append(1)
        if len(attempts) >= 3:
            co_state.mark_loaded(target)

    monkeypatch.setattr("ibkr.account.refresh_completed_orders_cache", _refresh)

    _run_scheduled_warm(ib)
    assert len(attempts) == 3
    assert co_state.loaded_for(ib) is True


def test_warm_gives_up_after_the_backoff_and_leaves_the_stamp(monkeypatch):
    monkeypatch.setattr("constants_ibkr.IBKR_COMPLETED_ORDERS_WARM_BACKOFF_SEC", (0.0,))
    ib = MagicMock()
    ib.isConnected.return_value = True
    attempts: list[int] = []

    async def _refresh(target=None, force=False):
        attempts.append(1)

    monkeypatch.setattr("ibkr.account.refresh_completed_orders_cache", _refresh)

    _run_scheduled_warm(ib)
    # len(backoff) + 1 asks, then completed_orders_health.reprobe_loop owns it.
    assert len(attempts) == 2
    assert co_state.loaded_for(ib) is False


def test_warm_stops_when_the_socket_drops(monkeypatch):
    monkeypatch.setattr("constants_ibkr.IBKR_COMPLETED_ORDERS_WARM_BACKOFF_SEC", (0.0, 0.0))
    ib = MagicMock()
    ib.isConnected.return_value = True
    attempts: list[int] = []

    async def _refresh(target=None, force=False):
        attempts.append(1)
        ib.isConnected.return_value = False  # Gateway went away mid-warm

    monkeypatch.setattr("ibkr.account.refresh_completed_orders_cache", _refresh)

    _run_scheduled_warm(ib)
    assert len(attempts) == 1


def test_warm_is_not_current_for_a_replaced_connection():
    old_ib = MagicMock()
    old_ib.isConnected.return_value = True
    new_ib = MagicMock()
    new_ib.isConnected.return_value = True

    async def _go():
        warm.schedule(old_ib)
        assert warm._still_current(old_ib) is True
        warm.schedule(new_ib)  # reconnect
        assert warm._still_current(old_ib) is False
        assert warm._still_current(new_ib) is True

    asyncio.run(_go())
