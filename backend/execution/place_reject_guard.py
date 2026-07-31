"""Heal false Cancelled acks (Error 10349) before writing ledger failed."""
from __future__ import annotations

import asyncio

from constants import (
    EXECUTION_CANCEL_ACK_GRACE_SEC,
    IBKR_ERROR_FRACTIONAL_API,
    IBKR_ERROR_TIF_PRESET,
)
from execution import telemetry
from ibkr import orders as _orders


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
