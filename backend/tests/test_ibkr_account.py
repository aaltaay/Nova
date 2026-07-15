"""Tests for ibkr/account.py — account summary and positions parsing.

No live IB Gateway required — ibkr.client.get_ib() is mocked to return a fake
IB object (or None to simulate disconnected state).
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import ibkr.account as account_mod
import ibkr.client as client_mod


class _FakePosition:
    def __init__(self, symbol, qty, avg_cost):
        self.contract = MagicMock(symbol=symbol)
        self.position = qty
        self.avgCost = avg_cost


class _FakePortfolioItem:
    def __init__(self, symbol, qty, market_price, market_value, avg_cost, u_pnl, r_pnl):
        self.contract = MagicMock(symbol=symbol)
        self.position = qty
        self.marketPrice = market_price
        self.marketValue = market_value
        self.averageCost = avg_cost
        self.unrealizedPNL = u_pnl
        self.realizedPNL = r_pnl


class _FakeSummaryItem:
    def __init__(self, tag, value, currency="USD"):
        self.tag = tag
        self.value = value
        self.currency = currency


def test_get_positions_returns_empty_when_disconnected(monkeypatch):
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    assert account_mod.get_positions() == []


def test_get_positions_parses_ib_positions(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.positions.return_value = [_FakePosition("AAPL", 10, 150.0)]
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    out = account_mod.get_positions()
    assert out == [{"symbol": "AAPL", "qty": 10, "avg_cost": 150.0, "market_value": None}]


def test_get_positions_returns_empty_on_error(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.positions.side_effect = RuntimeError("boom")
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    assert account_mod.get_positions() == []


def test_get_account_summary_disconnected(monkeypatch):
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    assert account_mod.get_account_summary() == {"connected": False, "mode": "disconnected"}


def test_get_account_summary_marks_pending_when_no_net_liquidation(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.accountValues.return_value = []
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    out = account_mod.get_account_summary()
    assert out["pending"] is True


def test_get_account_summary_error_reports_disconnected_with_reason(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.accountValues.side_effect = RuntimeError("no connection")
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    out = account_mod.get_account_summary()
    assert out["connected"] is False
    assert out["error"] == "no connection"


def test_refresh_account_summary_disconnected(monkeypatch):
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    out = asyncio.run(account_mod.refresh_account_summary())
    assert out == {"connected": False, "mode": "disconnected"}


def test_refresh_account_summary_uses_async_items(monkeypatch):
    fake_ib = MagicMock()

    async def _fake_summary():
        return [_FakeSummaryItem("NetLiquidation", "1000.00")]

    fake_ib.accountSummaryAsync = _fake_summary
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    out = asyncio.run(account_mod.refresh_account_summary())
    assert out["NetLiquidation"] == 1000.0
    assert out["connected"] is True


def test_refresh_account_summary_falls_back_to_cache_on_error(monkeypatch):
    fake_ib = MagicMock()

    async def _raise():
        raise RuntimeError("timeout")

    fake_ib.accountSummaryAsync = _raise
    fake_ib.accountValues.return_value = []
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    out = asyncio.run(account_mod.refresh_account_summary())
    assert out["error"] == "timeout"


def test_get_portfolio_returns_empty_when_disconnected(monkeypatch):
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    assert account_mod.get_portfolio() == []


def test_get_portfolio_parses_items(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.portfolio.return_value = [
        _FakePortfolioItem("TSLA", 5, 200.0, 1000.0, 190.0, 50.0, 0.0)
    ]
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    out = account_mod.get_portfolio()
    assert out == [{
        "symbol": "TSLA",
        "qty": 5,
        "market_price": 200.0,
        "market_value": 1000.0,
        "avg_cost": 190.0,
        "unrealized_pnl": 50.0,
        "realized_pnl": 0.0,
    }]


def test_get_portfolio_returns_empty_on_error(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.portfolio.side_effect = RuntimeError("boom")
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    assert account_mod.get_portfolio() == []
