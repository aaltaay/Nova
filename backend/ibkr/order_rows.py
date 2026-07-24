"""Public IBKR order-row mapping and passive fill reconciliation evidence."""
from __future__ import annotations


def _nonzero_price(value) -> float | None:
    """IB often sends 0.0 for unused LMT/STP fields — expose as null."""
    if value is None:
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price != 0.0 else None


def trade_to_order_row(trade) -> dict:
    """Map one cached Trade; recording evidence adds no broker request."""
    from execution.telemetry import note_reconciliation_fill
    from ibkr.order_times import extract_trade_times, resolve_submitted_at

    status = trade.orderStatus
    qty = trade.order.totalQuantity
    filled = getattr(status, "filled", None)
    remaining = getattr(status, "remaining", None)
    avg_fill = getattr(status, "avgFillPrice", None)
    filled_qty = float(filled) if filled is not None else 0.0
    remaining_qty = float(remaining) if remaining is not None else None
    if status.status == "Filled" and filled_qty == 0.0 and qty:
        filled_qty = float(qty)
        remaining_qty = 0.0
    for fill in getattr(trade, "fills", None) or []:
        note_reconciliation_fill(
            fill,
            complete=bool(
                status.status == "Filled"
                or (remaining_qty is not None and remaining_qty <= 0)
            ),
        )
    broker_submitted, updated_at, filled_at = extract_trade_times(trade)
    oid = trade.order.orderId
    submitted_at = resolve_submitted_at(broker_submitted, oid)
    return {
        "order_id": oid,
        "symbol": trade.contract.symbol,
        "side": trade.order.action,
        "qty": qty,
        "filled_qty": filled_qty,
        "remaining_qty": remaining_qty,
        "order_type": trade.order.orderType,
        "limit_price": _nonzero_price(getattr(trade.order, "lmtPrice", None)),
        "stop_price": _nonzero_price(getattr(trade.order, "auxPrice", None)),
        "avg_fill_price": (
            float(avg_fill) if avg_fill not in (None, 0, 0.0) else None
        ),
        "outside_rth": bool(getattr(trade.order, "outsideRth", False)),
        "status": status.status,
        "submitted_at": submitted_at,
        "updated_at": updated_at,
        "filled_at": filled_at,
    }
