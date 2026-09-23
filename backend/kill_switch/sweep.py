"""Kill-switch cancel sweep -- every cancel goes through execution.service (ADR 007).

Moved from ``strategy/executor_cancel.py`` when the Phase D executor was retired
(ADR 025). Owns no state: it cancels every working order on the account so
nothing can fill after a kill.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from ibkr import client as _ibkr_client
from ibkr import orders as _orders

logger = logging.getLogger(__name__)


def cancel_via_service(order_id: int) -> dict:
    """Sync cancel through execution.service with the protective ``kill`` source."""
    from execution.models import ExecutionCommand
    from execution.service import execute

    async def _run():
        return await execute(
            ExecutionCommand(
                operation="cancel",
                idempotency_key=f"kill:cancel:{order_id}:{uuid.uuid4()}",
                source="kill",
                order_id=order_id,
                skip_risk=True,
            ),
            wait_ack=False,
        )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        receipt = asyncio.run(_run())
        return receipt.legacy_place_dict()
    # The kill route is a sync FastAPI handler, so asyncio.run is the path taken.
    raise RuntimeError("kill cancel from a running loop -- use async execute directly")


def cancel_open_orders() -> tuple[list[int], list[int]]:
    """Cancel every working order on the account. Returns (cancelled, failed)."""
    if not _ibkr_client.is_connected():
        return [], []
    try:
        rows = _orders.open_orders()
    except _orders.IbkrAccountError as exc:
        logger.exception("kill: open_orders failed -- sweep skipped (%s)", exc)
        return [], []
    cancelled: list[int] = []
    failed: list[int] = []
    for row in rows:
        raw_id = row.get("order_id")
        if raw_id is None:
            continue
        order_id = int(raw_id)
        try:
            cancel_via_service(order_id)
            cancelled.append(order_id)
        except Exception:
            logger.exception("kill: sweep cancel failed for order %s", order_id)
            failed.append(order_id)
    return cancelled, failed
