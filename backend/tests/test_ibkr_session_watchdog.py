"""ibkr/session_watchdog.py -- sibling-task recovery (PROBLEM_LOG 2026-08-31).

The watchdog must recover a session that is stuck-unusable OR a dialer that
is dead/frozen, without depending on the dialer task itself being alive to
notice. Every check here calls the module functions directly (no real IB
loop / dialer task needed) -- session_watchdog's own module state is
stateless, so there is nothing to reset between cases beyond the modules it
reads/writes (session_state, session_errors).
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

import ibkr.session_errors as session_errors
import ibkr.session_state as session_state
import ibkr.session_watchdog as watchdog


@pytest.fixture(autouse=True)
def _isolate():
    session_state.reset_for_testing()
    session_errors.reset_for_tests()
    yield
    session_state.reset_for_testing()
    session_errors.reset_for_tests()


def _fake_client_mod(**overrides):
    client_mod = MagicMock()
    client_mod.is_connected.return_value = overrides.get("is_connected", True)
    client_mod.is_ready.return_value = overrides.get("is_ready", False)
    client_mod._ib = overrides.get("ib", MagicMock())
    client_mod.IB = MagicMock(return_value=MagicMock())
    return client_mod


def test_stuck_unusable_below_threshold_does_nothing(monkeypatch):
    import constants_ibkr as cibkr

    monkeypatch.setattr(cibkr, "IBKR_UNUSABLE_FORCE_RECONNECT_SEC", 30.0)
    session_errors.stamp_unusable()
    client_mod = _fake_client_mod()

    watchdog._check_stuck_unusable(client_mod)

    client_mod._safe_disconnect.assert_not_called()
    client_mod.wake_reconnect_loop.assert_not_called()


def test_stuck_unusable_past_threshold_forces_reset_and_wakes(monkeypatch):
    import constants_ibkr as cibkr

    monkeypatch.setattr(cibkr, "IBKR_UNUSABLE_FORCE_RECONNECT_SEC", 0.01)
    session_state.set_connecting()
    session_state.set_synchronizing()
    session_state.set_ready()
    session_state.set_degraded()
    session_errors.stamp_unusable()
    time.sleep(0.02)
    client_mod = _fake_client_mod(is_connected=True, is_ready=False)

    watchdog._check_stuck_unusable(client_mod)

    client_mod._safe_disconnect.assert_called_once()
    client_mod.wake_reconnect_loop.assert_called_once()
    assert session_state.state() == session_state.DISCONNECTED
    client_mod.set_session_reason.assert_called_with("force_reconnect_stuck_unusable")
    # Reset starts a fresh clock -- the next attempt is not pre-judged.
    assert session_errors.unusable_since() is None


@pytest.mark.parametrize("dialer_phase", ["connecting", "synchronizing"])
def test_stuck_unusable_leaves_in_progress_connect_alone(monkeypatch, dialer_phase):
    """PROBLEM_LOG 2026-09-19: an old stamp (the Reconnect click) made the
    watchdog kill every fresh connect ~4s in, so READY was never reachable."""
    import constants_ibkr as cibkr

    monkeypatch.setattr(cibkr, "IBKR_UNUSABLE_FORCE_RECONNECT_SEC", 0.01)
    session_errors.stamp_unusable()
    time.sleep(0.02)
    session_state.set_connecting()
    if dialer_phase == "synchronizing":
        session_state.set_synchronizing()
    client_mod = _fake_client_mod(is_connected=True, is_ready=False)

    watchdog._check_stuck_unusable(client_mod)

    client_mod._safe_disconnect.assert_not_called()
    client_mod.wake_reconnect_loop.assert_not_called()


def test_dialer_reset_also_clears_unusable_stamp(monkeypatch):
    import ibkr.session_reconnect as reconnect

    monkeypatch.setattr(reconnect, "dialer_heartbeat_age_sec", lambda: None)
    session_errors.stamp_unusable()
    client_mod = _fake_client_mod()
    client_mod.reconnect_task.return_value = None

    watchdog._check_dialer_heartbeat(client_mod)

    assert session_errors.unusable_since() is None


def test_stuck_unusable_ignored_when_transport_down():
    """No socket = ordinary reconnect path, not this watchdog's job."""
    session_errors.stamp_unusable()
    client_mod = _fake_client_mod(is_connected=False)

    watchdog._check_stuck_unusable(client_mod)

    client_mod._safe_disconnect.assert_not_called()


