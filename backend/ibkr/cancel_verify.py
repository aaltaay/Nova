"""Cancel an IBKR order and verify it left openTrades (fail loud).

Runs on the IB connect-loop (ADR 010): ``cancelOrder`` and ``openTrades`` are
``ib.*``. The verify wait is awaited, never slept -- the previous shape ran the
whole poll inside ``asyncio.to_thread``, so a worker thread called ``ib.*`` off
the connect-loop and blocked on ``time.sleep`` between reads.

The wait wakes on the order's next ``orderStatus`` callback when a telemetry
watch is supplied, and falls back to the poll interval otherwise.
"""
from __future__ import annotations

import asyncio
import logging
import time

from constants import (
    EXECUTION_CANCEL_VERIFY_HOP_MARGIN_SEC,
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


def _ok(order_id: int) -> dict:
    return {"ok": True, "error": None, "verified_gone": True, "order_id": order_id}


def _failed(order_id: int, error: str) -> dict:
    return {
        "ok": False,
        "error": error,
        "verified_gone": False,
        "order_id": order_id,
    }


async def _wait_for_status(watch, timeout: float) -> None:
    """Sleep ``timeout`` unless ``watch`` reports an orderStatus sooner."""
    if watch is None:
        await asyncio.sleep(timeout)
        return
    changed = asyncio.get_running_loop().create_future()

    def _on_status(_status: str) -> None:
        if not changed.done():
            changed.set_result(None)

    watch.add_status_listener(_on_status)
    try:
        await asyncio.wait_for(changed, timeout=timeout)
    except asyncio.TimeoutError:  # maintainer: allow-swallow the timeout is the normal end of the wait
        pass
    finally:
        watch.remove_status_listener(_on_status)


async def cancel_order_verified(
    order_id: int,
    *,
    timeout_sec: float | None = None,
    poll_sec: float | None = None,
    watch=None,
) -> dict:
    """Request cancel, then await until absent from open orders or timeout."""
    raw = _orders.cancel_order(order_id)
    if not raw.get("ok"):
        return _failed(order_id, raw.get("error") or "cancel rejected")

    timeout = max(
        0.1,
        float(
            EXECUTION_CANCEL_VERIFY_TIMEOUT_SEC if timeout_sec is None else timeout_sec
        ),
    )
    poll = max(
        0.05,
        float(EXECUTION_CANCEL_VERIFY_POLL_SEC if poll_sec is None else poll_sec),
    )
    deadline = time.monotonic() + timeout
    while True:
        if not _order_still_open(order_id):
            return _ok(order_id)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await _wait_for_status(watch, min(poll, remaining))

    if not _order_still_open(order_id):
        return _ok(order_id)
    msg = f"Cancel requested for {order_id} but order still open after {timeout:.1f}s"
    logger.error("cancel_verify: %s", msg)
    return _failed(order_id, msg)


async def cancel_order_verified_on_ib(order_id: int, *, watch=None) -> dict:
    """Entry point for the execution service: run the verify on the IB loop."""
    from ibkr.loop_supervisor import on_ib

    budget = float(EXECUTION_CANCEL_VERIFY_TIMEOUT_SEC) + float(
        EXECUTION_CANCEL_VERIFY_HOP_MARGIN_SEC
    )
    try:
        return await on_ib(
            cancel_order_verified(order_id, watch=watch),
            budget,
            label="cancel_verify",
        )
    except Exception as exc:
        logger.exception("cancel_verify: hop failed for order %s", order_id)
        return _failed(order_id, f"cancel verify failed: {exc}")
