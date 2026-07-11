"""
IBKR order placement and cancellation.

SAFETY GATES (both must pass before any order reaches the wire):
  1. IBKR_ENABLED=true in env
  2. IBKR_LIVE_TRADING_CONFIRMED=true OR we are on the paper port

Never placed from any other module. Never called by the Alpaca scan pipeline.
"""
from __future__ import annotations

import logging
import os
from typing import Literal

from ibkr import client as _client

logger = logging.getLogger(__name__)

OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MKT", "LMT"]


def _safety_check() -> tuple[bool, str]:
    """Returns (ok, reason). Both flags must be set for live orders."""
    if not _client.is_enabled():
        return False, "IBKR_ENABLED is not set"
    if not _client.is_connected():
        return False, "IBKR not connected"
    mode = _client.account_mode()
    if mode == "live":
        live_ok = os.environ.get("IBKR_LIVE_TRADING_CONFIRMED", "false").lower() in ("1", "true", "yes")
        if not live_ok:
            return False, "Live trading requires IBKR_LIVE_TRADING_CONFIRMED=true"
    return True, ""


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
        logger.error("IBKR: order error for %s: %s", symbol, exc)
        return {"ok": False, "order_id": None, "error": str(exc), "mode": _client.account_mode()}


def cancel_order(order_id: int) -> dict:
    """
    Cancel an open order by ID.
    Returns {"ok": bool, "error": str|None}.
    """
    ok, reason = _safety_check()
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
        logger.error("IBKR: cancel error for order %s: %s", order_id, exc)
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
        logger.error("IBKR: open_orders error: %s", exc)
        return []
