"""Unit tests for IBKR closed-orders filtering (no live Gateway)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import ibkr.orders as orders_mod
from ibkr.errors import IbkrAccountError


def _trade(order_id: int, symbol: str, status: str, filled: float = 0.0):
    return SimpleNamespace(
        order=SimpleNamespace(
            orderId=order_id,
            action="BUY",
            totalQuantity=100,
            orderType="LMT",
            lmtPrice=10.0,
            auxPrice=None,
            outsideRth=False,
        ),
        contract=SimpleNamespace(symbol=symbol),
        orderStatus=SimpleNamespace(
            status=status,
            filled=filled,
            remaining=max(0.0, 100.0 - filled),
            avgFillPrice=10.0 if filled else 0.0,
        ),
    )


def test_closed_orders_filters_terminal_statuses(monkeypatch):
    trades = [
        _trade(1, "AAA", "Submitted", filled=10),
        _trade(2, "BBB", "Filled", filled=100),
        _trade(3, "CCC", "Cancelled", filled=0),
        _trade(4, "DDD", "ApiCancelled", filled=25),
        _trade(5, "EEE", "Inactive", filled=0),
        _trade(6, "FFF", "PreSubmitted", filled=0),
    ]
    monkeypatch.setattr(orders_mod._client, "get_ib", lambda: SimpleNamespace(trades=lambda: trades))

    rows = orders_mod.closed_orders(limit=50)
    symbols = [r["symbol"] for r in rows]
    assert symbols == ["EEE", "DDD", "CCC", "BBB"]  # newest order_id first
    assert all(r["status"] in ("Filled", "Cancelled", "ApiCancelled", "Inactive") for r in rows)


def test_closed_orders_respects_limit(monkeypatch):
    trades = [_trade(i, f"S{i}", "Filled", filled=100) for i in range(1, 6)]
    monkeypatch.setattr(orders_mod._client, "get_ib", lambda: SimpleNamespace(trades=lambda: trades))
    rows = orders_mod.closed_orders(limit=2)
    assert len(rows) == 2
    assert rows[0]["order_id"] == 5


def test_closed_orders_raises_when_disconnected(monkeypatch):
    """A disconnected read must not look like "no closed orders" — see
    ibkr/errors.IbkrAccountError docstring."""
    monkeypatch.setattr(orders_mod._client, "get_ib", lambda: None)
    with pytest.raises(IbkrAccountError, match="not connected"):
        orders_mod.closed_orders()


def test_closed_orders_infers_filled_qty_for_warm_completed_order():
    """A Trade sourced from reqCompletedOrdersAsync (order never seen live by
    this API session) carries status="Filled" but IBKR does not backfill
    orderStatus.filled/remaining for it — must not show "Filled" + "0 filled"."""
    trade = _trade(1, "AAA", "Filled", filled=0)
    row = orders_mod._trade_to_order_row(trade)
    assert row["status"] == "Filled"
    assert row["filled_qty"] == 100.0
    assert row["remaining_qty"] == 0.0


def test_closed_orders_keeps_real_partial_fill_qty():
    """A genuinely tracked partial fill must not be overwritten by the
    Filled-with-zero inference (status is not "Filled" here)."""
    trade = _trade(1, "AAA", "ApiCancelled", filled=25)
    row = orders_mod._trade_to_order_row(trade)
    assert row["filled_qty"] == 25.0
    assert row["remaining_qty"] == 75.0


def test_closed_orders_async_returns_directly_when_non_empty(monkeypatch):
    trades = [_trade(1, "AAA", "Filled", filled=100)]
    monkeypatch.setattr(orders_mod._client, "get_ib", lambda: SimpleNamespace(trades=lambda: trades))
    calls = {"refresh": 0}

    async def fake_refresh():
        calls["refresh"] += 1

    import ibkr.account as account_mod
    monkeypatch.setattr(account_mod, "refresh_completed_orders_cache", fake_refresh)

    rows = asyncio.run(orders_mod.closed_orders_async())
    assert len(rows) == 1
    assert calls["refresh"] == 0


def test_closed_orders_async_warms_once_when_empty_then_populated(monkeypatch):
    """Empty on first read (e.g. UI mounted just before the connect-time warm
    finished) → one single-flighted refresh, then a real re-read."""
    state = {"trades": []}
    monkeypatch.setattr(
        orders_mod._client, "get_ib", lambda: SimpleNamespace(trades=lambda: state["trades"]),
    )
    calls = {"refresh": 0}

    async def fake_refresh():
        calls["refresh"] += 1
        state["trades"] = [_trade(1, "AAA", "Filled", filled=100)]

    import ibkr.account as account_mod
    monkeypatch.setattr(account_mod, "refresh_completed_orders_cache", fake_refresh)

    rows = asyncio.run(orders_mod.closed_orders_async())
    assert calls["refresh"] == 1
    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAA"


def test_closed_orders_async_raises_when_disconnected_without_warming(monkeypatch):
    monkeypatch.setattr(orders_mod._client, "get_ib", lambda: None)
    with pytest.raises(IbkrAccountError, match="not connected"):
        asyncio.run(orders_mod.closed_orders_async())
