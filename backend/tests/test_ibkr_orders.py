"""Pure validation and construction tests for manual IBKR orders."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import ibkr.client as client_mod
from ibkr import orders
from ibkr.errors import IbkrAccountError


def test_open_orders_raises_when_disconnected(monkeypatch):
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    with pytest.raises(IbkrAccountError, match="not connected"):
        orders.open_orders()


def test_open_orders_raises_on_error(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.openTrades.side_effect = RuntimeError("boom")
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    with pytest.raises(IbkrAccountError, match="boom"):
        orders.open_orders()


def test_closed_orders_raises_when_disconnected(monkeypatch):
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    with pytest.raises(IbkrAccountError, match="not connected"):
        orders.closed_orders()


def test_closed_orders_raises_on_error(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.trades.side_effect = RuntimeError("boom")
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    with pytest.raises(IbkrAccountError, match="boom"):
        orders.closed_orders()


def test_validation_requires_limit_price():
    error = orders._validation_error("BUY", 10, "LMT", None, None, False)
    assert error == "limit_price must be greater than zero for LMT"


def test_validation_requires_stop_price():
    error = orders._validation_error("SELL", 10, "STP", None, None, False)
    assert error == "stop_price must be greater than zero for STP"


def test_validation_allows_extended_hours_market_and_stop():
    assert orders._validation_error("BUY", 10, "MKT", None, None, True) is None
    assert orders._validation_error("SELL", 10, "STP", None, 12.5, True) is None


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


def test_build_stop_order_respects_outside_rth():
    order = orders._build_order("SELL", 20, "STP", None, 9.75, True)
    assert order.orderType == "STP"
    assert order.outsideRth is True


def test_normalize_accepts_stop_limit_and_trail_aliases():
    assert orders.normalize_order_type("stplmt") == "STP LMT"
    assert orders.normalize_order_type("stop-limit") == "STP LMT"
    assert orders.normalize_order_type("TRAILING STOP") == "TRAIL"
    assert orders.normalize_order_type("trail") == "TRAIL"


def test_validation_requires_both_prices_for_stop_limit():
    assert orders._validation_error("SELL", 10, "STP LMT", None, 12.5, False) == (
        "limit_price must be greater than zero for STP LMT"
    )
    assert orders._validation_error("SELL", 10, "STP LMT", 12.25, None, False) == (
        "stop_price must be greater than zero for STP LMT"
    )
    assert orders._validation_error("SELL", 10, "STP LMT", 12.25, 12.5, False) is None


def test_validation_requires_trail_dollar_amount():
    assert orders._validation_error("SELL", 10, "TRAIL", None, None, False) == (
        "stop_price must be greater than zero for TRAIL (trail $)"
    )
    assert orders._validation_error("SELL", 10, "TRAIL", None, 0.35, True) is None


def test_build_stop_limit_sets_lmt_and_aux():
    order = orders._build_order("SELL", 20, "STP LMT", 9.5, 9.75, True)
    assert order.orderType == "STP LMT"
    assert order.lmtPrice == 9.5
    assert order.auxPrice == 9.75
    assert order.outsideRth is True


def test_build_trail_uses_aux_price_as_trail_dollars():
    order = orders._build_order("SELL", 20, "TRAIL", None, 0.35, False)
    assert order.orderType == "TRAIL"
    assert order.auxPrice == 0.35
    assert order.outsideRth is False
    # Do not send trail % -- trailingPercent stays the IB unset sentinel.
    assert float(order.trailingPercent) > 1e100


def test_build_market_order_respects_outside_rth():
    rth = orders._build_order("BUY", 5, "MKT", None, None, False)
    assert rth.orderType == "MKT"
    assert rth.outsideRth is False
    eh = orders._build_order("SELL", 5, "MKT", None, None, True)
    assert eh.orderType == "MKT"
    assert eh.outsideRth is True
