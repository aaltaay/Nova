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
from ibkr.errors import IbkrAccountError, describe_exc
from ibkr.order_rows import trade_to_order_row as _trade_to_order_row

logger = logging.getLogger(__name__)

OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MKT", "LMT", "STP"]


def _safety_check() -> tuple[bool, str]:
    return _safety.assert_orders_allowed(
        client_enabled=_client.is_enabled(),
        connected=_client.is_connected(),
        account_mode=_client.account_mode(),
        broker_account_kind=_client.broker_account_kind(),
    )


def _validation_error(
    side: str,
    qty: float,
    order_type: str,
    limit_price: float | None,
    stop_price: float | None,
    outside_rth: bool,
) -> str | None:
    if side not in ("BUY", "SELL"):
        return "side must be BUY or SELL"
    if qty <= 0:
        return "qty must be greater than zero"
    if order_type not in ("MKT", "LMT", "STP"):
        return "order_type must be MKT, LMT, or STP"
    if order_type == "LMT" and (limit_price is None or limit_price <= 0):
        return "limit_price must be greater than zero for LMT"
    if order_type == "STP" and (stop_price is None or stop_price <= 0):
        return "stop_price must be greater than zero for STP"
    # MKT + LMT may trade extended; STP triggers stay RTH-only in Nova.
    if outside_rth and order_type == "STP":
        return "outside_rth is not supported for STP orders"
    return None


def _build_order(
    side: OrderSide,
    qty: float,
    order_type: OrderType,
    limit_price: float | None,
    stop_price: float | None,
    outside_rth: bool,
):
    from ib_async import LimitOrder, MarketOrder, StopOrder

    if order_type == "MKT":
        return MarketOrder(side, qty, outsideRth=bool(outside_rth))
    if order_type == "LMT":
        return LimitOrder(side, qty, limit_price, outsideRth=outside_rth)
    return StopOrder(side, qty, stop_price, outsideRth=False)


