"""Cancel an IBKR order and verify it left openTrades (fail loud)."""
from __future__ import annotations

import logging
import time

from constants import (
    EXECUTION_CANCEL_VERIFY_POLL_SEC,
    EXECUTION_CANCEL_VERIFY_TIMEOUT_SEC,
)
from ibkr import orders as _orders

logger = logging.getLogger(__name__)


def _order_still_open(order_id: int) -> bool:
    try:
        rows = _orders.open_orders()
    except Exception:
        logger.exception("cancel_verify: open_orders failed for %s", order_id)
        return True  # fail closed -- treat as still open
    return any(int(r.get("order_id") or 0) == int(order_id) for r in rows)


def cancel_order_verified(
    order_id: int,
    *,
    timeout_sec: float = EXECUTION_CANCEL_VERIFY_TIMEOUT_SEC,
    poll_sec: float = EXECUTION_CANCEL_VERIFY_POLL_SEC,
) -> dict:
    """Request cancel, then poll until absent from open orders or timeout."""
    raw = _orders.cancel_order(order_id)
    if not raw.get("ok"):
        return {
            "ok": False,
            "error": raw.get("error") or "cancel rejected",
            "verified_gone": False,
            "order_id": order_id,
        }

    deadline = time.monotonic() + max(0.1, float(timeout_sec))
    while time.monotonic() < deadline:
        if not _order_still_open(order_id):
            return {
                "ok": True,
                "error": None,
                "verified_gone": True,
                "order_id": order_id,
            }
        time.sleep(max(0.05, float(poll_sec)))

    still = _order_still_open(order_id)
    if not still:
        return {
            "ok": True,
            "error": None,
            "verified_gone": True,
            "order_id": order_id,
        }
    msg = f"Cancel requested for {order_id} but order still open after {timeout_sec:.1f}s"
    logger.error("cancel_verify: %s", msg)
    return {
        "ok": False,
        "error": msg,
        "verified_gone": False,
        "order_id": order_id,
    }