def test_stuck_unusable_ignored_when_already_ready():
    client_mod = _fake_client_mod(is_connected=True, is_ready=True)

    watchdog._check_stuck_unusable(client_mod)

    client_mod._safe_disconnect.assert_not_called()


def test_dead_dialer_task_forces_reset_and_respawns(monkeypatch):
    import ibkr.session_reconnect as reconnect

    monkeypatch.setattr(reconnect, "dialer_heartbeat_age_sec", lambda: None)
    client_mod = _fake_client_mod()
    done_task = MagicMock()
    done_task.done.return_value = True
    client_mod.reconnect_task.return_value = done_task

    watchdog._check_dialer_heartbeat(client_mod)

    client_mod._safe_disconnect.assert_called_once()
    client_mod.restart_reconnect_task.assert_called_once()


def test_missing_dialer_task_forces_reset_and_respawns(monkeypatch):
    """Before the dialer has ever been started -- treat None the same as dead."""
    import ibkr.session_reconnect as reconnect

    monkeypatch.setattr(reconnect, "dialer_heartbeat_age_sec", lambda: None)
    client_mod = _fake_client_mod()
    client_mod.reconnect_task.return_value = None

    watchdog._check_dialer_heartbeat(client_mod)

    client_mod.restart_reconnect_task.assert_called_once()


def test_frozen_dialer_heartbeat_forces_reset_and_respawns(monkeypatch):
    import constants_ibkr as cibkr
    import ibkr.session_reconnect as reconnect

    monkeypatch.setattr(cibkr, "IBKR_DIALER_HEARTBEAT_STALE_SEC", 5.0)
    monkeypatch.setattr(reconnect, "dialer_heartbeat_age_sec", lambda: 999.0)
    client_mod = _fake_client_mod()
    alive_task = MagicMock()
    alive_task.done.return_value = False
    client_mod.reconnect_task.return_value = alive_task

    watchdog._check_dialer_heartbeat(client_mod)

    client_mod._safe_disconnect.assert_called_once()
    client_mod.restart_reconnect_task.assert_called_once()
    # A frozen dialer's own task must still be cancellable independently --
    # the watchdog does not need to (and does not) call task.cancel() itself
    # here since restart_reconnect_task() owns cancel-then-respawn.


def test_healthy_dialer_heartbeat_does_nothing(monkeypatch):
    import constants_ibkr as cibkr
    import ibkr.session_reconnect as reconnect

    monkeypatch.setattr(cibkr, "IBKR_DIALER_HEARTBEAT_STALE_SEC", 75.0)
    monkeypatch.setattr(reconnect, "dialer_heartbeat_age_sec", lambda: 2.0)
    client_mod = _fake_client_mod()
    alive_task = MagicMock()
    alive_task.done.return_value = False
    client_mod.reconnect_task.return_value = alive_task

    watchdog._check_dialer_heartbeat(client_mod)

    client_mod._safe_disconnect.assert_not_called()
    client_mod.restart_reconnect_task.assert_not_called()


def test_never_stamped_heartbeat_does_nothing_yet(monkeypatch):
    """Before the dialer has run even once, age is None -- not evidence of
    frozen (see dialer_heartbeat_age_sec docstring); only a dead task counts."""
    import ibkr.session_reconnect as reconnect

    monkeypatch.setattr(reconnect, "dialer_heartbeat_age_sec", lambda: None)
    client_mod = _fake_client_mod()
    alive_task = MagicMock()
    alive_task.done.return_value = False
    client_mod.reconnect_task.return_value = alive_task

    watchdog._check_dialer_heartbeat(client_mod)

    client_mod._safe_disconnect.assert_not_called()
    client_mod.restart_reconnect_task.assert_not_called()
