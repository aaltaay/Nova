"""IB event handlers for OrderWatch (kept out of telemetry.py size budget)."""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("execution.telemetry")


def float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def make_handlers(get_watch):
    """Bind handlers to a watch lookup (avoids circular imports)."""

    def on_ib_error(
        reqId: int, errorCode: int, errorString: str, _contract: Any = None,
    ) -> None:
        try:
            oid = int(reqId)
        except (TypeError, ValueError):
            return
        w = get_watch(oid)
        if w is None:
            return
        try:
            w.note_error(int(errorCode), str(errorString or ""))
        except Exception:
            logger.exception("execution.telemetry: errorEvent handler error")

    def on_order_status(trade) -> None:
        try:
            oid = int(trade.order.orderId)
            status = str(trade.orderStatus.status or "")
            w = get_watch(oid)
            if w is None:
                return
            order_status = trade.orderStatus
            w.note_status(
                status,
                filled=float_or_none(getattr(order_status, "filled", None)),
                remaining=float_or_none(getattr(order_status, "remaining", None)),
                average_fill_price=float_or_none(
                    getattr(order_status, "avgFillPrice", None)
                ),
                callback_perf_ns=time.perf_counter_ns(),
                callback_wall_ns=time.time_ns(),
            )
            if status == "Filled":
                w.note_filled()
        except Exception:
            logger.exception("execution.telemetry: orderStatus handler error")

    def on_exec_details(trade, fill) -> None:
        try:
            oid = int(trade.order.orderId)
            w = get_watch(oid)
            if w is None:
                return
            execution = fill.execution
            order_status = trade.orderStatus
            remaining = float_or_none(getattr(trade.orderStatus, "remaining", None))
            cumulative = float_or_none(getattr(order_status, "filled", None))
            requested = float_or_none(
                getattr(getattr(trade, "order", None), "totalQuantity", None)
            )
            complete = (
                (
                    cumulative is not None
                    and requested is not None
                    and requested > 0
                    and cumulative >= requested
                )
                or str(trade.orderStatus.status) == "Filled"
            )
            w.note_execution(
                avg_price=float_or_none(getattr(execution, "avgPrice", None)),
                price=float_or_none(getattr(execution, "price", None)),
                shares=float_or_none(getattr(execution, "shares", None)),
                cumulative_shares=cumulative,
                remaining=remaining,
                exchange_time=getattr(execution, "time", None),
                complete=complete,
                callback_perf_ns=time.perf_counter_ns(),
                callback_wall_ns=time.time_ns(),
            )
            if complete:
                w.note_filled()
        except Exception:
            logger.exception("execution.telemetry: execDetails handler error")

    return on_ib_error, on_order_status, on_exec_details
