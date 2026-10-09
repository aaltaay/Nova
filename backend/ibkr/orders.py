"""
IBKR order placement and cancellation.

SAFETY: all spending goes through ibkr.safety.assert_orders_allowed() — the
single source of truth. See that module for the env gate list.
"""
from __future__ import annotations

import logging
from ibkr import client as _client
from ibkr import safety as _safety
from ibkr.errors import IbkrAccountError, describe_exc
from ibkr.order_build import (
    OrderSide,
    OrderType,
    build_ib_order as _build_order,
    normalize_order_type,
    normalize_tif,
    validation_error as _validation_error,
)
from ibkr.order_rows import trade_to_order_row as _trade_to_order_row
from ibkr.order_bracket import place_bracket_order  # its own module: a broken bracket is taken back
from sim.account_hooks import practice_broker as _practice_broker, practice_refusal as _practice_refusal

logger = logging.getLogger(__name__)

__all__ = (
    "OrderSide",
    "OrderType",
    "cancel_order",
    "closed_orders",
    "closed_orders_async",
    "normalize_order_type",
    "open_orders",
    "place_bracket_order",
    "place_order",
)


def _ib_sync(fn, label: str, timeout: float = 15.0):
    from ibkr.loop_supervisor import call_on_ib, is_ib_loop, is_ib_thread

    if is_ib_loop() or is_ib_thread():
        return fn()
    return call_on_ib(fn, timeout, label=label)


def _safety_check() -> tuple[bool, str]:
    return _safety.assert_orders_allowed(
        client_enabled=_client.is_enabled(),
        connected=_client.is_connected(),
        account_mode=_client.account_mode(),
        broker_account_kind=_client.broker_account_kind(),
    )


def place_order(
    symbol: str,
    side: OrderSide,
    qty: float,
    order_type: OrderType = "MKT",
    limit_price: float | None = None,
    stop_price: float | None = None,
    outside_rth: bool = False,
    order_id: int | None = None,
    tif: str | None = None,
    targeted: bool = False,
    order_ref: str | None = None,
) -> dict:
    """
    Place a market, limit, stop, stop-limit, or trailing-stop order
    (or price-modify when order_id set). ``targeted``: the execution door sent it to Live whatever
    the desk shows (Live's day cover, ADR 048 step 6), so the desk's practice guard does not apply.
    ``order_ref`` is Nova's reference (IBKR's orderRef), written to the ledger before this send.

    Returns {"ok": bool, "order_id": int|None, "error": str|None, "mode": str}.
    Adapter only — callers must enter via execution.service.execute (ADR 007).
    TRAIL uses stop_price as the IBKR trail $ (auxPrice). Trail % is not sent.
    ``tif`` None means IBKR_ORDER_TIF_DEFAULT (DAY); only IBKR_ORDER_TIFS pass.
    """
    from sim.mode import is_practice_venue

    if is_practice_venue() and not targeted:
        from sim.guard import refuse_place

        return _practice_refusal(refuse_place())

    order_type = normalize_order_type(order_type)  # type: ignore[assignment]
    tif = normalize_tif(tif)
    error = _validation_error(
        side, qty, order_type, limit_price, stop_price, outside_rth, tif,
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
            side, qty, order_type, limit_price, stop_price, outside_rth, tif, order_ref=order_ref,
        )
        if order_id is not None:
            order.orderId = int(order_id)

        from ibkr.loop_supervisor import assert_ib_loop, call_on_ib, is_ib_loop

        def _place():
            assert_ib_loop()
            return ib.placeOrder(contract, order)

        trade = _place() if is_ib_loop() else call_on_ib(_place, 15.0, label="placeOrder")
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
        price = limit_price if order_type in ("LMT", "STP LMT") else stop_price
        action = "modified" if order_id is not None else "placed"
        logger.info(
            "IBKR: %s %s %s %s %s @ %s outside_rth=%s tif=%s ref=%s (id=%s)",
            action,
            _client.account_mode(),
            order_type,
            side,
            qty,
            price,
            outside_rth,
            tif,
            order_ref,
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
            "nova_placed_at": nova_placed,
        }

    except Exception as exc:
        logger.exception("IBKR: order error for %s: %s", symbol, exc)
        return {"ok": False, "order_id": None, "error": str(exc), "mode": _client.account_mode()}


