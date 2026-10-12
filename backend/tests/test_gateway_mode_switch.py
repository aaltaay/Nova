"""Intentional Paper<->Live Gateway switch (ibkr.client.request_gateway_mode).

Covers: invalid input, disabled client, successful switch, honest failure on
refused port, refusing to pretend Live when the connected account isn't live,
and never touching the live spend-unlock env var.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock, patch

from ibkr import client as ibkr_client
from ibkr import gateway_heal as heal


def setup_function() -> None:
    heal.clear_heal_status_for_tests()


def _run(coro):
    return asyncio.run(coro)


def test_request_gateway_mode_rejects_invalid_mode():
    result = _run(ibkr_client.request_gateway_mode("bogus"))
    assert result["ok"] is False
    assert "invalid mode" in result["error"]


def test_request_gateway_mode_requires_enabled(monkeypatch):
    monkeypatch.delenv("IBKR_ENABLED", raising=False)
    monkeypatch.setattr(ibkr_client, "_enabled", False)
    monkeypatch.setattr(ibkr_client, "_config_loaded", True)
    result = _run(ibkr_client.request_gateway_mode("live"))
    assert result["ok"] is False
    assert "IBKR_ENABLED" in result["error"]
    assert "starting" not in result


def _starting(monkeypatch, saved_door: str) -> None:
    """API just started: .env has IBKR on, the dialer has not read it yet."""
    monkeypatch.setenv("IBKR_ENABLED", "true")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", saved_door)
    monkeypatch.setattr(ibkr_client, "_enabled", False)
    monkeypatch.setattr(ibkr_client, "_config_loaded", False)


def test_enabled_reads_env_until_the_dialer_has_read_it(monkeypatch):
    """Operator report 2026-10-11: a Live click 16 s after an API restart said
    "IBKR_ENABLED is not set" on a desk whose .env had it on."""
    _starting(monkeypatch, "live")
    assert ibkr_client.is_enabled() is True
    assert ibkr_client.is_starting() is True
    assert ibkr_client.session_snapshot()["enabled"] is True

    monkeypatch.setattr(ibkr_client, "_config_loaded", True)
    monkeypatch.setattr(ibkr_client, "_enabled", False)
    assert ibkr_client.is_enabled() is False  # the dialer's read wins once made
    assert ibkr_client.is_starting() is False


def test_request_gateway_mode_while_starting_never_blames_env_or_touches_gateway(monkeypatch):
    _starting(monkeypatch, "live")
    with patch(
        "ibkr.launch_gateway.launch_or_focus_gateway",
        side_effect=AssertionError("must not touch the Gateway while starting"),
    ):
        same_door = _run(ibkr_client.request_gateway_mode("live"))
        other_door = _run(ibkr_client.request_gateway_mode("paper"))

    assert same_door["ok"] is True
    assert same_door["starting"] is True
    assert same_door["launch_action"] == "noop"
    assert "IBKR_ENABLED" not in (same_door["message"] or "")

    assert other_door["ok"] is False
    assert other_door["starting"] is True
    assert "still starting" in other_door["error"]
    assert "IBKR_ENABLED" not in other_door["error"]


def test_request_gateway_mode_success_persists_and_sets_sticky_intent(monkeypatch):
    monkeypatch.setattr(ibkr_client, "_enabled", True)
    monkeypatch.setattr(ibkr_client, "_ib", None)
    monkeypatch.setattr(ibkr_client, "is_connected", lambda: True)
    monkeypatch.setattr(ibkr_client, "broker_account_kind", lambda: "paper")
    monkeypatch.setattr(ibkr_client, "account_mode", lambda: "paper")

    with (
        patch.object(heal, "persist_gateway_mode", return_value=True) as mock_persist,
        patch.object(heal, "apply_runtime_gateway_mode") as mock_apply,
        patch.object(heal, "set_intentional_mode") as mock_intent,
        patch("ibkr.launch_gateway.launch_or_focus_gateway") as mock_launch,
    ):
        result = _run(ibkr_client.request_gateway_mode("paper"))

    assert result["ok"] is True
    assert result["error"] is None
    assert result["connected"] is True
    assert result["launch_action"] == "noop"
    assert result["mode"] == "paper"
    mock_persist.assert_called_once_with("paper")
    mock_apply.assert_called_once_with("paper")
    mock_intent.assert_called_once_with("paper")
    mock_launch.assert_not_called()


def test_request_gateway_mode_never_unlocks_live_spend(monkeypatch):
    monkeypatch.delenv("IBKR_LIVE_TRADING_CONFIRMED", raising=False)
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    monkeypatch.setenv("IBKR_ORDERS_ENABLED", "true")
    monkeypatch.setattr(ibkr_client, "_enabled", True)
    monkeypatch.setattr(ibkr_client, "_ib", None)
    monkeypatch.setattr(ibkr_client, "is_connected", lambda: True)
    monkeypatch.setattr(ibkr_client, "broker_account_kind", lambda: "live")
    monkeypatch.setattr(ibkr_client, "account_mode", lambda: "live")

    with (
        patch.object(heal, "persist_gateway_mode", return_value=True),
        patch.object(heal, "apply_runtime_gateway_mode"),
        patch.object(heal, "set_intentional_mode"),
        patch("ibkr.launch_gateway.launch_or_focus_gateway") as mock_launch,
    ):
        result = _run(ibkr_client.request_gateway_mode("live"))

    assert result["ok"] is True
    assert result["spend_status"] == "locked_live_unconfirmed"
    assert result["launch_action"] == "noop"
    assert os.environ.get("IBKR_LIVE_TRADING_CONFIRMED") is None
    mock_launch.assert_not_called()


def test_request_gateway_mode_disconnected_live_starts_ibc(monkeypatch):
    monkeypatch.setattr(ibkr_client, "_enabled", True)
    monkeypatch.setattr(ibkr_client, "_ib", None)
    monkeypatch.setattr(ibkr_client, "is_connected", lambda: False)
    monkeypatch.setattr(ibkr_client, "broker_account_kind", lambda: "unknown")
    monkeypatch.setattr(ibkr_client, "account_mode", lambda: "disconnected")
    monkeypatch.setattr(ibkr_client, "wake_reconnect_loop", lambda: None)
    monkeypatch.setattr(ibkr_client, "set_session_reason", lambda *_a, **_k: None)
    monkeypatch.setattr(ibkr_client, "_set_session", lambda **_k: None)

    with (
        patch.object(heal, "persist_gateway_mode", return_value=True),
        patch.object(heal, "apply_runtime_gateway_mode"),
        patch("ibkr.launch_gateway.launch_or_focus_gateway") as mock_launch,
        patch("ibkr.port_diagnostics.probe_port", return_value=False),
    ):
        mock_launch.return_value = {
            "ok": True,
            "action": "launched_ibc",
            "message": "Starting LIVE Gateway (port 4001).",
        }
        result = _run(ibkr_client.request_gateway_mode("live"))

    assert result["ok"] is True
    assert result["connected"] is False
    assert result["launch_action"] == "launched_ibc"
    assert result["plan"] == "start_ibc"
    assert heal.intentional_mode() == "live"
    mock_launch.assert_called_once_with("live", force_restart=True)


def test_request_gateway_mode_live_from_paper_on_4001_replaces_target(monkeypatch):
    """Paper glued to 4001 is not Live -- replace that port only."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    monkeypatch.setattr(ibkr_client, "_enabled", True)
    monkeypatch.setattr(ibkr_client, "_ib", fake_ib)
    monkeypatch.setattr(ibkr_client, "is_connected", lambda: True)
    monkeypatch.setattr(ibkr_client, "broker_account_kind", lambda: "paper")
    monkeypatch.setattr(ibkr_client, "account_mode", lambda: "paper")
    monkeypatch.setattr(ibkr_client, "wake_reconnect_loop", lambda: None)
    monkeypatch.setattr(ibkr_client, "set_session_reason", lambda *_a, **_k: None)
    monkeypatch.setattr(ibkr_client, "_set_session", lambda **_k: None)

    with (
        patch.object(heal, "persist_gateway_mode", return_value=True),
        patch.object(heal, "apply_runtime_gateway_mode"),
        patch("ibkr.launch_gateway.launch_or_focus_gateway") as mock_launch,
        patch("ibkr.port_diagnostics.probe_port", return_value=True),
    ):
        mock_launch.return_value = {
            "ok": True,
            "action": "launched_ibc",
            "message": "Starting LIVE Gateway (port 4001).",
        }
        result = _run(ibkr_client.request_gateway_mode("live"))

    assert result["ok"] is True
    assert result["plan"] == "replace_target"
    assert result["launch_action"] == "launched_ibc"
    assert heal.intentional_mode() == "live"
    fake_ib.disconnect.assert_called()
    mock_launch.assert_called_once_with("live", force_restart=True)


