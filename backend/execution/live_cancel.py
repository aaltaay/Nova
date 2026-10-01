"""IBKR's verified cancel for a kill switch cancel aimed at Live, whatever the desk shows (spec D).

``ibkr.orders.cancel_order`` and ``open_orders`` answer for the desk's venue: on Paper or Sim
they refuse the cancel and read the practice ledger. The kill switch sweeps Live's working orders
from any desk (``kill_switch.sweep``), so its Live cancel asks IBKR itself -- the request and the
verify of ``ibkr.cancel_verify.cancel_order_verified``, without the desk-venue hook. Only the
execution door calls this, for a ``kill`` cancel whose ``target_venue`` is Live
(``execution.venue_door``). It runs on the IB loop (ADR 010), like every ``ib.*`` call.

Owner: this module (no state).
"""
from __future__ import annotations

import logging
import time

from constants import (
    EXECUTION_CANCEL_VERIFY_HOP_MARGIN_SEC,
    EXECUTION_CANCEL_VERIFY_POLL_SEC,
    EXECUTION_CANCEL_VERIFY_TIMEOUT_SEC,
)
from ibkr import client as _client
from ibkr import safety as _safety
from ibkr.cancel_verify import _wait_for_status

logger = logging.getLogger(__name__)


def _result(order_id: int, error: str | None) -> dict:
    return {"ok": error is None, "error": error, "verified_gone": error is None, "order_id": order_id}


def _still_open(ib, order_id: int) -> bool:
    """IBKR's own open trades, never the desk's practice ledger; unreadable counts as still open."""
    try:
        return any(int(trade.order.orderId) == int(order_id) for trade in ib.openTrades())
    except Exception:
        logger.exception("kill live cancel: IBKR's open orders unreadable for %s -- counted still open", order_id)
        return True


async def _cancel_and_verify(order_id: int, watch=None) -> dict:
    ok, reason = _safety.assert_cancel_allowed(
        client_enabled=_client.is_enabled(), connected=_client.is_connected(),
    )
    if not ok:
        return _result(order_id, reason)
    ib = _client.get_ib()
    if ib is None:
        return _result(order_id, "IBKR's session is not ready -- the Live cancel was not sent")
    from ib_async import Order

    order = Order()
    order.orderId = int(order_id)
    ib.cancelOrder(order)
    logger.info("kill live cancel: cancel requested for IBKR order %s", order_id)
    timeout = max(0.1, float(EXECUTION_CANCEL_VERIFY_TIMEOUT_SEC))
    deadline = time.monotonic() + timeout
    while True:
        if not _still_open(ib, order_id):
            return _result(order_id, None)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await _wait_for_status(watch, min(float(EXECUTION_CANCEL_VERIFY_POLL_SEC), remaining))
    if not _still_open(ib, order_id):
        return _result(order_id, None)
    message = f"Cancel requested for {order_id} but order still open after {timeout:.1f}s"
    logger.error("kill live cancel: %s", message)
    return _result(order_id, message)


async def cancel_verified(order_id: int, *, watch=None) -> dict:
    """Cancel IBKR order ``order_id`` and wait until it leaves IBKR's open orders, on the IB loop."""
    from ibkr.loop_supervisor import on_ib

    budget = float(EXECUTION_CANCEL_VERIFY_TIMEOUT_SEC) + float(EXECUTION_CANCEL_VERIFY_HOP_MARGIN_SEC)
    try:
        return await on_ib(_cancel_and_verify(order_id, watch), budget, label="kill_live_cancel")
    except Exception as exc:
        logger.exception("kill live cancel: hop failed for order %s", order_id)
        return _result(order_id, f"cancel verify failed: {exc}")
