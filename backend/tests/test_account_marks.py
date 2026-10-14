"""L1 mark preference + account-cluster overlay (issue #182)."""
from __future__ import annotations

import pytest

from ibkr.account_marks import (
    apply_l1_position_mark,
    apply_l1_marks,
    overlay_account_summary,
    unrealized_at_bid,
)
from ibkr import account_marks


def _row(**overrides):
    base = {
        "symbol": "SPCX",
        "qty": 100.0,
        "avg_cost": 10.0,
        "market_price": 10.50,
        "market_value": 1050.0,
        "unrealized_pnl": 50.0,
        "realized_pnl": 0.0,
    }
    base.update(overrides)
    return base


def test_apply_l1_position_mark_prefers_live_last():
    marked = apply_l1_position_mark(_row(), 10.87)
    assert marked["market_price"] == 10.87
    assert marked["market_value"] == pytest.approx(1087.0)
    assert marked["unrealized_pnl"] == pytest.approx(87.0)
    assert marked["avg_cost"] == 10.0
    assert marked["qty"] == 100.0


def test_apply_l1_position_mark_keeps_portfolio_when_no_l1():
    row = _row()
    assert apply_l1_position_mark(row, None) == row
    assert apply_l1_position_mark(row, 0.0) == row
    assert apply_l1_position_mark(row, float("nan")) == row
    assert apply_l1_position_mark(row, -1.5) == row


def test_apply_l1_position_mark_short_qty():
    marked = apply_l1_position_mark(
        _row(qty=-50.0, avg_cost=20.0, market_price=19.0, market_value=-950.0, unrealized_pnl=50.0),
        18.5,
    )
    assert marked["market_price"] == 18.5
    assert marked["market_value"] == pytest.approx(-925.0)
    assert marked["unrealized_pnl"] == pytest.approx(75.0)


def test_apply_l1_marks_only_overlays_symbols_with_l1():
    rows = [_row(symbol="SPCX"), _row(symbol="AAPL", qty=1.0, avg_cost=100.0, market_price=101.0, market_value=101.0, unrealized_pnl=1.0)]

    def last_for(symbol):
        return 10.87 if symbol == "SPCX" else None

    out = apply_l1_marks(rows, last_for)
    assert out[0]["market_price"] == 10.87
    assert out[1]["market_price"] == 101.0


def test_overlay_account_summary_uses_l1_unrealized_and_adjusts_net_liq():
    summary = {
        "connected": True,
        "mode": "live",
        "NetLiquidation": 10_000.0,
        "BuyingPower": 4_000.0,
        "UnrealizedPnL": 50.0,
        "RealizedPnL": 12.0,
        "GrossPositionValue": 1050.0,
        "AccountType": "MARGIN",
        "account_class": "margin",
    }
    positions = [apply_l1_position_mark(_row(), 10.87)]
    out = overlay_account_summary(summary, positions)
    assert out["UnrealizedPnL"] == pytest.approx(87.0)
    assert out["NetLiquidation"] == pytest.approx(10_037.0)
    assert out["BuyingPower"] == 4_000.0
    assert out["RealizedPnL"] == 12.0
    assert out["GrossPositionValue"] == 1050.0
    assert out["AccountType"] == "MARGIN"
    assert out["account_class"] == "margin"


def test_overlay_account_summary_skips_when_no_marked_unrealized():
    summary = {"connected": True, "UnrealizedPnL": 3.0, "NetLiquidation": 100.0}
    out = overlay_account_summary(summary, [_row(unrealized_pnl=None, market_price=None)])
    assert out["UnrealizedPnL"] == 3.0
    assert out["NetLiquidation"] == 100.0


def test_unrealized_at_bid_marks_a_long_at_the_bid_and_a_short_at_the_ask():
    quotes = {"SPCX": (10.40, 10.45), "SHRT": (5.00, 5.10)}
    rows = [_row(), _row(symbol="SHRT", qty=-50.0, avg_cost=5.50)]
    assert unrealized_at_bid(rows, quotes.__getitem__) == pytest.approx((10.40 - 10.0) * 100 + (5.10 - 5.50) * -50)


def test_unrealized_at_bid_is_unknown_when_any_position_lacks_its_closing_side():
    rows = [_row(), _row(symbol="SHRT", qty=-50.0, avg_cost=5.50)]
    quotes = {"SPCX": (10.40, 10.45), "SHRT": (5.00, None)}
    assert unrealized_at_bid(rows, quotes.__getitem__) is None
    assert unrealized_at_bid([_row(avg_cost=None)], lambda s: (10.4, 10.45)) is None


def test_unrealized_at_bid_with_nothing_held_is_zero():
    assert unrealized_at_bid([], lambda s: (None, None)) == 0.0


def test_marked_account_summary_adds_unrealized_at_bid_only_when_connected(monkeypatch):
    monkeypatch.setattr(account_marks, "live_l1_bid_ask", lambda sym: (10.25, 10.30))
    summary = {"connected": True, "UnrealizedPnL": 50.0, "NetLiquidation": 1000.0}
    assert account_marks.marked_account_summary(summary, [_row()])["UnrealizedAtBid"] == pytest.approx(25.0)
    offline = {"connected": False}
    assert "UnrealizedAtBid" not in account_marks.marked_account_summary(offline, [_row()])