def test_request_gateway_mode_paper_from_live_reattaches_if_4002_up(monkeypatch):
    """Live stays running. Paper port already up → dial 4002, no kill."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    monkeypatch.setattr(ibkr_client, "_enabled", True)
    monkeypatch.setattr(ibkr_client, "_ib", fake_ib)
    monkeypatch.setattr(ibkr_client, "is_connected", lambda: True)
    monkeypatch.setattr(ibkr_client, "broker_account_kind", lambda: "live")
    monkeypatch.setattr(ibkr_client, "account_mode", lambda: "live")
    monkeypatch.setattr(ibkr_client, "wake_reconnect_loop", lambda: None)
    monkeypatch.setattr(ibkr_client, "set_session_reason", lambda *_a, **_k: None)
    monkeypatch.setattr(ibkr_client, "_set_session", lambda **_k: None)

    with (
        patch.object(heal, "persist_gateway_mode", return_value=True),
        patch.object(heal, "apply_runtime_gateway_mode"),
        patch("ibkr.launch_gateway.launch_or_focus_gateway") as mock_launch,
        patch("ibkr.port_diagnostics.probe_port", return_value=True),
    ):
        mock_launch.return_value = {
            "ok": True,
            "action": "already_listening",
            "message": "PAPER Gateway is already listening on port 4002.",
        }
        result = _run(ibkr_client.request_gateway_mode("paper"))

    assert result["ok"] is True
    assert result["plan"] == "reconnect"
    assert result["launch_action"] == "already_listening"
    fake_ib.disconnect.assert_called()
    mock_launch.assert_called_once_with("paper", force_restart=False)


def test_request_gateway_mode_disarms_the_desk(monkeypatch):
    """ADR 018: a venue change disarms, and Paper<->Live does not go through
    sim.mode. Without this, an armed Paper desk reconnects as Live still armed
    and spends on the next keystroke -- carrying an arm across a venue change
    is the same class of bug as carrying it across a restart."""
    from ibkr import safety as _safety

    monkeypatch.setattr(ibkr_client, "_enabled", True)
    monkeypatch.setattr(ibkr_client, "_ib", None)
    monkeypatch.setattr(ibkr_client, "is_connected", lambda: True)
    monkeypatch.setattr(ibkr_client, "broker_account_kind", lambda: "paper")
    monkeypatch.setattr(ibkr_client, "account_mode", lambda: "paper")
    _safety.set_armed(True, reason="operator armed the paper desk")

    with (
        patch.object(heal, "persist_gateway_mode", return_value=True),
        patch.object(heal, "apply_runtime_gateway_mode"),
        patch.object(heal, "set_intentional_mode"),
        patch("ibkr.launch_gateway.launch_or_focus_gateway"),
    ):
        result = _run(ibkr_client.request_gateway_mode("live"))

    assert result["ok"] is True
    assert _safety.armed() is False, "the door changed -- the arm must not survive it"