def place_order(
    symbol: str,
    side: OrderSide,
    qty: float,
    order_type: OrderType = "MKT",
    limit_price: float | None = None,
    stop_price: float | None = None,
    outside_rth: bool = False,
    order_id: int | None = None,
) -> dict:
    """
    Place a market, limit, or stop order (or price-modify when order_id set).

    Returns {"ok": bool, "order_id": int|None, "error": str|None, "mode": str}.
    Adapter only — callers must enter via execution.service.execute (ADR 007).
    """
    error = _validation_error(
        side,
        qty,
        order_type,
        limit_price,
        stop_price,
        outside_rth,
    )
    if error:
        return {
            "ok": False,
            "order_id": None,
            "error": error,
            "mode": _client.account_mode(),
        }

    ok, reason = _safety_check()
    if not ok:
        logger.warning("IBKR order blocked: %s", reason)
        return {"ok": False, "order_id": None, "error": reason, "mode": _client.account_mode()}

    ib = _client.get_ib()
    if ib is None:
        return {"ok": False, "order_id": None, "error": "Not connected", "mode": "disconnected"}

    try:
        from ib_async import Stock
        contract = Stock(symbol, "SMART", "USD")
        order = _build_order(
            side,
            qty,
            order_type,
            limit_price,
            stop_price,
            outside_rth,
        )
        if order_id is not None:
            order.orderId = int(order_id)

        trade = ib.placeOrder(contract, order)
        oid = trade.order.orderId
        from ibkr.order_times import (
            audit_log_placed,
            extract_trade_times,
            remember_nova_placed,
            resolve_submitted_at,
        )

        nova_placed = remember_nova_placed(oid)
        broker_submitted, _, _ = extract_trade_times(trade)
        submitted_at = resolve_submitted_at(broker_submitted, oid)
        price = limit_price if order_type == "LMT" else stop_price
        action = "modified" if order_id is not None else "placed"
        logger.info(
            "IBKR: %s %s %s %s %s @ %s outside_rth=%s (id=%s)",
            action,
            _client.account_mode(),
            order_type,
            side,
            qty,
            price,
            outside_rth,
            oid,
        )
        if order_id is None:
            audit_log_placed(
                order_id=oid,
                symbol=symbol,
                side=side,
                qty=qty,
                order_type=order_type,
                mode=_client.account_mode(),
                nova_placed_at=nova_placed,
                broker_submitted_at=broker_submitted,
            )
        return {
            "ok": True,
            "order_id": oid,
            "error": None,
            "mode": _client.account_mode(),
            "submitted_at": submitted_at,
        }

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
        from ibkr.order_times import remember_nova_placed, wall_utc_now_iso

        bracket = ib.bracketOrder(side, qty, entry_price, target_price, stop_price)
        nova_stamp = wall_utc_now_iso()
        for order in bracket:
            ib.placeOrder(contract, order)
            remember_nova_placed(order.orderId, nova_stamp)
        logger.info(
            "IBKR: placed %s bracket %s %s qty=%s entry=%s target=%s stop=%s "
            "(parent=%s nova_placed_at_utc=%s)",
            _client.account_mode(), side, symbol, qty, entry_price, target_price, stop_price,
            bracket.parent.orderId,
            nova_stamp,
        )
        return {
            "ok": True,
            "parent_order_id": bracket.parent.orderId,
            "target_order_id": bracket.takeProfit.orderId,
            "stop_order_id": bracket.stopLoss.orderId,
            "error": None,
            "mode": _client.account_mode(),
            "submitted_at": nova_stamp,
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
    """Return list of open / working orders as plain dicts.

    Includes fill progress fields from IBKR ``orderStatus`` so the Working
    Orders panel can mirror Webull-style qty/filled/avg columns without a
    separate history API.

    Raises ``IbkrAccountError`` on disconnect / API failure — a failed read
    must never look like "no working orders" (cancel-all and the kill-switch
    reconciliation both depend on knowing the difference).
    """
    ib = _client.get_ib()
    if ib is None:
        raise IbkrAccountError("IBKR not connected — cannot read open orders")
    try:
        trades = ib.openTrades()
        return [_trade_to_order_row(t) for t in trades]
    except Exception as exc:
        detail = describe_exc(exc)
        logger.exception("IBKR: open_orders error: %s", detail)
        raise IbkrAccountError(f"open_orders failed: {detail}") from exc


def closed_orders(limit: int | None = None) -> list[dict]:
    """Return filled / cancelled / failed session orders (Closed Orders WID-027).

    Uses IBKR ``trades()`` filtered to terminal statuses — not a second broker
    path. Does not include still-working open trades. CSV / multi-day History
    export remains WID-020.

    ``ib.trades()`` includes both live-session orders and anything folded in
    by ``account.refresh_completed_orders_cache`` — ib_async merges those
    callbacks into the same trades map, so no separate dedupe is needed here.

    Raises ``IbkrAccountError`` on disconnect / API failure — never disguise
    as an empty session history.
    """
    from constants_ibkr import (
        IBKR_CLOSED_ORDER_STATUSES,
        IBKR_CLOSED_ORDERS_LIMIT_DEFAULT,
    )

    cap = IBKR_CLOSED_ORDERS_LIMIT_DEFAULT if limit is None else max(1, int(limit))
    ib = _client.get_ib()
    if ib is None:
        raise IbkrAccountError("IBKR not connected — cannot read closed orders")
    try:
        trades = list(ib.trades())
        rows: list[dict] = []
        for trade in trades:
            status = getattr(getattr(trade, "orderStatus", None), "status", "") or ""
            if status not in IBKR_CLOSED_ORDER_STATUSES:
                continue
            rows.append(_trade_to_order_row(trade))
        # Newest first when order ids grow monotonically (typical for a session).
        rows.sort(key=lambda r: int(r.get("order_id") or 0), reverse=True)
        return rows[:cap]
    except Exception as exc:
        detail = describe_exc(exc)
        logger.exception("IBKR: closed_orders error: %s", detail)
        raise IbkrAccountError(f"closed_orders failed: {detail}") from exc


async def closed_orders_async(limit: int | None = None) -> list[dict]:
    """``closed_orders`` with a one-shot completed-orders warm-up on empty.

    Covers a UI reading ``GET /api/ibkr/orders/closed`` before (or racing)
    the post-connect ``refresh_completed_orders_cache`` warm finishes. Only
    warms when the first read is empty *and* still connected; still raises
    ``IbkrAccountError`` like ``closed_orders`` when disconnected.
    """
    rows = closed_orders(limit=limit)
    if rows or _client.get_ib() is None:
        return rows
    from ibkr import account as _account

    await _account.refresh_completed_orders_cache()
    return closed_orders(limit=limit)