def cancel_order(order_id: int) -> dict:
    """
    Cancel an open order by ID.
    Allowed whenever connected (does not require IBKR_ORDERS_ENABLED).
    """
    from sim.mode import is_practice_venue

    if is_practice_venue():
        from sim.guard import refuse_cancel

        return _practice_refusal(refuse_cancel())

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
        _ib_sync(lambda: ib.cancelOrder(order), "cancelOrder")
        logger.info("IBKR: cancel requested for order %s", order_id)
        return {"ok": True, "error": None}
    except Exception as exc:
        logger.exception("IBKR: cancel error for order %s: %s", order_id, exc)
        return {"ok": False, "error": str(exc)}


def open_orders(*, ibkr_only: bool = False) -> list[dict]:
    """Return list of open / working orders as plain dicts.

    ``ibkr_only`` bypasses the selected desk venue for row-owned reconciliation.
    Includes fill progress fields from IBKR ``orderStatus`` so the Working
    Orders panel can mirror Webull-style qty/filled/avg columns without a
    separate history API.

    Raises ``IbkrAccountError`` on disconnect / API failure — a failed read
    must never look like "no working orders" (cancel-all and the kill-switch
    reconciliation both depend on knowing the difference).
    """
    practice = None if ibkr_only else _practice_broker()
    if practice is not None:
        return practice.working_orders()

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


def closed_orders(limit: int | None = None, *, ibkr_only: bool = False) -> list[dict]:
    """Return filled / cancelled / failed session orders (Closed Orders WID-027).

    ``ibkr_only`` bypasses the selected desk venue for row-owned reconciliation.
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

    practice = None if ibkr_only else _practice_broker()
    if practice is not None:
        return practice.closed_orders(limit)

    cap = IBKR_CLOSED_ORDERS_LIMIT_DEFAULT if limit is None else max(1, int(limit))
    ib = _client.get_ib()
    if ib is None:
        raise IbkrAccountError("IBKR not connected — cannot read closed orders")
    try:
        trades = list(ib.trades())
        # Transient Cancelled (Error 10349) can still be in openTrades as
        # PreSubmitted a tick later -- never list those as closed.
        open_fn = getattr(ib, "openTrades", None)
        open_trades = open_fn() if callable(open_fn) else []
        open_ids = {
            int(getattr(getattr(t, "order", None), "orderId", 0) or 0)
            for t in (open_trades or [])
        }
        rows: list[dict] = []
        for trade in trades:
            status = getattr(getattr(trade, "orderStatus", None), "status", "") or ""
            if status not in IBKR_CLOSED_ORDER_STATUSES:
                continue
            oid = int(getattr(getattr(trade, "order", None), "orderId", 0) or 0)
            if status in ("Cancelled", "ApiCancelled", "Inactive") and oid in open_ids:
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
    the post-READY ``completed_orders_warm`` task finishes. Only warms when
    the first read is empty *and* still connected; still raises
    ``IbkrAccountError`` like ``closed_orders`` when disconnected.
    """
    rows = closed_orders(limit=limit)
    if rows or _client.get_ib() is None:
        return rows
    from ibkr import account as _account
    from ibkr.loop_supervisor import is_ib_loop

    # HTTP / uvicorn is not the IB connect-loop. The post-READY warm already
    # runs on that loop; hopping reqCompletedOrders here 500s the blotter
    # (ADR 010). Skip and let the caller overlay the ledger.
    if not is_ib_loop():
        return rows
    try:
        await _account.refresh_completed_orders_cache()
    except Exception:
        logger.exception("closed_orders_async: completed-orders warm failed")
        return rows
    return closed_orders(limit=limit)
