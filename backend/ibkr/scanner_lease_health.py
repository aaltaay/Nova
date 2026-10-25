"""When a persistent scanner lease is sick, and freeing slots after a refusal.

``scanner_stream._watchdog_once`` asks ``reopen_reason`` about each lease and
cancels and reopens the ones it names. Two kinds of sick:

- **Never answered** -- no batch since the lease opened, past
  ``IBKR_SCANNER_FIRST_BATCH_RESUBSCRIBE_SEC``. Each reopen restarts the
  clock, so a Gateway that refuses scans is asked once per limit, never
  faster. On 2026-10-23 a Gainers lease IBKR refused with Error 322 sat empty
  04:00-16:00 because the watchdog skipped leases that had never delivered.
- **Stalled** -- batches stopped for ``max(min, mult x cadence)``.

An empty batch (``updateEvent`` with 0 rows) is an answer and sets
``last_batch_mono`` -- the 2026-08-07 lesson in
``scanner_stream.in_ready_quiet_window``. Only no event at all is silence.
"""
from __future__ import annotations

import logging
from typing import Any

from constants import (
    IBKR_ERROR_SCANNER_SLOT_EXHAUSTED,
    IBKR_SCANNER_FIRST_BATCH_RESUBSCRIBE_SEC,
    IBKR_SCANNER_WATCHDOG_CADENCE_MULT,
    IBKR_SCANNER_WATCHDOG_MIN_SEC,
)

logger = logging.getLogger(__name__)


def reopen_reason(lease: Any, now_m: float) -> tuple[str, float, float] | None:
    """``(what, age, limit)`` when ``lease`` should be reopened at ``now_m``, else None."""
    if lease.last_batch_mono <= 0:
        age = now_m - lease.opened_mono
        limit = IBKR_SCANNER_FIRST_BATCH_RESUBSCRIBE_SEC
        return ("no batch since open", age, limit) if age > limit else None
    age = now_m - lease.last_batch_mono
    cadence = (
        sum(lease.batch_intervals) / len(lease.batch_intervals)
        if lease.batch_intervals else IBKR_SCANNER_WATCHDOG_MIN_SEC
    )
    limit = max(
        IBKR_SCANNER_WATCHDOG_MIN_SEC,
        IBKR_SCANNER_WATCHDOG_CADENCE_MULT * cadence,
    )
    return ("batch age", age, limit) if age > limit else None


def free_slots_if_refused(table: str, lease: Any, ib: Any) -> None:
    """IBKR refused ``lease`` with Error 322: cancel this client's leaked scanner
    slots so its reopen can get one. Desired leases are never touched --
    ``recover_scanner_slots`` fences ``scanner_stream.persistent_reqids``."""
    if lease.ib_error_code != IBKR_ERROR_SCANNER_SLOT_EXHAUSTED:
        return
    from ibkr import discovery

    recovered = discovery.recover_scanner_slots(ib)
    logger.warning(
        "scanner_stream: %s was refused with Error %d -- freed %d leaked scanner slot(s)",
        table, IBKR_ERROR_SCANNER_SLOT_EXHAUSTED, recovered,
    )
