"""
Tests for IBKR safety gates and depth-cap logic.
No live IB Gateway required — all tests run with environment mocking.
"""
import os
import importlib
import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def reload_client(env: dict):
    """Reload ibkr.client with specific env vars patched."""
    for k, v in env.items():
        os.environ[k] = v
    for k in list(os.environ.keys()):
        if k.startswith("IBKR_") and k not in env:
            os.environ.pop(k, None)

    import ibkr.client as _c
    importlib.reload(_c)
    return _c


# ── Order safety gate ─────────────────────────────────────────────────────────

class TestOrderSafetyGate:
    def test_disabled_blocks_order(self, monkeypatch):
        """IBKR_ENABLED not set → orders are refused."""
        monkeypatch.delenv("IBKR_ENABLED", raising=False)
        monkeypatch.delenv("IBKR_LIVE_TRADING_CONFIRMED", raising=False)
        import ibkr.orders as orders_mod
        import importlib
        importlib.reload(orders_mod)
        result = orders_mod.place_order("AAPL", "BUY", 10)
        assert result["ok"] is False
        assert "IBKR_ENABLED" in result["error"]

    def test_enabled_but_not_connected_blocks_order(self, monkeypatch):
        """IBKR_ENABLED=true but no Gateway → orders are refused."""
        monkeypatch.setenv("IBKR_ENABLED", "true")
        monkeypatch.delenv("IBKR_LIVE_TRADING_CONFIRMED", raising=False)
        import ibkr.client as client_mod
        import ibkr.orders as orders_mod
        import importlib
        importlib.reload(client_mod)
        importlib.reload(orders_mod)
        # client._enabled=True but is_connected() returns False (no Gateway)
        result = orders_mod.place_order("AAPL", "BUY", 10)
        assert result["ok"] is False
        assert "connect" in result["error"].lower() or "enabled" in result["error"].lower()

    def test_live_mode_without_confirmation_blocks_order(self, monkeypatch):
        """Live port enabled but IBKR_LIVE_TRADING_CONFIRMED not set → blocked."""
        monkeypatch.setenv("IBKR_ENABLED", "true")
        monkeypatch.setenv("IBKR_LIVE_TRADING_CONFIRMED", "false")
        import ibkr.client as client_mod
        import ibkr.orders as orders_mod
        import importlib
        importlib.reload(client_mod)
        importlib.reload(orders_mod)

        # Patch is_connected() and account_mode() to simulate a live connection
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
        monkeypatch.setattr(client_mod, "account_mode", lambda: "live")
        importlib.reload(orders_mod)

        result = orders_mod.place_order("AAPL", "BUY", 10)
        assert result["ok"] is False
        assert "IBKR_LIVE_TRADING_CONFIRMED" in result["error"]

    def test_paper_mode_without_confirmation_is_allowed_past_gate(self, monkeypatch):
        """Paper account does NOT require IBKR_LIVE_TRADING_CONFIRMED."""
        monkeypatch.setenv("IBKR_ENABLED", "true")
        monkeypatch.delenv("IBKR_LIVE_TRADING_CONFIRMED", raising=False)
        import ibkr.client as client_mod
        import ibkr.orders as orders_mod
        import importlib

        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
        monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
        importlib.reload(orders_mod)

        # Safety gate should pass; the subsequent ib_async call will fail
        # (no real IB), but the error should NOT be the gate message.
        result = orders_mod.place_order("AAPL", "BUY", 10)
        # Gate passed — the only failure is the missing ib_async import or no IB object
        assert "IBKR_ENABLED" not in (result.get("error") or "")
        assert "IBKR_LIVE_TRADING_CONFIRMED" not in (result.get("error") or "")


# ── Depth cap ─────────────────────────────────────────────────────────────────

class TestDepthCap:
    def setup_method(self):
        """Reset depth subscriptions before each test."""
        import ibkr.depth as depth_mod
        import importlib
        importlib.reload(depth_mod)
        self.depth = depth_mod

    def test_subscribe_when_disconnected_returns_error(self, monkeypatch):
        import ibkr.client as client_mod
        monkeypatch.setattr(client_mod, "is_connected", lambda: False)
        result = self.depth.subscribe("AAPL")
        assert result["ok"] is False
        assert "connect" in result["error"].lower()

    def test_subscribe_cap_enforced(self, monkeypatch):
        """After IBKR_MAX_DEPTH_SYMBOLS subs, a 4th is rejected."""
        import ibkr.client as client_mod
        from constants import IBKR_MAX_DEPTH_SYMBOLS
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)

        # Fill subscriptions directly (bypass the IB call)
        for i in range(IBKR_MAX_DEPTH_SYMBOLS):
            self.depth._subscriptions[f"SYM{i}"] = {}

        result = self.depth.subscribe("EXTRA")
        assert result["ok"] is False
        assert str(IBKR_MAX_DEPTH_SYMBOLS) in result["error"]

    def test_resubscribe_same_symbol_is_idempotent(self, monkeypatch):
        """Subscribing an already-tracked symbol returns ok immediately."""
        import ibkr.client as client_mod
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        self.depth._subscriptions["AAPL"] = {}
        result = self.depth.subscribe("AAPL")
        assert result["ok"] is True

    def test_subscribed_symbols_list(self):
        """subscribed_symbols() returns the current keys."""
        self.depth._subscriptions = {"AAPL": {}, "TSLA": {}}
        assert set(self.depth.subscribed_symbols()) == {"AAPL", "TSLA"}
