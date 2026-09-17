"""Nova auto-cancel for bot working orders after session TTL."""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from bot.audit import record as audit
from bot.persist import load_session
from bot.risk import drop_working
from constants_bot import BOT_REASON_TTL_EXPIRED

logger = logging.getLogger(__name__)


def due_working(now: float | None = None) -> list[dict[str, Any]]:
    stamp = time.time() if now is None else now
    row = load_session()
    due: list[dict[str, Any]] = []
    for item in list(row.get("working") or []):
        try:
            expire = float(item.get("expire_ts") or 0)
        except (TypeError, ValueError):
            expire = 0
        if expire and expire <= stamp:
            due.append(item)
    return due


async def cancel_due() -> list[dict[str, Any]]:
    from execution.models import ExecutionCommand
    from execution.service import execute

    results: list[dict[str, Any]] = []
    for item in due_working():
        order_id = item.get("order_id")
        if order_id is None:
            drop_working(0)
            continue
        receipt = await execute(
            ExecutionCommand(
                operation="cancel",
                idempotency_key=f"bot:ttl:{order_id}:{uuid.uuid4()}",
                source="bot",
                order_id=int(order_id),
                symbol=str(item.get("symbol") or "") or None,
                skip_risk=True,
                skip_concurrency=True,
            ),
            wait_ack=False,
        )
        drop_working(int(order_id))
        audit(
            action="ttl_cancel",
            outcome="ok" if receipt.ok else "failed",
            reason=BOT_REASON_TTL_EXPIRED,
            order_id=int(order_id),
            inputs=item,
        )
        results.append(receipt.legacy_place_dict())
    return results
