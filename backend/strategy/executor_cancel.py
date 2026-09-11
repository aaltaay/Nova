"""Executor cancel paths — every cancel goes through execution.service (ADR 007).

Extracted from `strategy/executor.py` when the D-037 kill-switch sweep pushed
that module past the 400-line limit (file-size-limits.mdc). These three
helpers take a position/ids argument and own no module state, so they move
cleanly; `kill_switch()` / `cancel_working_entry()` stay in `executor.py`
because they mutate `_open_positions` and the kill latch.
"""
from __future__ import annotations

import asyncio
import logging

from ibkr import client as _ibkr_client
from ibkr import orders as _orders

logger = logging.getLogger(__name__)

CancelOutcome = str  # cancelled_unfilled | preserved_protective | unknown_state


def cancel_via_service(order_id: int, *, source: str) -> dict:
    """Sync cancel helper for kill/flatten — uses execution.service."""
    import uuid

    from execution.models import ExecutionCommand
    from execution.service import execute

    async def _run():
        return await execute(
            ExecutionCommand(
                operation="cancel",
                idempotency_key=f"{source}:cancel:{order_id}:{uuid.uuid4()}",
                source=source,  # type: ignore[arg-type]
                order_id=order_id,
                skip_risk=True,
                skip_concurrency=True,
            ),
            wait_ack=False,
        )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        receipt = asyncio.run(_run())
        return receipt.legacy_place_dict()
    # Nested in async context (e.g. fill poll) — schedule and do not block forever.
    # Kill/flatten routes are sync FastAPI handlers, so asyncio.run is the common path.
    raise RuntimeError("cancel from running loop — use async execute directly")


def cancel_bracket_if_parent_unfilled(pos) -> tuple[list[int], CancelOutcome]:
    """Cancel parent+children only when parent is still in open_orders.

    Returns (cancelled_ids, outcome) where outcome is
    'cancelled_unfilled' | 'preserved_protective' | 'unknown_state'.
    """
    if not _ibkr_client.is_connected():
        return [], "unknown_state"
    try:
        open_ids = {o["order_id"] for o in _orders.open_orders()}
    except _orders.IbkrAccountError as exc:
        # Cannot verify whether the parent is still working — treat as
        # unknown rather than guessing "unfilled" and cancelling a filled
        # position's live protective stop/target.
        logger.exception("kill/cancel: open_orders failed for %s — %s", pos.symbol, exc)
        return [], "unknown_state"
    if pos.parent_order_id not in open_ids:
        return [], "preserved_protective"
    cancelled: list[int] = []
    for order_id in (pos.parent_order_id, pos.target_order_id, pos.stop_order_id):
        try:
            cancel_via_service(order_id, source="kill")
            cancelled.append(order_id)
        except Exception:
            logger.exception("cancel failed for order %s (%s)", order_id, pos.symbol)
    return cancelled, "cancelled_unfilled"


def cancel_remaining_open_orders(
    *, preserve_ids: set[int], already_cancelled: set[int],
) -> tuple[list[int], list[int]]:
    """Cancel every other working order so nothing can fill after a kill.

    `preserve_ids` are protective legs of already-filled parents — cancelling
    those would leave a naked position, which is the opposite of a kill.
    Returns (cancelled_ids, failed_ids).
    """
    if not _ibkr_client.is_connected():
        return [], []
    try:
        rows = _orders.open_orders()
    except _orders.IbkrAccountError as exc:
        logger.exception("kill: open_orders failed — sweep skipped (%s)", exc)
        return [], []
    cancelled: list[int] = []
    failed: list[int] = []
    for row in rows:
        raw_id = row.get("order_id")
        if raw_id is None:
            continue
        order_id = int(raw_id)
        if order_id in preserve_ids or order_id in already_cancelled:
            continue
        try:
            cancel_via_service(order_id, source="kill")
            cancelled.append(order_id)
        except Exception:
            logger.exception("kill: sweep cancel failed for order %s", order_id)
            failed.append(order_id)
    return cancelled, failed
