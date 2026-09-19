"""earn_usable -- overall warm-up deadline (PROBLEM_LOG 2026-08-31).

Each account.py call already bounds itself internally (positions timeout,
completed-orders timeout + cold_slot acquire timeout). This overall deadline
is belt-and-suspenders for the case where one of those inner bounds is
bypassed -- it must abort cleanly (not promote to READY) rather than hang.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

import ibkr.account as account_mod
import ibkr.session_errors as session_errors
import ibkr.session_state as session_state
import ibkr.session_usable as session_usable
from ibkr.ib_scheduler import reset_for_testing as reset_cold_slot


@pytest.fixture(autouse=True)
def _isolate():
    session_state.reset_for_testing()
    session_errors.reset_for_tests()
    session_usable.reset_for_tests()
    reset_cold_slot()
    account_mod.reset_completed_orders_cooldown_for_testing()
    yield
    session_state.reset_for_testing()
    session_errors.reset_for_tests()
    session_usable.reset_for_tests()
    reset_cold_slot()
    account_mod.reset_completed_orders_cooldown_for_testing()


def _fake_ib() -> MagicMock:
    ib = MagicMock()
    ib.isConnected.return_value = True
    return ib


def test_earn_usable_transport_down_returns_immediately():
    ib = MagicMock()
    ib.isConnected.return_value = False
    ok, detail = asyncio.run(session_usable.earn_usable(ib, "test"))
    assert ok is False
    assert detail == "transport_down"
    assert session_state.state() == session_state.DISCONNECTED


def test_earn_usable_aborts_on_overall_deadline_without_promoting_ready(monkeypatch):
    """A warm-up that never returns (bypassing its own inner timeout) must
    not leave the session READY on top of caches that never warmed."""
    import constants_ibkr as cibkr

    monkeypatch.setattr(cibkr, "IBKR_EARN_USABLE_TIMEOUT_SEC", 0.05)

    async def hang(_ib):
        await asyncio.sleep(30)

    monkeypatch.setattr(account_mod, "refresh_positions_cache", hang)

    ib = _fake_ib()
    ok, detail = asyncio.run(session_usable.earn_usable(ib, "connect"))

    assert ok is False
    assert detail == "warmup_deadline_exceeded"
    assert session_state.state() != session_state.READY
    assert session_errors.unusable_since() is not None


def test_earn_usable_happy_path_reaches_ready(monkeypatch):
    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(account_mod, "refresh_positions_cache", _noop)
    monkeypatch.setattr(account_mod, "refresh_completed_orders_cache", _noop)

    ib = _fake_ib()
    ok, detail = asyncio.run(session_usable.earn_usable(ib, "connect"))

    assert ok is True
    assert detail == "ok"
    assert session_state.state() == session_state.READY
    assert session_state.generation() == 1


def test_earn_usable_reaches_ready_when_completed_orders_future_is_stale(monkeypatch):
    """connectAsync's completed-orders sync timed out, so ib_async hands the
    warm-up an already-cancelled future. That used to raise CancelledError
    out of earn_usable and silently kill the dialer (PROBLEM_LOG 2026-09-19)."""

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(account_mod, "refresh_positions_cache", _noop)

    async def run():
        stale = asyncio.get_running_loop().create_future()
        stale.cancel()
        ib = _fake_ib()
        ib.reqCompletedOrdersAsync = lambda _api_only: stale
        return await session_usable.earn_usable(ib, "connect")

    ok, detail = asyncio.run(run())

    assert (ok, detail) == (True, "ok")
    assert session_state.state() == session_state.READY
