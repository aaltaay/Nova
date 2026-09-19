"""ibkr/completed_orders_state.py -- per-connection 'history loaded' marker
that gates startup_sweep's absence-means-abandoned rule (PROBLEM_LOG 2026-09-19)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

import ibkr.account as account_mod
import ibkr.completed_orders_state as state
from ibkr.ib_scheduler import reset_for_testing as reset_cold_slot


@pytest.fixture(autouse=True)
def _isolate():
    state.reset_for_testing()
    reset_cold_slot()
    account_mod.reset_completed_orders_cooldown_for_testing()
    yield
    state.reset_for_testing()
    reset_cold_slot()
    account_mod.reset_completed_orders_cooldown_for_testing()


def test_marker_is_per_connection_object():
    first, reconnect = MagicMock(), MagicMock()
    state.mark_loaded(first)
    assert state.loaded_for(first) is True
    assert state.loaded_for(reconnect) is False
    assert state.loaded_for(None) is False


def test_successful_refresh_marks_the_connection():
    async def ok(_api_only):
        return []

    ib = MagicMock()
    ib.reqCompletedOrdersAsync = ok
    asyncio.run(account_mod.refresh_completed_orders_cache(ib, force=True))
    assert state.loaded_for(ib) is True


def test_unanswered_refresh_leaves_the_connection_unmarked():
    """The 2026-09-19 shape: ib_async hands back an already-cancelled future."""

    async def run(ib):
        stale = asyncio.get_running_loop().create_future()
        stale.cancel()
        ib.reqCompletedOrdersAsync = lambda _api_only: stale
        await account_mod.refresh_completed_orders_cache(ib, force=True)

    ib = MagicMock()
    asyncio.run(run(ib))
    assert state.loaded_for(ib) is False
