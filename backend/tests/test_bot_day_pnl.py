"""Whole-account Day P&L meter: realized + unrealized minus commissions."""
from __future__ import annotations

from bot.day_pnl import day_pnl_usd


def test_day_pnl_realized_plus_unrealized_minus_commissions():
    summary = {"RealizedPnL": -40.0, "UnrealizedPnL": -20.0}
    assert day_pnl_usd(summary, commission_total=5.0) == -65.0


def test_day_pnl_missing_one_leg():
    assert day_pnl_usd({"RealizedPnL": -12.0}, commission_total=0) == -12.0
    assert day_pnl_usd({"UnrealizedPnL": 3.0}, commission_total=1.0) == 2.0


def test_day_pnl_none_when_no_legs():
    assert day_pnl_usd({}, commission_total=2.0) is None
    assert day_pnl_usd(None) is None


def test_commissions_count_absolute():
    summary = {"RealizedPnL": 0.0, "UnrealizedPnL": 0.0}
    assert day_pnl_usd(summary, commission_total=-8.0) == -8.0
