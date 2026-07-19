"""Unit tests for IBKR open-order JSON row mapping (no live Gateway)."""

from __future__ import annotations

from types import SimpleNamespace

from ibkr.orders import _trade_to_order_row


def test_trade_to_order_row_includes_fill_progress():
    trade = SimpleNamespace(
        order=SimpleNamespace(
            orderId=7,
            action="BUY",
            totalQuantity=100,
            orderType="LMT",
            lmtPrice=10.25,
            auxPrice=0.0,
            outsideRth=True,
        ),
        contract=SimpleNamespace(symbol="AAPL"),
        orderStatus=SimpleNamespace(
            status="Submitted",
            filled=40,
            remaining=60,
            avgFillPrice=10.2,
        ),
    )
    row = _trade_to_order_row(trade)
    assert row["order_id"] == 7
    assert row["symbol"] == "AAPL"
    assert row["side"] == "BUY"
    assert row["qty"] == 100
    assert row["filled_qty"] == 40.0
    assert row["remaining_qty"] == 60.0
    assert row["avg_fill_price"] == 10.2
    assert row["limit_price"] == 10.25
    assert row["outside_rth"] is True
    assert row["status"] == "Submitted"


def test_trade_to_order_row_omits_zero_avg_fill():
    trade = SimpleNamespace(
        order=SimpleNamespace(
            orderId=1,
            action="SELL",
            totalQuantity=10,
            orderType="MKT",
            lmtPrice=0.0,
            auxPrice=None,
            outsideRth=False,
        ),
        contract=SimpleNamespace(symbol="XYZ"),
        orderStatus=SimpleNamespace(
            status="PreSubmitted",
            filled=0,
            remaining=10,
            avgFillPrice=0.0,
        ),
    )
    row = _trade_to_order_row(trade)
    assert row["filled_qty"] == 0.0
    assert row["avg_fill_price"] is None
