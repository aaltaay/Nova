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


def test_place_order_route_happy_path_delegates_to_orders_module(monkeypatch):
    # Route wiring asserts requested qty; disable MASTER TEST QTY GATE for this test.
    monkeypatch.setattr(exec_svc, "IBKR_FORCE_ONE_SHARE", False)
    import execution.qty_gate as qty_gate

    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", False)
    fake_result = {"ok": True, "order_id": 42, "error": None, "mode": "paper"}
    patches = _arm_paper_gates()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
         patches[7], patches[8], \
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


def test_stop_limit_route_delegates_both_prices():
    fake_result = {"ok": True, "order_id": 46, "error": None, "mode": "paper"}
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
                "order_type": "stp lmt",
                "stop_price": 210.5,
                "limit_price": 210.0,
                "idempotency_key": "route-stplmt",
            },
        )
    assert res.status_code == 200
    assert res.json()["ok"] is True
    kwargs = place_mock.call_args.kwargs
    assert kwargs["order_type"] == "STP LMT"
    assert kwargs["stop_price"] == 210.5
    assert kwargs["limit_price"] == 210.0


def test_trail_route_delegates_trail_dollars_as_stop_price():
    fake_result = {"ok": True, "order_id": 47, "error": None, "mode": "paper"}
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
                "order_type": "trail",
                "stop_price": 0.35,
                "idempotency_key": "route-trail",
            },
        )
    assert res.status_code == 200
    assert res.json()["ok"] is True
    kwargs = place_mock.call_args.kwargs
    assert kwargs["order_type"] == "TRAIL"
    assert kwargs["stop_price"] == 0.35


def test_limit_order_route_delegates_extended_hours():
    fake_result = {"ok": True, "order_id": 44, "error": None, "mode": "paper"}
    patches = _arm_paper_gates()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
         patches[7], patches[8], \
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


def test_order_route_persists_clock_safe_client_measurement():
    fake_result = {"ok": True, "order_id": 45, "error": None, "mode": "paper"}
    patches = _arm_paper_gates()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
         patches[7], patches[8], \
         patch.object(orders_mod, "place_order", return_value=fake_result):
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


def test_executions_list_route_returns_shaped_rows():
    execution_id, _ = exec_store.reserve(
        idempotency_key="route-activity",
        operation="place",
        source="manual",
        symbol="IVF",
        received_ns=1,
        payload={"side": "BUY", "requested_qty": 10, "sent_qty": 1, "forced_one_share": True},
    )
    exec_store.update_stages(execution_id, status="filled", order_id=19112)
    res = client.get("/api/ibkr/executions?symbol=IVF")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["id"] == execution_id
    assert body[0]["requested_qty"] == 10
    assert body[0]["sent_qty"] == 1
    assert body[0]["forced_one_share"] is True


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
         patches[7], patches[8], \
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


def test_order_route_defaults_tif_to_day_and_forwards_gtc(monkeypatch):
    """#91: the ticket's TIF reaches the adapter; omitting it still means DAY."""
    fake_result = {"ok": True, "order_id": 51, "error": None, "mode": "paper"}
    patches = _arm_paper_gates()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
         patches[7], patches[8], \
         patch.object(orders_mod, "place_order", return_value=fake_result) as place_mock:
        base = {
            "symbol": "AAPL", "side": "BUY", "qty": 1,
            "order_type": "lmt", "limit_price": 10.0,
        }
        client.post("/api/ibkr/order", json={**base, "idempotency_key": "route-tif-day"})
        client.post(
            "/api/ibkr/order",
            json={**base, "tif": "gtc", "idempotency_key": "route-tif-gtc"},
        )
    assert place_mock.call_args_list[0].kwargs["tif"] == "DAY"
    assert place_mock.call_args_list[1].kwargs["tif"] == "GTC"


