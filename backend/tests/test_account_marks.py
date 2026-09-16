"""L1 mark preference + account-cluster overlay (issue #182)."""
from __future__ import annotations

import pytest

from ibkr.account_marks import (
    apply_l1_position_mark,
    apply_l1_marks,
    overlay_account_summary,
)


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
    }
    positions = [apply_l1_position_mark(_row(), 10.87)]
    out = overlay_account_summary(summary, positions)
    assert out["UnrealizedPnL"] == pytest.approx(87.0)
    assert out["NetLiquidation"] == pytest.approx(10_037.0)
    assert out["BuyingPower"] == 4_000.0
    assert out["RealizedPnL"] == 12.0
    assert out["GrossPositionValue"] == 1050.0
    assert out["AccountType"] == "MARGIN"


def test_overlay_account_summary_skips_when_no_marked_unrealized():
    summary = {"connected": True, "UnrealizedPnL": 3.0, "NetLiquidation": 100.0}
    out = overlay_account_summary(summary, [_row(unrealized_pnl=None, market_price=None)])
    assert out["UnrealizedPnL"] == 3.0
    assert out["NetLiquidation"] == 100.0
