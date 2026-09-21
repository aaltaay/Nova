"""Execution-telemetry bridge for the practice venues (ADR 020).

The practice broker settles its own orders -- a fill, a buying-power cancel, a
DAY expiry -- with no IBKR callback to carry the news, so it tells the
execution telemetry watch itself. Import failures are logged and swallowed:
telemetry is a reader of the venue, never a gate on it.
"""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def notify_watch(order_id: int, row: dict[str, Any]) -> None:
    """Tell the execution telemetry watch what the practice venue decided."""
    try:
        from execution import telemetry
    except Exception:
        logger.debug("PRACTICE: telemetry import failed", exc_info=True)
        return
    watch = telemetry.watch_order(int(order_id))
    avg = row.get("avg_fill_price")
    watch.note_status(
        str(row.get("status") or "Submitted"),
        filled=float(row.get("filled_qty") or 0),
        remaining=float(row.get("remaining_qty") or 0),
        average_fill_price=float(avg) if avg else None,
        perm_id=int(order_id),
        callback_perf_ns=time.perf_counter_ns(),
    )
