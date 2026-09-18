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
    from execution.order_outcome import honest_broker_fill_qty
    from execution.telemetry import note_reconciliation_fill
    from ibkr.order_times import extract_trade_times, resolve_submitted_at

    status = trade.orderStatus
    qty = trade.order.totalQuantity
    remaining = getattr(status, "remaining", None)
    remaining_qty = float(remaining) if remaining is not None else None
    fills = list(getattr(trade, "fills", None) or [])
    filled_qty = 0.0
    avg_fill: float | None = None
    notional = 0.0
    commission_total = 0.0
    has_commission = False
    for fill in fills:
        note_reconciliation_fill(
            fill,
            complete=bool(
                status.status == "Filled"
                or (remaining_qty is not None and remaining_qty <= 0)
            ),
        )
        execution = getattr(fill, "execution", None)
        try:
            shares = float(getattr(execution, "shares", 0) or 0)
        except (TypeError, ValueError):
            shares = 0.0
        try:
            price = float(getattr(execution, "price", 0) or 0)
        except (TypeError, ValueError):
            price = 0.0
        if shares > 0 and price > 0:
            filled_qty += shares
            notional += shares * price
        report = getattr(fill, "commissionReport", None)
        if report is not None:
            try:
                commission_total += float(getattr(report, "commission", 0) or 0)
                has_commission = True
            except (TypeError, ValueError):
                pass
    if filled_qty > 0:
        avg_fill = notional / filled_qty
    elif fills:
        # Real execDetails exist but shares/price were omitted on the object
        # (unit fixtures). Status filled/avg are allowed only as companions
        # to those fills -- never when Trade.fills is empty.
        try:
            status_filled = float(getattr(status, "filled", 0) or 0)
        except (TypeError, ValueError):
            status_filled = 0.0
        if status_filled > 0:
            filled_qty = status_filled
        raw_avg = getattr(status, "avgFillPrice", None)
        if raw_avg not in (None, 0, 0.0):
            try:
                avg_fill = float(raw_avg)
            except (TypeError, ValueError):
                avg_fill = None
    try:
        status_filled = float(getattr(status, "filled", 0) or 0)
    except (TypeError, ValueError):
        status_filled = 0.0
    inferred, warm_completed = honest_broker_fill_qty(
        ib_status=status.status,
        exec_filled_qty=filled_qty,
        status_filled_qty=status_filled,
        requested_qty=qty,
    )
    if inferred > 0:
        filled_qty = inferred
        if warm_completed:
            remaining_qty = 0.0
        if avg_fill is None:
            raw_avg = getattr(status, "avgFillPrice", None)
            if raw_avg not in (None, 0, 0.0):
                try:
                    avg_fill = float(raw_avg)
                except (TypeError, ValueError):
                    avg_fill = None
    if filled_qty <= 0:
        remaining_qty = float(remaining) if remaining is not None else (
            float(qty) if qty else None
        )
    broker_submitted, updated_at, filled_at = extract_trade_times(trade)
    if filled_qty <= 0:
        filled_at = None
        avg_fill = None
        filled_qty = 0.0
    elif not fills:
        # Broker fill size is real; no execDetails clock on this session.
        filled_at = None
    oid = trade.order.orderId
    submitted_at = resolve_submitted_at(broker_submitted, oid)
    if filled_at:
        from execution.fill_audit_clock import honest_filled_at_iso

        filled_at = honest_filled_at_iso(submitted_at, filled_at)
    from ibkr.order_held_until import held_until_iso_from_trade

    perm_raw = getattr(trade.order, "permId", None)
    try:
        perm_id = int(perm_raw) if perm_raw not in (None, 0, "0") else None
    except (TypeError, ValueError):
        perm_id = None
    if perm_id is not None and perm_id <= 0:
        perm_id = None

    return {
        "order_id": oid,
        "perm_id": perm_id,
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
        "held_until": held_until_iso_from_trade(trade),
        "commission": commission_total if has_commission else None,
    }
