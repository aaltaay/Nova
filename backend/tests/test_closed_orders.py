"""Unit tests for IBKR closed-orders filtering (no live Gateway)."""

from __future__ import annotations

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
