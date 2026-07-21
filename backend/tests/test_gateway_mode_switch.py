"""Intentional Paper<->Live Gateway switch (ibkr.client.request_gateway_mode).

Covers: invalid input, disabled client, successful switch, honest failure on
refused port, refusing to pretend Live when the connected account isn't live,
and never touching the live spend-unlock env var.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

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
    monkeypatch.setattr(ibkr_client, "_enabled", False)
    result = _run(ibkr_client.request_gateway_mode("live"))
    assert result["ok"] is False
    assert "IBKR_ENABLED" in result["error"]


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
        patch.object(ibkr_client, "wake_reconnect_loop") as mock_wake,
    ):
        result = _run(ibkr_client.request_gateway_mode("paper"))

    assert result["ok"] is True
    assert result["error"] is None
    assert result["connected"] is True
    assert result["mode"] == "paper"
    mock_persist.assert_called_once_with("paper")
    mock_apply.assert_called_once_with("paper")
    mock_intent.assert_called_once_with("paper")
    mock_wake.assert_called_once()


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
        patch.object(ibkr_client, "wake_reconnect_loop"),
    ):
        result = _run(ibkr_client.request_gateway_mode("live"))

    assert result["ok"] is True
    assert result["spend_status"] == "locked_live_unconfirmed"
    assert os.environ.get("IBKR_LIVE_TRADING_CONFIRMED") is None


def test_request_gateway_mode_honest_failure_keeps_sticky_intent(monkeypatch):
    monkeypatch.setattr(ibkr_client, "_enabled", True)
    monkeypatch.setattr(ibkr_client, "_ib", None)
    monkeypatch.setattr(ibkr_client, "is_connected", lambda: False)
    monkeypatch.setattr(ibkr_client, "broker_account_kind", lambda: "unknown")
    monkeypatch.setattr(ibkr_client, "account_mode", lambda: "disconnected")
    monkeypatch.setattr(ibkr_client, "IBKR_CONNECT_TIMEOUT_SEC", 0.05)

    with (
        patch.object(heal, "persist_gateway_mode", return_value=True),
        patch.object(heal, "apply_runtime_gateway_mode"),
        patch.object(ibkr_client, "wake_reconnect_loop"),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        result = _run(ibkr_client.request_gateway_mode("live"))

    assert result["ok"] is False
    assert result["connected"] is False
    assert "Could not connect" in result["error"]
    # Sticky intent survives the failed switch — heal stays blocked.
    assert heal.intentional_mode() == "live"
    assert heal.self_heal_suppressed() is True


def test_request_gateway_mode_refuses_paper_account_on_live_port(monkeypatch):
    """Defensive: a paper account should never answer on the live port, but
    if it does, disconnect and fail loud rather than pretending Live."""
    fake_ib = MagicMock()
    fake_ib.isConnected.return_value = True

    monkeypatch.setattr(ibkr_client, "_enabled", True)
    monkeypatch.setattr(ibkr_client, "_ib", fake_ib)
    monkeypatch.setattr(ibkr_client, "is_connected", lambda: True)
    monkeypatch.setattr(ibkr_client, "broker_account_kind", lambda: "paper")
    monkeypatch.setattr(ibkr_client, "account_mode", lambda: "live")

    with (
        patch.object(heal, "persist_gateway_mode", return_value=True),
        patch.object(heal, "apply_runtime_gateway_mode"),
        patch.object(heal, "set_intentional_mode"),
        patch.object(ibkr_client, "wake_reconnect_loop"),
    ):
        result = _run(ibkr_client.request_gateway_mode("live"))

    assert result["ok"] is False
    assert result["connected"] is False
    assert result["mode"] == "disconnected"
    assert "not live" in result["error"]
    fake_ib.disconnect.assert_called()
