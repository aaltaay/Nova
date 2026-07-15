"""Tests for IBKR trading routes (backend/routes/trading.py).

No live IB Gateway required — ibkr.safety / ibkr.client / ibkr.orders are
mocked so these exercise route wiring and the safety-gate contract only.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

import ibkr.client as client_mod
import ibkr.orders as orders_mod
import ibkr.safety as safety_mod
from main import app

client = TestClient(app)


def test_place_order_route_blocked_when_safety_gate_fails():
    """A failing safety gate must surface as ok=False with the gate's reason,
    never as a silent success (see ibkr/safety.py — single source of truth)."""
    with patch.object(
        safety_mod, "assert_orders_allowed",
        return_value=(False, "IBKR_ORDERS_ENABLED is false — orders locked"),
    ):
        res = client.post(
            "/api/ibkr/order",
            json={"symbol": "aapl", "side": "buy", "qty": 10},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert body["order_id"] is None
    assert "IBKR_ORDERS_ENABLED" in body["error"]


def test_place_order_route_happy_path_delegates_to_orders_module():
    fake_result = {"ok": True, "order_id": 42, "error": None, "mode": "paper"}
    with patch.object(orders_mod, "place_order", return_value=fake_result) as place_mock:
        res = client.post(
            "/api/ibkr/order",
            json={"symbol": "aapl", "side": "buy", "qty": 5, "order_type": "mkt"},
        )
    assert res.status_code == 200
    assert res.json() == fake_result
    place_mock.assert_called_once_with(
        symbol="AAPL", side="BUY", qty=5, order_type="MKT", limit_price=None,
    )


def test_cancel_order_route_blocked_when_not_connected():
    with patch.object(client_mod, "is_connected", return_value=False), \
         patch.object(client_mod, "is_enabled", return_value=True):
        res = client.delete("/api/ibkr/order/123")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert "connected" in body["error"].lower()


def test_status_route_reports_safety_snapshot():
    fake_snapshot = {
        "gateway_mode": "paper",
        "orders_enabled": False,
        "live_trading_confirmed": False,
        "spend_status": "locked",
    }
    with patch.object(safety_mod, "status_snapshot", return_value=fake_snapshot), \
         patch.object(client_mod, "is_enabled", return_value=False), \
         patch.object(client_mod, "is_connected", return_value=False), \
         patch.object(client_mod, "account_mode", return_value="disconnected"):
        res = client.get("/api/ibkr/status")
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is False
    assert body["connected"] is False
    assert body["spend_status"] == "locked"
