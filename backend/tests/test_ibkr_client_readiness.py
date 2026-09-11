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


class _FakeRuntimeState:
    def __init__(self, *, error: str = "", ts: float = 0.0):
        self.ibkr_bridge_last_error = error
        self.ibkr_bridge_last_error_ts = ts


def test_clear_sticky_bridge_error_on_ready_drops_stale_disconnect_error(monkeypatch):
    """Session reaching READY must drop a bridge error left over from the
    disconnect window (see PROBLEM_LOG 2026-07-23 sticky-banner-after-
    reconnect) — otherwise Integrity fail stays red even though movers/L1
    are already live again."""
    state = _FakeRuntimeState(error="gainers: IbkrDiscoveryError: ib=none", ts=123.0)
    monkeypatch.setattr(ibkr_client, "_get_runtime_state", lambda: state)

    ibkr_client._clear_sticky_bridge_error_on_ready()

    assert state.ibkr_bridge_last_error == ""
    assert state.ibkr_bridge_last_error_ts == 0.0


def test_clear_sticky_bridge_error_on_ready_noop_when_already_clear(monkeypatch):
    state = _FakeRuntimeState(error="", ts=0.0)
    monkeypatch.setattr(ibkr_client, "_get_runtime_state", lambda: state)

    ibkr_client._clear_sticky_bridge_error_on_ready()  # must not raise

    assert state.ibkr_bridge_last_error == ""


def test_clear_sticky_bridge_error_on_ready_tolerates_missing_runtime_state(monkeypatch):
    """Must never let a runtime_state lookup failure break the reconnect path."""

    def _raise():
        raise RuntimeError("no runtime state yet")

    monkeypatch.setattr(ibkr_client, "_get_runtime_state", _raise)

    ibkr_client._clear_sticky_bridge_error_on_ready()  # must not raise


def test_earn_usable_single_flight_and_promotes_ready(monkeypatch):
    from ibkr import session_errors as se
    from ibkr import session_usable as su

    se.reset_for_tests()
    su.reset_for_tests()
    session.reset_for_testing()

    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True
    calls: list[str] = []

    async def _warm_pos(ib=None):
        calls.append("pos")

    async def _warm_orders(ib=None, force=False):
        calls.append("orders")

    async def _on_ready(ib, *, reason: str):
        calls.append(f"ready:{reason}")

    monkeypatch.setattr("ibkr.account.refresh_positions_cache", _warm_pos)
    monkeypatch.setattr("ibkr.account.refresh_completed_orders_cache", _warm_orders)
    monkeypatch.setattr(ibkr_client, "_on_session_ready", _on_ready)
    monkeypatch.setattr(ibkr_client, "_clear_sticky_bridge_error_on_ready", lambda: None)
    monkeypatch.setattr(ibkr_client, "_ib", fake_ib)

    async def _run():
        ok1, d1 = await su.earn_usable(fake_ib, "test")
        ok2, d2 = await su.earn_usable(fake_ib, "test2")
        return ok1, d1, ok2, d2

    ok1, d1, ok2, d2 = asyncio.run(_run())
    assert ok1 is True and d1 == "ok"
    assert ok2 is True and d2 == "ok"
    assert session.is_ready() is True
    assert ibkr_client.get_ib() is fake_ib
    assert ibkr_client.is_ready() is True
    assert calls.count("pos") == 2
    assert any(c.startswith("ready:") for c in calls)
    assert se.unusable_since() is None


def test_earn_usable_aborts_if_revoked_mid_sync(monkeypatch):
    from ibkr import session_errors as se
    from ibkr import session_usable as su

    se.reset_for_tests()
    su.reset_for_tests()
    session.reset_for_testing()

    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    async def _warm_pos(ib=None):
        session.set_degraded()
        se.stamp_unusable(code=1100)

    async def _warm_orders(ib=None, force=False):
        return None

    monkeypatch.setattr("ibkr.account.refresh_positions_cache", _warm_pos)
    monkeypatch.setattr("ibkr.account.refresh_completed_orders_cache", _warm_orders)

    ok, detail = asyncio.run(su.earn_usable(fake_ib, "revoked"))
    assert ok is False
    assert detail == "revoked_during_sync"
    assert session.is_ready() is False
    assert ibkr_client.get_ib() is None


def test_earn_usable_transport_down_clears_synchronizing(monkeypatch):
    """Dead socket must not leave session_state=synchronizing (misleading UI)."""
    from ibkr import session_usable as su

    su.reset_for_tests()
    session.reset_for_testing()
    session.set_synchronizing()
    ibkr_client.set_session_reason("synchronizing")

    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = False

    ok, detail = asyncio.run(su.earn_usable(fake_ib, "stale_sync"))
    assert ok is False
    assert detail == "transport_down"
    assert session.state() == session.DISCONNECTED
    assert ibkr_client.session_reason() == "disconnected"


