"""Tests for IBKR trading routes (backend/routes/trading.py).

No live IB Gateway required — execution.service + ibkr adapters are mocked
so these exercise route wiring and the safety-gate contract only.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import execution.service as exec_svc
import execution.store as exec_store
import execution.telemetry as exec_telemetry
import ibkr.account as account_mod
import ibkr.client as client_mod
import ibkr.orders as orders_mod
import ibkr.safety as safety_mod
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_execution_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    import execution.broker_send as broker_send

    monkeypatch.setattr(broker_send, "EXECUTION_ACK_WAIT_SEC", 0.05)
    exec_store.init_db()
    exec_telemetry.reset_for_tests()
    yield
    exec_telemetry.reset_for_tests()


def _arm_paper_gates():
    return (
        patch.object(client_mod, "is_enabled", return_value=True),
        patch.object(client_mod, "is_connected", return_value=True),
        patch.object(client_mod, "account_mode", return_value="paper"),
        patch.object(client_mod, "broker_account_kind", return_value="paper"),
        patch.object(client_mod, "get_ib", return_value=None),
        patch.object(safety_mod, "orders_enabled", return_value=True),
        patch.object(
            account_mod,
            "get_account_summary",
            return_value={"connected": True, "BuyingPower": 1_000_000.0, "pending": False},
        ),
        patch.object(account_mod, "get_positions", return_value=[]),
    )


def test_place_order_route_blocked_when_safety_gate_fails():
    """A failing safety gate must surface as ok=False with the gate's reason,
    never as a silent success (see ibkr/safety.py — single source of truth)."""
    with patch.object(client_mod, "is_enabled", return_value=True), \
         patch.object(client_mod, "is_connected", return_value=True), \
         patch.object(client_mod, "account_mode", return_value="paper"), \
         patch.object(client_mod, "broker_account_kind", return_value="paper"), \
         patch.object(safety_mod, "orders_enabled", return_value=False):
        res = client.post(
            "/api/ibkr/order",
            json={
                "symbol": "aapl",
                "side": "buy",
                "qty": 10,
                "idempotency_key": "route-blocked-1",
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert body["order_id"] is None
    assert "IBKR_ORDERS_ENABLED" in body["error"]


def test_place_order_route_happy_path_delegates_to_orders_module():
    fake_result = {"ok": True, "order_id": 42, "error": None, "mode": "paper"}
    patches = _arm_paper_gates()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
         patch.object(orders_mod, "place_order", return_value=fake_result) as place_mock:
        res = client.post(
            "/api/ibkr/order",
            json={
                "symbol": "aapl",
                "side": "buy",
                "qty": 5,
                "order_type": "mkt",
                "idempotency_key": "route-place-mkt",
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["order_id"] == 42
    assert body["execution_id"]
    place_mock.assert_called_once()
    kwargs = place_mock.call_args.kwargs
    assert kwargs["symbol"] == "AAPL"
    assert kwargs["side"] == "BUY"
    assert kwargs["qty"] == 5.0
    assert kwargs["order_type"] == "MKT"


def test_stop_order_route_delegates_stop_price():
    fake_result = {"ok": True, "order_id": 43, "error": None, "mode": "paper"}
    patches = _arm_paper_gates()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patch.object(
             account_mod,
             "get_positions",
             return_value=[{"symbol": "TSLA", "qty": 25.0}],
         ), \
         patch.object(orders_mod, "place_order", return_value=fake_result) as place_mock:
        res = client.post(
            "/api/ibkr/order",
            json={
                "symbol": "tsla",
                "side": "sell",
                "qty": 25,
                "order_type": "stp",
                "stop_price": 210.5,
                "idempotency_key": "route-stp",
            },
        )
    assert res.status_code == 200
    assert res.json()["ok"] is True
    kwargs = place_mock.call_args.kwargs
    assert kwargs["symbol"] == "TSLA"
    assert kwargs["side"] == "SELL"
    assert kwargs["order_type"] == "STP"
    assert kwargs["stop_price"] == 210.5


def test_limit_order_route_delegates_extended_hours():
    fake_result = {"ok": True, "order_id": 44, "error": None, "mode": "paper"}
    patches = _arm_paper_gates()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
         patch.object(orders_mod, "place_order", return_value=fake_result) as place_mock:
        res = client.post(
            "/api/ibkr/order",
            json={
                "symbol": "nvda",
                "side": "buy",
                "qty": 10,
                "order_type": "lmt",
                "limit_price": 150.25,
                "outside_rth": True,
                "idempotency_key": "route-lmt-rth",
            },
        )
    assert res.status_code == 200
    assert res.json()["ok"] is True
    kwargs = place_mock.call_args.kwargs
    assert kwargs["symbol"] == "NVDA"
    assert kwargs["order_type"] == "LMT"
    assert kwargs["limit_price"] == 150.25
    assert kwargs["outside_rth"] is True


def test_order_route_rejects_non_positive_quantity():
    res = client.post(
        "/api/ibkr/order",
        json={"symbol": "AAPL", "side": "BUY", "qty": 0},
    )
    assert res.status_code == 422


def test_duplicate_idempotency_key_does_not_resend(monkeypatch):
    fake_result = {"ok": True, "order_id": 88, "error": None, "mode": "paper"}
    patches = _arm_paper_gates()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
         patch.object(orders_mod, "place_order", return_value=fake_result) as place_mock:
        body = {
            "symbol": "AAPL",
            "side": "BUY",
            "qty": 1,
            "order_type": "MKT",
            "idempotency_key": "route-dup",
        }
        r1 = client.post("/api/ibkr/order", json=body)
        r2 = client.post("/api/ibkr/order", json=body)
    assert r1.json()["ok"] is True
    assert r2.json()["duplicate"] is True
    assert place_mock.call_count == 1


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
