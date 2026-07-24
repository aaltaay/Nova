"""Tests for ibkr/account.py — account summary and positions parsing.

No live IB Gateway required — ibkr.client.get_ib() is mocked to return a fake
IB object (or None to simulate disconnected state).
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

import ibkr.account as account_mod
import ibkr.client as client_mod
from ibkr.errors import IbkrAccountError
from metrics import op_metrics


@pytest.fixture(autouse=True)
def reset_op_metrics():
    op_metrics.reset_for_tests()
    yield
    op_metrics.reset_for_tests()


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


def test_get_positions_raises_when_disconnected(monkeypatch):
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    with pytest.raises(IbkrAccountError, match="not connected"):
        account_mod.get_positions()


def test_get_positions_parses_ib_positions(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.positions.return_value = [_FakePosition("AAPL", 10, 150.0)]
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    out = account_mod.get_positions()
    assert out == [{"symbol": "AAPL", "qty": 10, "avg_cost": 150.0, "market_value": None}]
    assert op_metrics.snapshot()["operations"]["ibkr.account.positions_read"]["count"] == 1


def test_get_positions_raises_on_error(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.positions.side_effect = RuntimeError("boom")
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    with pytest.raises(IbkrAccountError, match="boom"):
        account_mod.get_positions()
    assert op_metrics.snapshot()["operations"]["ibkr.account.positions_read"]["error_count"] == 1


def test_get_account_summary_disconnected(monkeypatch):
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    assert account_mod.get_account_summary() == {"connected": False, "mode": "disconnected"}


def test_get_account_summary_marks_pending_when_no_net_liquidation(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.accountValues.return_value = []
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    out = account_mod.get_account_summary()
    assert out["pending"] is True


def test_get_account_summary_raises_on_account_values_error(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.accountValues.side_effect = RuntimeError("no connection")
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    with pytest.raises(IbkrAccountError, match="no connection"):
        account_mod.get_account_summary()


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
    assert op_metrics.snapshot()["operations"]["ibkr.account.summary_refresh"]["count"] == 1


def test_refresh_account_summary_raises_on_async_error(monkeypatch):
    fake_ib = MagicMock()

    async def _raise():
        raise RuntimeError("timeout")

    fake_ib.accountSummaryAsync = _raise
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    with pytest.raises(IbkrAccountError, match="timeout"):
        asyncio.run(account_mod.refresh_account_summary())
    assert op_metrics.snapshot()["operations"]["ibkr.account.summary_refresh"]["error_count"] == 1


def test_long_qty_sums_longs_ignores_flat_and_short(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.positions.return_value = [
        _FakePosition("SPY", 1, 500.0),
        _FakePosition("SPY", 2, 501.0),
        _FakePosition("SPY", 0, 0.0),
        _FakePosition("SPY", -3, 502.0),
        _FakePosition("QQQ", 10, 400.0),
    ]
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    assert account_mod.long_qty("spy") == 3.0
    assert account_mod.long_qty("QQQ") == 10.0
    assert account_mod.long_qty("MISSING") == 0.0


def test_long_qty_raises_when_positions_unavailable(monkeypatch):
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    with pytest.raises(IbkrAccountError, match="not connected"):
        account_mod.long_qty("SPY")


def test_positions_for_ui_qty_from_positions_not_portfolio_only(monkeypatch):
    """Portfolio long + empty positions → API qty must not invent a long."""
    fake_ib = MagicMock()
    fake_ib.positions.return_value = []
    fake_ib.portfolio.return_value = [
        _FakePortfolioItem("SPY", 1, 500.0, 500.0, 490.0, 10.0, 0.0)
    ]
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    assert account_mod.positions_for_ui() == []
    assert account_mod.long_qty("SPY") == 0.0


def test_positions_for_ui_joins_mtm_from_portfolio(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.positions.return_value = [_FakePosition("SPY", 1, 490.0)]
    fake_ib.portfolio.return_value = [
        _FakePortfolioItem("SPY", 1, 500.0, 500.0, 490.0, 10.0, 0.0),
        # Portfolio-only row must not appear:
        _FakePortfolioItem("QQQ", 5, 400.0, 2000.0, 390.0, 50.0, 0.0),
    ]
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    out = account_mod.positions_for_ui()
    assert len(out) == 1
    assert out[0]["symbol"] == "SPY"
    assert out[0]["qty"] == 1.0
    assert out[0]["market_price"] == 500.0
    assert out[0]["unrealized_pnl"] == 10.0


def test_get_portfolio_raises_when_disconnected(monkeypatch):
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    with pytest.raises(IbkrAccountError, match="not connected"):
        account_mod.get_portfolio()


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
    assert op_metrics.snapshot()["operations"]["ibkr.account.portfolio_read"]["count"] == 1


def test_get_portfolio_raises_on_error(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.portfolio.side_effect = RuntimeError("boom")
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    with pytest.raises(IbkrAccountError, match="boom"):
        account_mod.get_portfolio()


def test_refresh_completed_orders_cache_noop_when_disconnected(monkeypatch):
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    # Must not raise — best-effort warm-up, same shape as refresh_positions_cache.
    asyncio.run(account_mod.refresh_completed_orders_cache())


def test_refresh_completed_orders_cache_calls_api_only_false(monkeypatch):
    account_mod._completed_orders_lock = None
    calls: list[bool] = []

    async def fake_req(api_only):
        calls.append(api_only)

    fake_ib = MagicMock()
    fake_ib.reqCompletedOrdersAsync = fake_req
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    asyncio.run(account_mod.refresh_completed_orders_cache())
    assert calls == [False]


def test_refresh_completed_orders_cache_times_out_without_raising(monkeypatch):
    """Read-Only / wedged Gateway must not hang reconnect or GET /orders/closed."""
    import time

    import constants_ibkr as cibkr

    account_mod._completed_orders_lock = None

    async def hang(_api_only):
        await asyncio.sleep(30)

    fake_ib = MagicMock()
    fake_ib.reqCompletedOrdersAsync = hang
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(cibkr, "IBKR_COMPLETED_ORDERS_TIMEOUT_SEC", 0.05)
    started = time.monotonic()
    asyncio.run(account_mod.refresh_completed_orders_cache())
    assert time.monotonic() - started < 2.0


def test_refresh_completed_orders_cache_logs_and_swallows_failure(monkeypatch):
    account_mod._completed_orders_lock = None

    async def fake_req(_api_only):
        raise RuntimeError("reqCompletedOrders timeout")

    fake_ib = MagicMock()
    fake_ib.reqCompletedOrdersAsync = fake_req
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    # Must not propagate — Closed Orders still fails closed on its own read.
    asyncio.run(account_mod.refresh_completed_orders_cache())


def test_refresh_positions_cache_uses_explicit_ib_without_get_ib(monkeypatch):
    """Connect-time warm-up passes ib directly — it must not depend on
    get_ib(), which is gated on the READY state this call itself earns."""
    calls: list[None] = []

    async def fake_req():
        calls.append(None)

    fake_ib = MagicMock()
    fake_ib.reqPositionsAsync = fake_req

    def _boom():
        raise AssertionError("must not call get_ib() when ib is passed explicitly")

    monkeypatch.setattr(client_mod, "get_ib", _boom)
    asyncio.run(account_mod.refresh_positions_cache(fake_ib))
    assert calls == [None]
    assert op_metrics.snapshot()["operations"]["ibkr.account.positions_refresh"]["count"] == 1


def test_refresh_completed_orders_cache_uses_explicit_ib_without_get_ib(monkeypatch):
    account_mod._completed_orders_lock = None
    calls: list[bool] = []

    async def fake_req(api_only):
        calls.append(api_only)

    fake_ib = MagicMock()
    fake_ib.reqCompletedOrdersAsync = fake_req

    def _boom():
        raise AssertionError("must not call get_ib() when ib is passed explicitly")

    monkeypatch.setattr(client_mod, "get_ib", _boom)
    asyncio.run(account_mod.refresh_completed_orders_cache(fake_ib))
    assert calls == [False]


def test_refresh_completed_orders_cache_serializes_concurrent_calls(monkeypatch):
    """ib_async can hang if reqCompletedOrdersAsync overlaps — the guard must
    never let two calls run inside the request at the same time."""
    account_mod._completed_orders_lock = None
    state = {"concurrent": 0, "max_concurrent": 0}

    async def fake_req(_api_only):
        state["concurrent"] += 1
        state["max_concurrent"] = max(state["max_concurrent"], state["concurrent"])
        await asyncio.sleep(0.02)
        state["concurrent"] -= 1

    fake_ib = MagicMock()
    fake_ib.reqCompletedOrdersAsync = fake_req
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)

    async def _run_both():
        await asyncio.gather(
            account_mod.refresh_completed_orders_cache(),
            account_mod.refresh_completed_orders_cache(),
        )

    asyncio.run(_run_both())
    assert state["max_concurrent"] == 1
