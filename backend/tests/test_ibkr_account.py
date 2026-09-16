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
    from ibkr.ib_scheduler import reset_for_testing as reset_cold_slot

    op_metrics.reset_for_tests()
    account_mod.reset_completed_orders_cooldown_for_testing()
    reset_cold_slot()
    yield
    op_metrics.reset_for_tests()
    account_mod.reset_completed_orders_cooldown_for_testing()
    reset_cold_slot()


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
    monkeypatch.setattr(client_mod, "is_connected", lambda: False)
    with pytest.raises(IbkrAccountError, match="transport down|not connected"):
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
    assert "AccountType" not in out


def test_get_account_summary_keeps_cash_account_type_as_string(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.accountValues.return_value = [
        _FakeSummaryItem("NetLiquidation", "1000.00"),
        _FakeSummaryItem("AccountType", "CASH"),
        _FakeSummaryItem("BuyingPower", "1000.00"),
    ]
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    out = account_mod.get_account_summary()
    assert out["AccountType"] == "CASH"
    assert out["NetLiquidation"] == 1000.0
    assert out["BuyingPower"] == 1000.0


def test_get_account_summary_keeps_margin_account_type_as_string(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.accountValues.return_value = [
        _FakeSummaryItem("NetLiquidation", "5000.00"),
        _FakeSummaryItem("AccountType", "MARGIN"),
    ]
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "live")
    out = account_mod.get_account_summary()
    assert out["AccountType"] == "MARGIN"


def test_get_account_summary_does_not_invent_account_type_from_buying_power(
    monkeypatch,
):
    fake_ib = MagicMock()
    fake_ib.accountValues.return_value = [
        _FakeSummaryItem("NetLiquidation", "1000.00"),
        _FakeSummaryItem("BuyingPower", "4000.00"),
    ]
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    out = account_mod.get_account_summary()
    assert "AccountType" not in out
    assert out["BuyingPower"] == 4000.0


def test_get_account_summary_blank_account_type_is_none(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.accountValues.return_value = [
        _FakeSummaryItem("NetLiquidation", "1000.00"),
        _FakeSummaryItem("AccountType", ""),
    ]
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    out = account_mod.get_account_summary()
    assert out["AccountType"] is None


def test_overlay_missing_tags_fills_only_empty_config_keys():
    from ibkr.account_summary import overlay_missing_tags

    out = overlay_missing_tags(
        {
            "connected": True,
            "mode": "live",
            "AccountType": "INDIVIDUAL",
            "BuyingPower": 376.0,
            "TradingType": None,
        },
        {
            "AccountType": "CASH",
            "TradingType": "STKNOPT",
            "WhatIfPMEnabled": "true",
            "BuyingPower": 99999.0,
        },
    )
    assert out["AccountType"] == "INDIVIDUAL"
    assert out["TradingType"] == "STKNOPT"
    assert out["WhatIfPMEnabled"] == "true"
    assert out["BuyingPower"] == 376.0


def test_refresh_account_summary_includes_account_type(monkeypatch):
    fake_ib = MagicMock()

    async def _fake_summary():
        return [
            _FakeSummaryItem("NetLiquidation", "1000.00"),
            _FakeSummaryItem("AccountType", "INDIVIDUAL"),
        ]

    fake_ib.accountSummaryAsync = _fake_summary
    fake_ib.accountValues.return_value = []
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    out = asyncio.run(account_mod.refresh_account_summary())
    assert out["AccountType"] == "INDIVIDUAL"
    assert out["NetLiquidation"] == 1000.0


def test_refresh_account_summary_overlays_trading_type_from_account_values(
    monkeypatch,
):
    """reqAccountSummary does not request TradingType-S -- fill from accountValues."""
    fake_ib = MagicMock()

    async def _fake_summary():
        return [
            _FakeSummaryItem("NetLiquidation", "540.00"),
            _FakeSummaryItem("AccountType", "INDIVIDUAL"),
            _FakeSummaryItem("BuyingPower", "376.00"),
            _FakeSummaryItem("TotalCashValue", "383.00"),
        ]

    fake_ib.accountSummaryAsync = _fake_summary
    fake_ib.accountValues.return_value = [
        _FakeSummaryItem("TradingType-S", "STKNOPT"),
        _FakeSummaryItem("WhatIfPMEnabled", "true"),
        _FakeSummaryItem("Leverage-S", "0.29"),
        _FakeSummaryItem("BuyingPower", "99999.00"),
    ]
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "live")
    out = asyncio.run(account_mod.refresh_account_summary())
    assert out["AccountType"] == "INDIVIDUAL"
    assert out["TradingType"] == "STKNOPT"
    assert out["WhatIfPMEnabled"] == "true"
    assert out["Leverage"] == 0.29
    assert out["BuyingPower"] == 376.0
    assert out["NetLiquidation"] == 540.0


def test_get_account_summary_ahmed_individual_does_not_invent_margin(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.accountValues.return_value = [
        _FakeSummaryItem("AccountType", "INDIVIDUAL"),
        _FakeSummaryItem("NetLiquidation", "540.00"),
        _FakeSummaryItem("BuyingPower", "376.00"),
        _FakeSummaryItem("TotalCashValue", "383.00"),
        _FakeSummaryItem("TradingType-S", "STKNOPT"),
    ]
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "live")
    out = account_mod.get_account_summary()
    assert out["AccountType"] == "INDIVIDUAL"
    assert out["TradingType"] == "STKNOPT"
    assert out["BuyingPower"] == 376.0
    assert out.get("margin_kind") is None


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
    fake_ib.accountValues.return_value = []
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
    monkeypatch.setattr(client_mod, "is_connected", lambda: False)
    with pytest.raises(IbkrAccountError, match="transport down|not connected"):
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


def test_positions_for_ui_prefers_live_l1_last_over_portfolio(monkeypatch):
    fake_ib = MagicMock()
    fake_ib.positions.return_value = [_FakePosition("SPCX", 100, 10.0)]
    fake_ib.portfolio.return_value = [
        _FakePortfolioItem("SPCX", 100, 10.50, 1050.0, 10.0, 50.0, 0.0),
    ]
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(
        account_mod,
        "live_l1_last",
        lambda symbol: 10.87 if symbol == "SPCX" else None,
    )
    out = account_mod.positions_for_ui()
    assert len(out) == 1
    assert out[0]["market_price"] == 10.87
    assert out[0]["market_value"] == pytest.approx(1087.0)
    assert out[0]["unrealized_pnl"] == pytest.approx(87.0)


def test_account_summary_for_ui_reads_cache_and_overlays_l1(monkeypatch):
    monkeypatch.setattr(
        account_mod,
        "get_account_summary",
        lambda: {
            "connected": True,
            "mode": "live",
            "NetLiquidation": 10_000.0,
            "BuyingPower": 4_000.0,
            "UnrealizedPnL": 50.0,
            "RealizedPnL": 12.0,
        },
    )
    monkeypatch.setattr(
        account_mod,
        "positions_for_ui",
        lambda: [{
            "symbol": "SPCX",
            "qty": 100.0,
            "avg_cost": 10.0,
            "market_price": 10.87,
            "market_value": 1087.0,
            "unrealized_pnl": 87.0,
            "realized_pnl": 0.0,
        }],
    )
    out = account_mod.account_summary_for_ui()
    assert out["UnrealizedPnL"] == pytest.approx(87.0)
    assert out["NetLiquidation"] == pytest.approx(10_037.0)
    assert out["BuyingPower"] == 4_000.0


def test_ibkr_account_poll_sec_is_one_second_or_faster():
    from constants_ibkr import IBKR_ACCOUNT_POLL_SEC

    assert IBKR_ACCOUNT_POLL_SEC <= 1


def test_get_portfolio_raises_when_disconnected(monkeypatch):
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    monkeypatch.setattr(client_mod, "is_connected", lambda: False)
    with pytest.raises(IbkrAccountError, match="transport down|not connected"):
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
    account_mod.reset_completed_orders_cooldown_for_testing()
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

    account_mod.reset_completed_orders_cooldown_for_testing()

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
    account_mod.reset_completed_orders_cooldown_for_testing()

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
    account_mod.reset_completed_orders_cooldown_for_testing()
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
    account_mod.reset_completed_orders_cooldown_for_testing()
    state = {"concurrent": 0, "max_concurrent": 0, "calls": 0}

    async def fake_req(_api_only):
        state["calls"] += 1
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
    # Second waiter hits cooldown after the first success -- only one IBKR call.
    assert state["calls"] == 1


def test_refresh_completed_orders_cache_cooldown_skips_repeat(monkeypatch):
    """Empty Closed Orders polls must not re-warm IBKR every 5s."""
    import constants_ibkr as cibkr

    account_mod.reset_completed_orders_cooldown_for_testing()
    monkeypatch.setattr(cibkr, "IBKR_COMPLETED_ORDERS_MIN_INTERVAL_SEC", 60.0)
    calls: list[bool] = []

    async def fake_req(api_only):
        calls.append(api_only)

    fake_ib = MagicMock()
    fake_ib.reqCompletedOrdersAsync = fake_req
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)

    asyncio.run(account_mod.refresh_completed_orders_cache())
    asyncio.run(account_mod.refresh_completed_orders_cache())
    assert calls == [False]

    # Connect warm-up bypasses cooldown.
    asyncio.run(account_mod.refresh_completed_orders_cache(force=True))
    assert calls == [False, False]
