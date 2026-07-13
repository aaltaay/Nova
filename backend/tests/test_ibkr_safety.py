"""
Tests for IBKR safety gates and depth-cap logic.
No live IB Gateway required — all tests run with environment mocking.
"""
import os
import importlib
import pytest


def _reload_safety_stack(monkeypatch, env: dict):
    for k in list(os.environ.keys()):
        if k.startswith("IBKR_"):
            monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import ibkr.safety as safety_mod
    import ibkr.client as client_mod
    import ibkr.orders as orders_mod
    importlib.reload(safety_mod)
    importlib.reload(client_mod)
    importlib.reload(orders_mod)
    return safety_mod, client_mod, orders_mod


class TestOrderSafetyGate:
    def test_disabled_blocks_order(self, monkeypatch):
        _safety, _client, orders_mod = _reload_safety_stack(monkeypatch, {})
        result = orders_mod.place_order("AAPL", "BUY", 10)
        assert result["ok"] is False
        assert "IBKR_ENABLED" in result["error"]

    def test_orders_kill_switch_blocks_even_when_connected(self, monkeypatch):
        """Live Gateway + ORDERS_ENABLED=false → no spending."""
        _safety, client_mod, orders_mod = _reload_safety_stack(monkeypatch, {
            "IBKR_ENABLED": "true",
            "IBKR_GATEWAY_MODE": "live",
            "IBKR_ORDERS_ENABLED": "false",
            "IBKR_LIVE_TRADING_CONFIRMED": "false",
        })
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
        monkeypatch.setattr(client_mod, "account_mode", lambda: "live")
        result = orders_mod.place_order("AAPL", "BUY", 10)
        assert result["ok"] is False
        assert "IBKR_ORDERS_ENABLED" in result["error"]

    def test_live_mode_orders_on_without_confirmation_blocks(self, monkeypatch):
        _safety, client_mod, orders_mod = _reload_safety_stack(monkeypatch, {
            "IBKR_ENABLED": "true",
            "IBKR_GATEWAY_MODE": "live",
            "IBKR_ORDERS_ENABLED": "true",
            "IBKR_LIVE_TRADING_CONFIRMED": "false",
        })
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
        monkeypatch.setattr(client_mod, "account_mode", lambda: "live")
        result = orders_mod.place_order("AAPL", "BUY", 10)
        assert result["ok"] is False
        assert "IBKR_LIVE_TRADING_CONFIRMED" in result["error"]

    def test_paper_orders_enabled_passes_gate(self, monkeypatch):
        _safety, client_mod, orders_mod = _reload_safety_stack(monkeypatch, {
            "IBKR_ENABLED": "true",
            "IBKR_GATEWAY_MODE": "paper",
            "IBKR_ORDERS_ENABLED": "true",
        })
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
        monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
        monkeypatch.setattr(client_mod, "get_ib", lambda: None)
        result = orders_mod.place_order("AAPL", "BUY", 10)
        assert "IBKR_ORDERS_ENABLED" not in (result.get("error") or "")
        assert "IBKR_LIVE_TRADING_CONFIRMED" not in (result.get("error") or "")
        assert result["ok"] is False  # no IB object — gate already passed

    def test_cancel_allowed_when_orders_locked(self, monkeypatch):
        _safety, client_mod, orders_mod = _reload_safety_stack(monkeypatch, {
            "IBKR_ENABLED": "true",
            "IBKR_GATEWAY_MODE": "live",
            "IBKR_ORDERS_ENABLED": "false",
        })
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
        monkeypatch.setattr(client_mod, "get_ib", lambda: None)
        result = orders_mod.cancel_order(1)
        # Gate allows cancel; fails only on missing IB
        assert "IBKR_ORDERS_ENABLED" not in (result.get("error") or "")
        assert result["ok"] is False
        assert "Not connected" in (result.get("error") or "")


class TestDepthCap:
    def setup_method(self):
        import ibkr.depth as depth_mod
        importlib.reload(depth_mod)
        self.depth = depth_mod

    def test_subscribe_when_disconnected_returns_error(self, monkeypatch):
        import ibkr.client as client_mod
        monkeypatch.setattr(client_mod, "is_connected", lambda: False)
        result = self.depth.subscribe("AAPL")
        assert result["ok"] is False
        assert "connect" in result["error"].lower()

    def test_subscribe_cap_enforced(self, monkeypatch):
        import ibkr.client as client_mod
        from constants import IBKR_MAX_DEPTH_SYMBOLS
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        for i in range(IBKR_MAX_DEPTH_SYMBOLS):
            self.depth._subscriptions[f"SYM{i}"] = {}
        result = self.depth.subscribe("EXTRA")
        assert result["ok"] is False
        assert str(IBKR_MAX_DEPTH_SYMBOLS) in result["error"]

    def test_resubscribe_same_symbol_is_idempotent(self, monkeypatch):
        import ibkr.client as client_mod
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        self.depth._subscriptions["AAPL"] = {}
        result = self.depth.subscribe("AAPL")
        assert result["ok"] is True

    def test_subscribed_symbols_list(self):
        self.depth._subscriptions = {"AAPL": {}, "TSLA": {}}
        assert set(self.depth.subscribed_symbols()) == {"AAPL", "TSLA"}
