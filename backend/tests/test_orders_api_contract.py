"""
L2 Orders pyramid — HTTP contract for open/closed order JSON.

No live IB Gateway. Routes return mocked rows; asserts field presence and
filled+remaining==qty when both quantities are present.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

import ibkr.client as client_mod
import routes.trading as trading_routes
from ibkr.errors import IbkrAccountError
from main import app

client = TestClient(app)

WORKING_PARTIAL = {
    "order_id": 4242,
    "symbol": "AAPL",
    "side": "BUY",
    "qty": 100,
    "filled_qty": 40.0,
    "remaining_qty": 60.0,
    "order_type": "LMT",
    "limit_price": 190.55,
    "stop_price": None,
    "avg_fill_price": 190.42,
    "outside_rth": False,
    "status": "Submitted",
    "submitted_at": "2026-07-18T13:41:23.000Z",
    "updated_at": "2026-07-18T18:00:00.000Z",
}

WORKING_NULL_REMAINING = {
    **WORKING_PARTIAL,
    "order_id": 4243,
    "filled_qty": 40.0,
    "remaining_qty": None,
}

CLOSED_FILLED = {
    "order_id": 9001,
    "symbol": "AAPL",
    "side": "BUY",
    "qty": 100,
    "filled_qty": 100.0,
    "remaining_qty": 0.0,
    "order_type": "LMT",
    "limit_price": 12.5,
    "stop_price": None,
    "avg_fill_price": 12.48,
    "outside_rth": False,
    "status": "Filled",
    "submitted_at": "2026-07-18T13:00:00.000Z",
    "updated_at": "2026-07-18T13:41:23.000Z",
}

CLOSED_PARTIAL_CANCEL = {
    "order_id": 9004,
    "symbol": "AAPL",
    "side": "BUY",
    "qty": 100,
    "filled_qty": 35.0,
    "remaining_qty": 0.0,
    "order_type": "LMT",
    "limit_price": 12.6,
    "stop_price": None,
    "avg_fill_price": 12.59,
    "outside_rth": False,
    "status": "Cancelled",
    "submitted_at": "2026-07-18T12:00:00.000Z",
    "updated_at": "2026-07-18T12:30:00.000Z",
}

_REQUIRED_KEYS = {
    "order_id",
    "symbol",
    "side",
    "qty",
    "filled_qty",
    "remaining_qty",
    "order_type",
    "limit_price",
    "stop_price",
    "avg_fill_price",
    "outside_rth",
    "status",
    "submitted_at",
    "updated_at",
}


def _assert_row_shape(row: dict) -> None:
    missing = _REQUIRED_KEYS - set(row)
    assert not missing, f"missing keys: {missing}"


def test_get_open_orders_contract_fields_and_invariant():
    with (
        patch.object(client_mod, "is_connected", return_value=True),
        patch.object(
            trading_routes._orders,
            "open_orders",
            return_value=[WORKING_PARTIAL, WORKING_NULL_REMAINING],
        ),
    ):
        res = client.get("/api/ibkr/orders")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 2
    for row in rows:
        _assert_row_shape(row)

    partial = next(r for r in rows if r["order_id"] == 4242)
    assert partial["filled_qty"] + partial["remaining_qty"] == partial["qty"]
    assert partial["limit_price"] == 190.55
    assert partial["avg_fill_price"] == 190.42
    assert partial["submitted_at"] == "2026-07-18T13:41:23.000Z"

    null_rem = next(r for r in rows if r["order_id"] == 4243)
    assert null_rem["remaining_qty"] is None
    assert null_rem["filled_qty"] == 40.0


def test_get_closed_orders_contract_fields():
    with (
        patch.object(client_mod, "is_connected", return_value=True),
        patch.object(
            trading_routes._orders,
            "closed_orders",
            return_value=[CLOSED_FILLED, CLOSED_PARTIAL_CANCEL],
        ),
    ):
        res = client.get("/api/ibkr/orders/closed")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 2
    for row in rows:
        _assert_row_shape(row)

    filled = next(r for r in rows if r["order_id"] == 9001)
    assert filled["filled_qty"] + filled["remaining_qty"] == filled["qty"]
    assert filled["status"] == "Filled"

    partial_cancel = next(r for r in rows if r["order_id"] == 9004)
    assert partial_cancel["filled_qty"] == 35.0
    assert partial_cancel["remaining_qty"] == 0.0
    assert partial_cancel["status"] == "Cancelled"


def test_open_orders_route_returns_503_not_empty_list_on_failure():
    """A read failure must surface as an honest error, never as '[]' (which
    the UI would render as 'No open orders.')."""
    with patch.object(
        trading_routes._orders,
        "open_orders",
        side_effect=IbkrAccountError("open_orders failed: boom"),
    ):
        res = client.get("/api/ibkr/orders")
    assert res.status_code == 503
    assert "boom" in res.json()["detail"]


def test_positions_route_returns_503_not_empty_list_on_failure():
    with patch.object(
        trading_routes._account,
        "positions_for_ui",
        side_effect=IbkrAccountError("get_positions failed: boom"),
    ):
        res = client.get("/api/ibkr/positions")
    assert res.status_code == 503
    assert "boom" in res.json()["detail"]


def test_account_route_returns_503_on_summary_failure():
    async def _boom():
        raise IbkrAccountError("refresh_account_summary failed: boom")

    with patch.object(
        trading_routes._account,
        "refresh_account_summary",
        side_effect=_boom,
    ):
        res = client.get("/api/ibkr/account")
    assert res.status_code == 503
    assert "boom" in res.json()["detail"]


def test_positions_route_does_not_invent_long_from_portfolio(monkeypatch):
    """Split-brain: portfolio shows SPY, positions empty → HTTP 200 + []."""
    import ibkr.account as account_mod

    monkeypatch.setattr(account_mod, "get_positions", lambda: [])
    monkeypatch.setattr(
        account_mod,
        "get_portfolio",
        lambda: [{
            "symbol": "SPY",
            "qty": 1,
            "market_price": 500.0,
            "market_value": 500.0,
            "avg_cost": 490.0,
            "unrealized_pnl": 10.0,
            "realized_pnl": 0.0,
        }],
    )
    res = client.get("/api/ibkr/positions")
    assert res.status_code == 200
    assert res.json() == []


def test_closed_orders_route_returns_503_not_empty_list_on_failure():
    with patch.object(
        trading_routes._orders,
        "closed_orders",
        side_effect=IbkrAccountError("closed_orders failed: boom"),
    ):
        res = client.get("/api/ibkr/orders/closed")
    assert res.status_code == 503
    assert "boom" in res.json()["detail"]


def test_cancel_orders_for_symbol_returns_error_dict_not_500_on_failure():
    with patch.object(
        trading_routes._orders,
        "open_orders",
        side_effect=IbkrAccountError("open_orders failed: boom"),
    ):
        res = client.delete("/api/ibkr/orders", params={"symbol": "AAPL"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert "boom" in body["error"]
    assert body["cancelled"] == []
    assert body["failed"] == []
