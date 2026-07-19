"""Pure validation and construction tests for manual IBKR orders."""

from __future__ import annotations

from ibkr import orders


def test_validation_requires_limit_price():
    error = orders._validation_error("BUY", 10, "LMT", None, None, False)
    assert error == "limit_price must be greater than zero for LMT"


def test_validation_requires_stop_price():
    error = orders._validation_error("SELL", 10, "STP", None, None, False)
    assert error == "stop_price must be greater than zero for STP"


def test_validation_rejects_extended_hours_market_and_stop():
    market_error = orders._validation_error(
        "BUY", 10, "MKT", None, None, True
    )
    stop_error = orders._validation_error(
        "SELL", 10, "STP", None, 12.5, True
    )
    assert market_error == "outside_rth is supported only for LMT orders"
    assert stop_error == "outside_rth is supported only for LMT orders"


def test_build_limit_order_sets_outside_rth():
    order = orders._build_order("BUY", 15, "LMT", 10.25, None, True)
    assert order.orderType == "LMT"
    assert order.action == "BUY"
    assert order.totalQuantity == 15
    assert order.lmtPrice == 10.25
    assert order.outsideRth is True


def test_build_stop_order_sets_trigger_and_regular_hours():
    order = orders._build_order("SELL", 20, "STP", None, 9.75, False)
    assert order.orderType == "STP"
    assert order.action == "SELL"
    assert order.totalQuantity == 20
    assert order.auxPrice == 9.75
    assert order.outsideRth is False


def test_build_market_order_is_regular_hours():
    order = orders._build_order("BUY", 5, "MKT", None, None, False)
    assert order.orderType == "MKT"
    assert order.outsideRth is False