def test_order_route_protective_legs_place_one_bracket():
    """Defaults on → one bracket through execute(), never a second place."""
    fake_bracket = {
        "ok": True, "parent_order_id": 61, "target_order_id": 62,
        "stop_order_id": 63, "error": None, "mode": "paper",
    }
    patches = _arm_paper_gates()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
         patches[7], patches[8], \
         patch.object(orders_mod, "place_order") as place_mock, \
         patch.object(
             orders_mod, "place_bracket_order", return_value=fake_bracket,
         ) as bracket_mock:
        res = client.post(
            "/api/ibkr/order",
            json={
                "symbol": "AAPL", "side": "BUY", "qty": 1, "order_type": "LMT",
                "limit_price": 10.0, "take_profit_price": 10.5,
                "stop_loss_price": 9.8, "tif": "GTC", "outside_rth": True,
                "idempotency_key": "route-legs",
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["parent_order_id"] == 61
    assert body["target_order_id"] == 62
    assert body["stop_order_id"] == 63
    place_mock.assert_not_called()
    kwargs = bracket_mock.call_args.kwargs
    assert kwargs["entry_price"] == 10.0
    assert kwargs["target_price"] == 10.5
    assert kwargs["stop_price"] == 9.8
    assert kwargs["tif"] == "GTC"
    assert kwargs["outside_rth"] is True


def test_order_route_refuses_legs_without_a_limit_entry():
    res = client.post(
        "/api/ibkr/order",
        json={
            "symbol": "AAPL", "side": "BUY", "qty": 1, "order_type": "MKT",
            "take_profit_price": 10.5, "stop_loss_price": 9.8,
        },
    )
    assert res.status_code == 422


def test_order_route_refuses_one_sided_legs():
    res = client.post(
        "/api/ibkr/order",
        json={
            "symbol": "AAPL", "side": "BUY", "qty": 1, "order_type": "LMT",
            "limit_price": 10.0, "stop_loss_price": 9.8,
        },
    )
    assert res.status_code == 422


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
         patch.object(client_mod, "is_ready", return_value=False), \
         patch.object(client_mod, "is_connected", return_value=False), \
         patch.object(client_mod, "session_reason", return_value="disabled"), \
         patch.object(client_mod, "account_mode", return_value="disconnected"), \
         patch.object(client_mod, "get_market_data_type", return_value=1), \
         patch("ibkr.session_errors.is_delayed_data", return_value=True), \
         patch("ibkr.port_diagnostics.status_port_fields", return_value=fake_ports) as ports:
        res = client.get("/api/ibkr/status")
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is False
    assert body["connected"] is False
    assert body["transport_connected"] is False
    assert body["session_reason"] == "disabled"
    assert body["spend_status"] == "locked"
    assert body["trading_allowed"] is False
    assert body["trading_allowed_reason"]
    assert body["disconnect_hint"] == "paper_port_refused_live_listening"
    assert body["preferred_port"] == 4002
    assert body["market_data_type"] == 1
    assert body["market_data_delayed"] is True
    # Port hints must key off transport, not usable.
    ports.assert_called_once_with(connected=False)


def test_status_route_connected_means_usable_not_transport():
    """Socket up + degraded → connected false; transport_connected true."""
    fake_snapshot = {
        "gateway_mode": "paper",
        "orders_enabled": False,
        "live_trading_confirmed": False,
        "spend_status": "locked",
    }
    with patch.object(safety_mod, "status_snapshot", return_value=fake_snapshot), \
         patch.object(client_mod, "is_enabled", return_value=True), \
         patch.object(client_mod, "is_ready", return_value=False), \
         patch.object(client_mod, "is_connected", return_value=True), \
         patch.object(client_mod, "session_reason", return_value="connectivity_lost"), \
         patch.object(client_mod, "account_mode", return_value="paper"), \
         patch.object(client_mod, "broker_account_kind", return_value="paper"), \
         patch.object(client_mod, "get_market_data_type", return_value=1), \
         patch("ibkr.session_errors.is_delayed_data", return_value=False), \
         patch("ibkr.port_diagnostics.status_port_fields", return_value={
             "preferred_port": 4002,
             "alternate_port": 4001,
             "preferred_port_reachable": True,
             "alternate_port_reachable": False,
             "disconnect_hint": "paper_port_open_but_disconnected",
             "live_port": 4001,
             "paper_port": 4002,
         }) as ports:
        res = client.get("/api/ibkr/status")
    body = res.json()
    assert body["connected"] is False
    assert body["transport_connected"] is True
    assert body["session_reason"] == "connectivity_lost"
    ports.assert_called_once_with(connected=True)


def test_status_route_surfaces_freeze_diagnostics():
    """PROBLEM_LOG 2026-08-31 -- one query instead of an hour of log
    archaeology the next time the session freezes with the port open."""
    fake_snapshot = {
        "gateway_mode": "live",
        "orders_enabled": False,
        "live_trading_confirmed": False,
        "spend_status": "locked",
    }
    with patch.object(safety_mod, "status_snapshot", return_value=fake_snapshot), \
         patch.object(client_mod, "is_enabled", return_value=True), \
         patch.object(client_mod, "is_ready", return_value=False), \
         patch.object(client_mod, "is_connected", return_value=True), \
         patch.object(client_mod, "session_reason", return_value="connectivity_restored"), \
         patch.object(client_mod, "account_mode", return_value="live"), \
         patch.object(client_mod, "broker_account_kind", return_value="live"), \
         patch.object(client_mod, "get_market_data_type", return_value=1), \
         patch("ibkr.session_errors.is_delayed_data", return_value=False), \
         patch("ibkr.port_diagnostics.status_port_fields", return_value={
             "preferred_port": 4001,
             "alternate_port": 4002,
             "preferred_port_reachable": True,
             "alternate_port_reachable": False,
             "disconnect_hint": None,
             "live_port": 4001,
             "paper_port": 4002,
         }), \
         patch("ibkr.session_usable.earn_in_flight", return_value=False), \
         patch("ibkr.ib_scheduler.inflight_label", return_value=""), \
         patch("ibkr.session_reconnect.dialer_heartbeat_age_sec", return_value=25200.0):
        res = client.get("/api/ibkr/status")
    body = res.json()
    assert body["earn_in_flight"] is False
    assert body["ib_cold_inflight"] is None
    assert body["dialer_heartbeat_age_sec"] == 25200.0


def test_status_route_surfaces_completed_orders_unanswered_since():
    """D-058: READY desk, but the Gateway stopped answering reqCompletedOrders."""
    fake_snapshot = {
        "gateway_mode": "live",
        "orders_enabled": False,
        "live_trading_confirmed": False,
        "spend_status": "locked",
    }
    with patch.object(safety_mod, "status_snapshot", return_value=fake_snapshot), \
         patch.object(client_mod, "is_enabled", return_value=True), \
         patch.object(client_mod, "is_ready", return_value=True), \
         patch.object(client_mod, "is_connected", return_value=True), \
         patch.object(client_mod, "session_reason", return_value="ok"), \
         patch.object(client_mod, "account_mode", return_value="live"), \
         patch.object(client_mod, "broker_account_kind", return_value="live"), \
         patch.object(client_mod, "get_market_data_type", return_value=1), \
         patch("ibkr.session_errors.is_delayed_data", return_value=False), \
         patch("ibkr.completed_orders_health.warn_since", return_value=1789808049.0):
        res = client.get("/api/ibkr/status")
        assert res.json()["completed_orders_unanswered_since"] == 1789808049.0
        # Not usable -> never report a verdict that may belong to a replaced session.
        with patch.object(client_mod, "is_ready", return_value=False):
            res = client.get("/api/ibkr/status")
        assert res.json()["completed_orders_unanswered_since"] is None


def test_status_route_surfaces_gateway_read_only():
    """D-076: Read-Only API rejected an order -- name it instead of 'login/2FA'."""
    fake_snapshot = {
        "gateway_mode": "live",
        "orders_enabled": False,
        "live_trading_confirmed": False,
        "spend_status": "locked",
    }
    with patch.object(safety_mod, "status_snapshot", return_value=fake_snapshot), \
         patch.object(client_mod, "is_enabled", return_value=True), \
         patch.object(client_mod, "is_ready", return_value=True), \
         patch.object(client_mod, "is_connected", return_value=True), \
         patch.object(client_mod, "session_reason", return_value="ok"), \
         patch.object(client_mod, "account_mode", return_value="live"), \
         patch.object(client_mod, "broker_account_kind", return_value="live"), \
         patch.object(client_mod, "get_market_data_type", return_value=1), \
         patch("ibkr.session_errors.is_delayed_data", return_value=False):
        with patch("ibkr.session_errors.gateway_read_only", return_value=True), \
             patch(
                 "ibkr.session_errors.gateway_read_only_since",
                 return_value=1789808049.0,
             ):
            body = client.get("/api/ibkr/status").json()
        assert body["gateway_read_only"] is True
        assert body["gateway_read_only_since"] == 1789808049.0
        # The session is still READY -- read-only is not a connection fault.
        assert body["connected"] is True

        body = client.get("/api/ibkr/status").json()
        assert body["gateway_read_only"] is False
        assert body["gateway_read_only_since"] is None


def test_status_route_includes_reqmkt_data_budget():
    """D-039: /api/ibkr/status exposes the Error 101 ticker ceiling."""
    fake_snapshot = {
        "gateway_mode": "paper",
        "orders_enabled": False,
        "live_trading_confirmed": False,
        "spend_status": "locked",
    }
    budget = {
        "reqMktData_lines": 3,
        "reqMktData_by_owner": {"detail": 1, "scanner": 2, "hod": 1},
        "reqMktData_limit": 100,
        "reqMktData_remaining": 97,
        "max_tickers_hit": False,
        "max_tickers_ts": None,
    }
    with patch.object(safety_mod, "status_snapshot", return_value=fake_snapshot), \
         patch.object(client_mod, "is_enabled", return_value=True), \
         patch.object(client_mod, "is_ready", return_value=True), \
         patch.object(client_mod, "is_connected", return_value=True), \
         patch.object(client_mod, "session_reason", return_value="ok"), \
         patch.object(client_mod, "account_mode", return_value="paper"), \
         patch.object(client_mod, "broker_account_kind", return_value="paper"), \
         patch.object(client_mod, "get_market_data_type", return_value=1), \
         patch("ibkr.session_errors.is_delayed_data", return_value=False), \
         patch("ibkr.port_diagnostics.status_port_fields", return_value={
             "preferred_port": 4002,
             "alternate_port": 4001,
             "preferred_port_reachable": True,
             "alternate_port_reachable": False,
             "disconnect_hint": None,
             "live_port": 4001,
             "paper_port": 4002,
         }), \
         patch("ibkr.ticks.ticker_budget_status", return_value=budget):
        res = client.get("/api/ibkr/status")
    body = res.json()
    assert body["reqMktData_lines"] == 3
    assert body["reqMktData_limit"] == 100
    assert body["reqMktData_remaining"] == 97
    assert body["max_tickers_hit"] is False


def test_launch_gateway_route_already_listening_and_ready_is_a_noop():
    """Session is fine -- the button should just focus the window, no rebuild."""
    fake_launch = {
        "ok": True,
        "action": "already_listening",
        "mode": "live",
        "message": "LIVE Gateway is already listening on port 4001.",
    }
    with patch("ibkr.launch_gateway.launch_or_focus_gateway", return_value=fake_launch), \
         patch.object(client_mod, "is_ready", return_value=True):
        res = client.post("/api/ibkr/launch-gateway", json={"mode": "live"})
    assert res.status_code == 200
    assert res.json() == fake_launch


def test_launch_gateway_route_rebuilds_session_when_port_open_but_not_ready():
    """PROBLEM_LOG 2026-08-31 -- Open live/paper Gateway must not be a no-op
    when Gateway is fine but Nova's own session never reached READY."""
    fake_launch = {
        "ok": True,
        "action": "already_listening",
        "mode": "live",
        "message": "LIVE Gateway is already listening on port 4001.",
    }
    fake_rebuild = {
        "connected": True,
        "session_state": "ready",
        "session_reason": "ok",
    }
    with patch("ibkr.launch_gateway.launch_or_focus_gateway", return_value=fake_launch), \
         patch.object(client_mod, "is_ready", return_value=False), \
         patch.object(
             client_mod, "force_reconnect", new=AsyncMock(return_value=fake_rebuild)
         ) as mock_rebuild:
        res = client.post("/api/ibkr/launch-gateway", json={"mode": "live"})
    assert res.status_code == 200
    body = res.json()
    assert body["action"] == "rebuild_session"
    assert body["connected"] is True
    assert body["session_state"] == "ready"
    assert "rebuilt the connection" in body["message"]
    mock_rebuild.assert_called_once_with()


def test_launch_gateway_route_does_not_rebuild_when_not_already_listening():
    """focused_authenticating (2FA in progress) must not trigger a rebuild --
    there is nothing to dial yet."""
    fake_launch = {
        "ok": True,
        "action": "focused_authenticating",
        "mode": "live",
        "message": "Gateway is already running and the API port is not open yet.",
    }
    with patch("ibkr.launch_gateway.launch_or_focus_gateway", return_value=fake_launch), \
         patch.object(client_mod, "is_ready", return_value=False), \
         patch.object(client_mod, "force_reconnect", new=AsyncMock()) as mock_rebuild:
        res = client.post("/api/ibkr/launch-gateway", json={"mode": "live"})
    assert res.status_code == 200
    assert res.json() == fake_launch
    mock_rebuild.assert_not_called()


# ── ADR 018: the arm latch endpoint the header padlock posts to ───────────────

def test_arm_route_arms_and_disarms_this_process():
    res = client.post("/api/ibkr/arm", json={"armed": False})
    assert res.status_code == 200
    assert res.json()["armed"] is False
    assert safety_mod.armed() is False

    res = client.post("/api/ibkr/arm", json={"armed": True})
    assert res.status_code == 200
    assert res.json()["armed"] is True
    assert safety_mod.armed() is True


def test_arm_route_refuses_a_malformed_body_rather_than_arming():
    """A body Nova cannot read must never be taken as a request to arm."""
    safety_mod.set_armed(False, reason="test")
    for bad in ({}, {"armed": "yes"}, {"arm": True}):
        res = client.post("/api/ibkr/arm", json=bad)
        assert res.status_code == 422, bad
        assert safety_mod.armed() is False


def test_arm_route_reports_disarmed_as_locked_not_armed():
    """spend_status must fail closed so no surface reads a disarmed desk as armed."""
    patches = _arm_paper_gates()
    with patches[0], patches[1], patches[2], patches[3], patches[5], patches[7]:
        client.post("/api/ibkr/arm", json={"armed": False})
        snap = client.post("/api/ibkr/arm", json={"armed": False}).json()
        assert snap["armed"] is False
        assert snap["spend_status"] == "locked_disarmed"
        # The environment still permits spending -- only this process does not.
        assert snap["spend_permitted"] is True
        assert snap["armed_for_account_kind"] is None
