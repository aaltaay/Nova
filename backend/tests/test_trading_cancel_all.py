"""Cancel-all-for-symbol orchestration route (Phase G3)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from main import app
from ibkr import orders as orders_mod

client = TestClient(app)


def test_cancel_orders_for_symbol_requires_symbol():
    res = client.delete("/api/ibkr/orders?symbol=")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False
    assert "symbol" in (body.get("error") or "").lower()


def test_cancel_orders_for_symbol_loops_matching_orders():
    open_rows = [
        {"order_id": 11, "symbol": "AAPL", "side": "BUY"},
        {"order_id": 12, "symbol": "MSFT", "side": "SELL"},
        {"order_id": 13, "symbol": "AAPL", "side": "SELL"},
    ]
    receipt_ok = type("R", (), {
        "ok": True,
        "error": None,
        "execution_id": "e1",
        "timings": None,
        "broker_status": None,
        "duplicate": False,
    })()

    with patch.object(orders_mod, "open_orders", return_value=open_rows), \
         patch("execution.service.execute", new_callable=AsyncMock, return_value=receipt_ok) as exec_mock:
        res = client.delete("/api/ibkr/orders?symbol=aapl")

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["symbol"] == "AAPL"
    assert body["cancelled"] == [11, 13]
    assert body["failed"] == []
    assert exec_mock.await_count == 2


def test_cancel_orders_for_symbol_empty_when_no_match():
    with patch.object(orders_mod, "open_orders", return_value=[
        {"order_id": 1, "symbol": "MSFT"},
    ]), patch("execution.service.execute", new_callable=AsyncMock) as exec_mock:
        res = client.delete("/api/ibkr/orders?symbol=AAPL")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["cancelled"] == []
    exec_mock.assert_not_awaited()
