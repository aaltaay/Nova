"""
IBKR order placement and cancellation.

SAFETY: all spending goes through ibkr.safety.assert_orders_allowed() — the
single source of truth. See that module for the env gate list.
"""
from __future__ import annotations

import logging
from typing import Literal

from ibkr import client as _client
from ibkr import safety as _safety

logger = logging.getLogger(__name__)

OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MKT", "LMT"]


def _safety_check() -> tuple[bool, str]:
    return _safety.assert_orders_allowed(
        client_enabled=_client.is_enabled(),
        connected=_client.is_connected(),
        account_mode=_client.account_mode(),
    )


def place_order(
    symbol: str,
    side: OrderSide,
    qty: float,
    order_type: OrderType = "MKT",
    limit_price: float | None = None,
) -> dict:
    """
    Place a market or limit order.
    Returns {"ok": bool, "order_id": int|None, "error": str|None, "mode": str}.
    """
    ok, reason = _safety_check()
    if not ok:
        logger.warning("IBKR order blocked: %s", reason)
        return {"ok": False, "order_id": None, "error": reason, "mode": _client.account_mode()}

    ib = _client.get_ib()
    if ib is None:
        return {"ok": False, "order_id": None, "error": "Not connected", "mode": "disconnected"}

    try:
        from ib_async import Stock, MarketOrder, LimitOrder
        contract = Stock(symbol, "SMART", "USD")

        if order_type == "MKT":
            order = MarketOrder(side, qty)
        else:
            if limit_price is None:
                return {"ok": False, "order_id": None, "error": "limit_price required for LMT", "mode": _client.account_mode()}
            order = LimitOrder(side, qty, limit_price)

        trade = ib.placeOrder(contract, order)
        oid = trade.order.orderId
        logger.info("IBKR: placed %s %s %s %s @ %s (id=%s)", _client.account_mode(), order_type, side, qty, limit_price, oid)
        return {"ok": True, "order_id": oid, "error": None, "mode": _client.account_mode()}

    except Exception as exc:
        logger.exception("IBKR: order error for %s: %s", symbol, exc)
        return {"ok": False, "order_id": None, "error": str(exc), "mode": _client.account_mode()}


def place_bracket_order(
    symbol: str,
    side: OrderSide,
    qty: int,
    entry_price: float,
    stop_price: float,
    target_price: float,
) -> dict:
    """
    Place a bracket order: a LMT entry with a linked LMT profit target and a
    linked STP loss. Uses ib_async's native IB.bracketOrder() helper.
    """
    ok, reason = _safety_check()
    if not ok:
        logger.warning("IBKR bracket order blocked: %s", reason)
        return {
            "ok": False, "parent_order_id": None, "target_order_id": None,
            "stop_order_id": None, "error": reason, "mode": _client.account_mode(),
        }

    ib = _client.get_ib()
    if ib is None:
        return {
            "ok": False, "parent_order_id": None, "target_order_id": None,
            "stop_order_id": None, "error": "Not connected", "mode": "disconnected",
        }

    try:
        from ib_async import Stock
        contract = Stock(symbol, "SMART", "USD")
        bracket = ib.bracketOrder(side, qty, entry_price, target_price, stop_price)
        for order in bracket:
            ib.placeOrder(contract, order)
        logger.info(
            "IBKR: placed %s bracket %s %s qty=%s entry=%s target=%s stop=%s (parent=%s)",
            _client.account_mode(), side, symbol, qty, entry_price, target_price, stop_price,
            bracket.parent.orderId,
        )
        return {
            "ok": True,
            "parent_order_id": bracket.parent.orderId,
            "target_order_id": bracket.takeProfit.orderId,
            "stop_order_id": bracket.stopLoss.orderId,
            "error": None,
            "mode": _client.account_mode(),
        }
    except Exception as exc:
        logger.exception("IBKR: bracket order error for %s: %s", symbol, exc)
        return {
            "ok": False, "parent_order_id": None, "target_order_id": None,
            "stop_order_id": None, "error": str(exc), "mode": _client.account_mode(),
        }


def cancel_order(order_id: int) -> dict:
    """
    Cancel an open order by ID.
    Allowed whenever connected (does not require IBKR_ORDERS_ENABLED).
    """
    ok, reason = _safety.assert_cancel_allowed(
        client_enabled=_client.is_enabled(),
        connected=_client.is_connected(),
    )
    if not ok:
        return {"ok": False, "error": reason}

    ib = _client.get_ib()
    if ib is None:
        return {"ok": False, "error": "Not connected"}

    try:
        from ib_async import Order
        order = Order()
        order.orderId = order_id
        ib.cancelOrder(order)
        logger.info("IBKR: cancel requested for order %s", order_id)
        return {"ok": True, "error": None}
    except Exception as exc:
        logger.exception("IBKR: cancel error for order %s: %s", order_id, exc)
        return {"ok": False, "error": str(exc)}


def open_orders() -> list[dict]:
    """Return list of open orders as plain dicts."""
    ib = _client.get_ib()
    if ib is None:
        return []
    try:
        trades = ib.openTrades()
        return [
            {
                "order_id": t.order.orderId,
                "symbol": t.contract.symbol,
                "side": t.order.action,
                "qty": t.order.totalQuantity,
                "order_type": t.order.orderType,
                "limit_price": getattr(t.order, "lmtPrice", None),
                "status": t.orderStatus.status,
            }
            for t in trades
        ]
    except Exception as exc:
        logger.exception("IBKR: open_orders error: %s", exc)
        return []
