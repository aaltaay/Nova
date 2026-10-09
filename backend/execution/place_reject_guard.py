"""Heal false Cancelled acks (Error 10349) before writing ledger failed."""
from __future__ import annotations

import asyncio

from constants import (
    EXECUTION_CANCEL_ACK_GRACE_SEC,
    IBKR_ERROR_FRACTIONAL_API,
    IBKR_ERROR_TIF_PRESET,
)
from execution import telemetry
from execution.order_outcome import closed_state, is_closure_notice
from ibkr import orders as _orders


def closed_not_refused(watch: telemetry.OrderWatch) -> bool:
    """IBKR closed the order with a closure notice and no hard error: a cancel, never a reject.

    10148 (the order was already closed) and 201 naming the OCA group (a one-cancels-all sibling
    filled) say why the order closed; neither is IBKR refusing it.
    """
    return watch.error_code is None and any(is_closure_notice(c, m) for c, m in watch.error_events)


def cancel_came_too_late(watch: telemetry.OrderWatch) -> bool:
    """The order a cancel named had already filled: 10148 says ``state: Filled``, or the fill reached the watch.

    The order left the working orders because it filled, so "gone" is not "cancelled".
    """
    if watch.has_fill() or watch.latest_status == "Filled":
        return True
    return (closed_state(watch.error_events) or "").lower() == "filled"


def order_still_open(order_id: int) -> bool:
    try:
        return any(
            int(r.get("order_id") or 0) == int(order_id)
            for r in _orders.open_orders()
        )
    except Exception:
        return False


async def confirm_terminal_reject(
    watch: telemetry.OrderWatch,
    order_id: int | None,
) -> tuple[bool, str | None]:
    """Return (is_reject, broker_status). Grace + open_orders heal false cancels."""
    status = watch.ack_status or watch.latest_status
    if (status or "") not in telemetry.TERMINAL_REJECT_STATUSES:
        return False, status
    if watch.has_fill():
        return False, status
    if watch.error_code == IBKR_ERROR_FRACTIONAL_API:
        return True, status
    # Error 10349 alone is informational -- never a reject by itself.
    if watch.error_code == IBKR_ERROR_TIF_PRESET:
        await asyncio.sleep(EXECUTION_CANCEL_ACK_GRACE_SEC)
        latest = watch.latest_status or watch.ack_status
        if latest in telemetry.WORKING_ACK_STATUSES:
            return False, latest
        if order_id is not None and order_still_open(order_id):
            return False, latest or "PreSubmitted"
    await asyncio.sleep(EXECUTION_CANCEL_ACK_GRACE_SEC)
    latest = watch.latest_status or watch.ack_status
    if latest in telemetry.WORKING_ACK_STATUSES:
        return False, latest
    if order_id is not None and order_still_open(order_id):
        return False, latest or "PreSubmitted"
    return True, latest
