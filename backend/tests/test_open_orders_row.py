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
            auxPrice=0.0,  # unused stop field from IB
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
    assert row["filled_qty"] + row["remaining_qty"] == row["qty"]
    assert row["avg_fill_price"] == 10.2
    assert row["limit_price"] == 10.25
    assert row["stop_price"] is None  # auxPrice 0 → null
    assert row["outside_rth"] is True
    assert row["status"] == "Submitted"
    assert row["submitted_at"] is not None
    assert row["updated_at"] is not None
    assert "09:41:23" in row["updated_at"] or "13:41:23" in row["updated_at"]


def test_trade_to_order_row_null_remaining_when_status_missing():
    trade = SimpleNamespace(
        order=SimpleNamespace(
            orderId=3,
            action="BUY",
            totalQuantity=100,
            orderType="LMT",
            lmtPrice=5.0,
            auxPrice=0.0,
            outsideRth=False,
        ),
        contract=SimpleNamespace(symbol="IBM"),
        orderStatus=SimpleNamespace(
            status="Submitted",
            filled=40,
            remaining=None,
            avgFillPrice=5.01,
        ),
    )
    row = _trade_to_order_row(trade)
    assert row["filled_qty"] == 40.0
    assert row["remaining_qty"] is None
    assert row["avg_fill_price"] == 5.01


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
    assert row["limit_price"] is None
    assert row["stop_price"] is None


def test_trade_to_order_row_stop_and_partial_fields():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    trade = SimpleNamespace(
        order=SimpleNamespace(
            orderId=99,
            action="SELL",
            totalQuantity=50,
            orderType="STP",
            lmtPrice=0.0,
            auxPrice=23.5,
            outsideRth=False,
        ),
        contract=SimpleNamespace(symbol="TSLA"),
        orderStatus=SimpleNamespace(
            status="Submitted",
            filled=0,
            remaining=50,
            avgFillPrice=0.0,
        ),
        log=[SimpleNamespace(time=datetime(2026, 7, 18, 10, 0, 0, tzinfo=et))],
        fills=[],
    )
    row = _trade_to_order_row(trade)
    assert row["order_id"] == 99
    assert row["stop_price"] == 23.5
    assert row["limit_price"] is None
    assert row["filled_qty"] == 0.0
    assert row["remaining_qty"] == 50.0
    assert row["avg_fill_price"] is None
    assert row["submitted_at"] is not None
    # Fill activity must not rewrite submitted snapshot identity.
    assert row["submitted_at"].startswith("2026-07-18T14:00:00")