def test_transport_up_unusable_no_longer_force_reconnects_itself(monkeypatch):
    """Stuck-unusable force-reconnect moved to ibkr/session_watchdog.py (a
    sibling IB-loop task) -- see test_ibkr_session_watchdog.py. This function
    must only stamp unusable + wait, never disconnect/recreate IB() on its
    own: a watchdog living inside the task it watches cannot fire once that
    task itself is the thing that froze (PROBLEM_LOG 2026-08-31)."""
    from ibkr import session_errors as se

    se.reset_for_tests()
    session.reset_for_testing()
    session.set_degraded()
    se.stamp_unusable(code=1100)
    se._unusable_since = __import__("time").time() - 100.0  # type: ignore[attr-defined]

    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True
    monkeypatch.setattr(ibkr_client, "_ib", fake_ib)
    monkeypatch.setattr(ibkr_client, "_mode", "paper")
    created: list[object] = []

    class _NewIB:
        def __init__(self):
            created.append(self)

        def isConnected(self):
            return False

        def disconnect(self):
            return None

    monkeypatch.setattr(ibkr_client, "IB", _NewIB)
    monkeypatch.setattr(ibkr_client, "_safe_disconnect", lambda ib: None)
    monkeypatch.setattr(se, "take_restore_pending", lambda: None)
    monkeypatch.setattr(ibkr_client, "_sleep_reconnect", lambda _delay: _fast_noop())

    asyncio.run(ibkr_client._handle_transport_up_unusable("paper"))
    assert len(created) == 0
    assert session.state() == session.DEGRADED  # untouched -- watchdog's job now
    assert se.unusable_since() is not None  # still stamped for the watchdog to read


async def _fast_noop() -> None:
    return None


def test_status_connected_matches_get_ib(monkeypatch):
    """status.connected (usable) == (get_ib() is not None)."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True
    monkeypatch.setattr(ibkr_client, "_ib", fake_ib)
    monkeypatch.setattr(ibkr_client, "_enabled", True)
    session.reset_for_testing()

    assert ibkr_client.get_ib() is None
    assert ibkr_client.is_ready() is False

    session.set_ready()
    assert ibkr_client.get_ib() is fake_ib
    assert ibkr_client.is_ready() is True
    snap = ibkr_client.session_snapshot()
    assert snap["usable"] is True
    assert snap["transport_up"] is True


def test_restart_reconnect_task_cancels_existing_and_spawns_new(monkeypatch):
    """session_watchdog's recovery path -- must not require the old task to
    be responsive (cancelling a suspended/frozen await does not need it to
    cooperate beyond raising CancelledError, which asyncio does for us)."""
    async def _main():
        old = asyncio.create_task(asyncio.sleep(60))
        monkeypatch.setattr(ibkr_client, "_reconnect_task", old)

        async def _fresh_loop():
            await asyncio.sleep(60)

        monkeypatch.setattr(ibkr_client, "reconnect_loop", _fresh_loop)

        assert ibkr_client.reconnect_task() is old
        ibkr_client.restart_reconnect_task()
        new_task = ibkr_client.reconnect_task()

        assert new_task is not old
        assert old.cancelled() or old.cancelling() > 0
        new_task.cancel()
        for task in (old, new_task):
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(_main())


def test_restart_reconnect_task_handles_no_prior_task(monkeypatch):
    async def _main():
        monkeypatch.setattr(ibkr_client, "_reconnect_task", None)

        async def _fresh_loop():
            await asyncio.sleep(60)

        monkeypatch.setattr(ibkr_client, "reconnect_loop", _fresh_loop)

        ibkr_client.restart_reconnect_task()
        new_task = ibkr_client.reconnect_task()
        assert new_task is not None
        new_task.cancel()
        try:
            await new_task
        except asyncio.CancelledError:
            pass

    asyncio.run(_main())


def test_unavailable_detail_distinguishes_transport_vs_session(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = False
    monkeypatch.setattr(ibkr_client, "_ib", fake_ib)
    monkeypatch.setattr(ibkr_client, "_session_reason", "disconnected")
    detail = ibkr_client.unavailable_detail("IBKR bars")
    assert "transport down" in detail

    fake_ib.isConnected.return_value = True
    monkeypatch.setattr(ibkr_client, "_session_reason", "connectivity_lost")
    detail = ibkr_client.unavailable_detail("IBKR bars")
    assert "session not usable" in detail
    assert "connectivity_lost" in detail


def test_on_session_ready_clears_stale_scanner_reqids(monkeypatch):
    """D-039: READY after a full reconnect forgets prior-socket scanner reqIds."""
    from ibkr import discovery

    discovery._inflight_scan_reqids.clear()
    discovery._inflight_scan_reqids.add(99)
    discovery._qualified_contracts.clear()
    discovery._qualified_contracts["AAA"] = object()

    async def _clear(*, reason=""):
        return 0

    monkeypatch.setattr("ibkr.ticks.clear_all_subscriptions", _clear)
    monkeypatch.setattr(ibkr_client._session_errors, "install_error_hook", lambda _ib: None)
    monkeypatch.setattr(ibkr_client._session_errors, "reset_session_md_flags", lambda: None)

    class _IB:
        def reqMarketDataType(self, _n):
            return None

    asyncio.run(ibkr_client._on_session_ready(_IB(), reason="reconnect test"))
    assert discovery._inflight_scan_reqids == set()
    assert discovery._qualified_contracts == {}
