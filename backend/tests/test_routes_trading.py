"""Tests for IBKR trading routes (backend/routes/trading.py).

No live IB Gateway required — execution.service + ibkr adapters are mocked
so these exercise route wiring and the safety-gate contract only.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import app_lifespan
import execution.service as exec_svc
import execution.store as exec_store
import execution.telemetry as exec_telemetry
import ibkr.account as account_mod
import ibkr.client as client_mod
import ibkr.orders as orders_mod
import ibkr.safety as safety_mod
import journal.db as journal_db
import nova_os.events_db as events_db
import strategy.risk as risk_mod
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_execution_ledger(tmp_path, monkeypatch):
    # main.app's lifespan (triggered by TestClient's first request) schedules
    # a real background bootstrap (IBKR ping, strategy.risk.reconstruct_from_journal,
    # nova_os.recovery.run_startup_recovery) via asyncio.create_task. Without
    # this, that task reads/replays the *real* on-disk journal — tripping the
    # process-global strategy.risk._state singleton's loss-halt guardrail and
    # silently rejecting every execute() bracket call for the rest of the
    # pytest session (cross-file pollution). These are route-wiring tests
    # that already mock the IBKR/execution boundary, so the real bootstrap
    # has nothing to do here — stub it out at the source.
    monkeypatch.setattr(app_lifespan, "_bootstrap_runtime", AsyncMock())
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    monkeypatch.setattr(journal_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(events_db, "cache_dir", lambda: tmp_path)
    import execution.broker_send as broker_send

    monkeypatch.setattr(broker_send, "EXECUTION_ACK_WAIT_SEC", 0.05)
    exec_store.init_db()
    journal_db.init_db()
    events_db.init_db()
    exec_telemetry.reset_for_tests()
    risk_mod.reset_day()
    yield
    exec_telemetry.reset_for_tests()
    risk_mod.reset_day()


def _arm_paper_gates():
    # NOTE: patches[2]/[3] mock the *connection* reality (account_mode /
    # broker_account_kind); patches[7] mocks the *env target*
    # (ibkr.safety.gateway_mode reads IBKR_GATEWAY_MODE straight from
    # os.environ in assert_orders_allowed's paper-pin / live-confirm branch,
    # independent of the account_mode/broker_account_kind mocks). Both must
    # be paper here — otherwise these "paper" tests silently depend on
    # whatever IBKR_GATEWAY_MODE happens to be set to in the developer's
    # real .env (see PROBLEM_LOG.md "route tests depend on real .env gateway mode").
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
        patch.dict(os.environ, {"IBKR_GATEWAY_MODE": "paper"}),
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
         patches[7], patch.object(orders_mod, "place_order", return_value=fake_result) as place_mock:
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
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[7], \
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
         patches[7], patch.object(orders_mod, "place_order", return_value=fake_result) as place_mock:
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


def test_order_route_persists_clock_safe_client_measurement():
    fake_result = {"ok": True, "order_id": 45, "error": None, "mode": "paper"}
    patches = _arm_paper_gates()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
         patches[7], patch.object(orders_mod, "place_order", return_value=fake_result):
        res = client.post(
            "/api/ibkr/order",
            json={
                "symbol": "AAPL",
                "side": "BUY",
                "qty": 1,
                "order_type": "LMT",
                "limit_price": 10.0,
                "reference_price": 10.05,
                "idempotency_key": "route-clock-contract",
                "client_timing": {
                    "action_wall_ms": 1_000.0,
                    "action_performance_ms": 10.0,
                    "request_wall_ms": 1_015.0,
                    "request_performance_ms": 25.0,
                },
            },
        )
    assert res.status_code == 200
    body = res.json()
    measurement = body["measurement"]
    assert measurement["browser"]["action_to_request_ms"] == 15.0
    assert measurement["cross_clock_arithmetic"] == "forbidden"
    assert measurement["browser_to_backend_wall_observation"]["latency_usable"] is False
    assert measurement["backend"]["ingress_to_response_ready_ms"] >= 0


def test_order_route_rejects_non_positive_quantity():
    res = client.post(
        "/api/ibkr/order",
        json={"symbol": "AAPL", "side": "BUY", "qty": 0},
    )
    assert res.status_code == 422


def test_execution_latency_route_is_bounded_and_population_labeled():
    res = client.get("/api/ibkr/execution-latency")
    assert res.status_code == 200
    body = res.json()
    assert body["bounded_limit"] == 500
    assert body["clock_contract"]["cross_clock_arithmetic"] == "forbidden"
    assert set(body["segments"]) == {
        "population", "mode", "operation", "source", "fill_provenance",
        "fill_leg",
    }


def test_duplicate_idempotency_key_does_not_resend(monkeypatch):
    fake_result = {"ok": True, "order_id": 88, "error": None, "mode": "paper"}
    patches = _arm_paper_gates()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
         patches[7], patch.object(orders_mod, "place_order", return_value=fake_result) as place_mock:
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


def test_gateway_mode_route_rejects_invalid_mode():
    res = client.post("/api/ibkr/gateway-mode", json={"mode": "bogus"})
    assert res.status_code == 400


def test_gateway_mode_route_delegates_to_client():
    fake_result = {
        "ok": True,
        "error": None,
        "requested_mode": "live",
        "connected": True,
        "mode": "live",
        "broker_account_kind": "live",
        "spend_status": "locked_live_unconfirmed",
    }
    with patch.object(
        client_mod, "request_gateway_mode", new=AsyncMock(return_value=fake_result)
    ) as mock_switch:
        res = client.post("/api/ibkr/gateway-mode", json={"mode": "live"})
    assert res.status_code == 200
    assert res.json() == fake_result
    mock_switch.assert_called_once_with("live")


def test_status_route_reports_safety_snapshot():
    fake_snapshot = {
        "gateway_mode": "paper",
        "orders_enabled": False,
        "live_trading_confirmed": False,
        "spend_status": "locked",
    }
    fake_ports = {
        "preferred_port": 4002,
        "alternate_port": 4001,
        "preferred_port_reachable": False,
        "alternate_port_reachable": True,
        "disconnect_hint": "paper_port_refused_live_listening",
        "live_port": 4001,
        "paper_port": 4002,
    }
    with patch.object(safety_mod, "status_snapshot", return_value=fake_snapshot), \
         patch.object(client_mod, "is_enabled", return_value=False), \
         patch.object(client_mod, "is_connected", return_value=False), \
         patch.object(client_mod, "account_mode", return_value="disconnected"), \
         patch("ibkr.port_diagnostics.status_port_fields", return_value=fake_ports):
        res = client.get("/api/ibkr/status")
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is False
    assert body["connected"] is False
    assert body["spend_status"] == "locked"
    assert body["disconnect_hint"] == "paper_port_refused_live_listening"
    assert body["preferred_port"] == 4002
