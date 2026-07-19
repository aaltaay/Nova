"""Unit tests for IBKR open-order JSON row mapping (no live Gateway)."""

from __future__ import annotations

from types import SimpleNamespace

from ibkr.orders import _trade_to_order_row


def test_trade_to_order_row_includes_fill_progress():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
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
        log=[SimpleNamespace(time=datetime(2026, 7, 18, 9, 30, 0, tzinfo=et))],
        fills=[
            SimpleNamespace(
                execution=SimpleNamespace(
                    time=datetime(2026, 7, 18, 9, 41, 23, tzinfo=et),
                ),
            ),
        ],
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
    assert row["submitted_at"] is not None
    assert row["updated_at"] is not None
    assert "09:41:23" in row["updated_at"] or "13:41:23" in row["updated_at"]


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
