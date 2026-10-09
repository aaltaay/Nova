"""IB event handlers for OrderWatch (kept out of telemetry.py size budget).

Nothing IBKR says is dropped without a word: a fill or an order error no watch claims goes to
``execution.fill_claims`` / ``ibkr.unclaimed``, and every fill heard is remembered across reconnects
(``ibkr.session_fills``) so a new session can tell the fills it never heard.
"""
from __future__ import annotations

import logging
import time
import weakref
from typing import Any

from execution import fill_claims, inflight
from ibkr import session_fills

logger = logging.getLogger("execution.telemetry")


def float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def perm_id_or_none(order: Any) -> int | None:
    try:
        perm = int(getattr(order, "permId", 0) or 0)
    except (TypeError, ValueError):
        return None
    return perm if perm > 0 else None


def make_handlers(get_watch, ib: Any = None):
    """Bind handlers to a watch lookup (avoids circular imports) and the ``IB()`` they hear."""
    session = weakref.ref(ib) if ib is not None else (lambda: None)

    def on_ib_error(
        reqId: int, errorCode: int, errorString: str, _contract: Any = None,
    ) -> None:
        try:
            oid = int(reqId)
        except (TypeError, ValueError):
            return
        try:
            w = get_watch(oid)
            if w is None:
                # An order IBKR knows that no Nova watch holds: said, never dropped. A data request's
                # error (no such order) belongs to its own handler.
                fill_claims.unwatched_order_error(session(), oid, int(errorCode), str(errorString or ""))
                return
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
                perm_id=perm_id_or_none(trade.order),
                callback_perf_ns=time.perf_counter_ns(),
                callback_wall_ns=time.time_ns(),
                why_held=str(getattr(order_status, "whyHeld", "") or ""),
            )
            if status == "Filled":
                w.note_filled()
            inflight.release_on_broker_status(oid, status, "live")
        except Exception:
            logger.exception("execution.telemetry: orderStatus handler error")

    def on_exec_details(trade, fill) -> None:
        try:
            session_fills.note_heard(fill)
            oid = int(trade.order.orderId)
            w = get_watch(oid)
            if w is None:
                fill_claims.unwatched_fill(session(), fill)
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
                perm_id=perm_id_or_none(trade.order),
                callback_perf_ns=time.perf_counter_ns(),
                callback_wall_ns=time.time_ns(),
            )
            if complete:
                w.note_filled()
                inflight.release_order(oid, "live")
        except Exception:
            logger.exception("execution.telemetry: execDetails handler error")

    def on_commission(trade, fill, report) -> None:
        try:
            oid = int(trade.order.orderId)
            w = get_watch(oid)
            if w is None:
                return
            w.note_commission(float_or_none(getattr(report, "commission", None)))
        except Exception:
            logger.exception("execution.telemetry: commissionReport handler error")

    return on_ib_error, on_order_status, on_exec_details, on_commission


def note_reconciliation_fill(fill: Any, get_watch, *, complete: bool = True) -> bool:
    """Persist evidence from an existing poll/cache read; issues no IB request."""
    execution = getattr(fill, "execution", None)
    oid = int(getattr(execution, "orderId", 0) or 0)
    watch = get_watch(oid)
    if oid <= 0 or watch is None or watch.execution_id is None:
        return False
    from execution.reconciliation import record_reconciliation_fill

    return record_reconciliation_fill(fill, watch, complete=complete)
