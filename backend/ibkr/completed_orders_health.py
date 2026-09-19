"""Is the Gateway answering reqCompletedOrders? (D-058, PROBLEM_LOG 2026-09-19)

After a Gateway <-> IBKR server reconnect the Gateway can stop answering
``reqCompletedOrders`` for hours while every other request still works, so
Nova stays READY and the only symptom used to be a log line. This keeps the
first unanswered attempt so ``/api/ibkr/status``, the Trading prerequisites
panel and the morning check can say "not answering since HH:MM".

- ``reprobe_loop`` (an IB-loop task) re-asks every
  ``IBKR_COMPLETED_ORDERS_REPROBE_SEC`` while stamped, so the first answer
  clears it. Without it nothing re-asks until the next reconnect: the Closed
  Orders poll never warms off the IB loop.
- ``warn_since`` hides stamps younger than ``IBKR_COMPLETED_ORDERS_WARN_AFTER_SEC``
  so a Gateway that is merely slow at connect never reaches the desk.

In-memory on purpose: the stamp is the first failure *this API process* saw,
not the Gateway-side onset, and it never outlives a restart that might have
fixed the Gateway.
"""
from __future__ import annotations

import asyncio
import logging
import time

from ibkr.errors import StaleIbRequestError

logger = logging.getLogger(__name__)

_unanswered_since: float | None = None


def note_answered() -> None:
    global _unanswered_since
    _unanswered_since = None


def note_failed(exc: BaseException) -> None:
    """Stamp only "no answer" failures. A dropped socket or a busy cold slot
    is not the Gateway refusing completed orders."""
    global _unanswered_since
    if not isinstance(exc, (TimeoutError, StaleIbRequestError)):
        return
    if _unanswered_since is None:
        _unanswered_since = time.time()


def unanswered_since() -> float | None:
    """Epoch seconds of the first unanswered attempt, or None when answering."""
    return _unanswered_since


def warn_since(now: float | None = None) -> float | None:
    """The stamp once it is old enough to show the operator, else None."""
    from constants_ibkr import IBKR_COMPLETED_ORDERS_WARN_AFTER_SEC

    since = _unanswered_since
    if since is None:
        return None
    current = time.time() if now is None else now
    if current - since < float(IBKR_COMPLETED_ORDERS_WARN_AFTER_SEC):
        return None
    return since


async def reprobe_once() -> None:
    """One re-ask while stamped and READY. Outcome lands via account's hooks."""
    if _unanswered_since is None:
        return
    from ibkr import account as _account
    from ibkr import client as _client

    ib = _client.get_ib()
    if ib is None:
        return
    await _account.refresh_completed_orders_cache(ib, force=True)


async def reprobe_loop() -> None:
    """IB-loop task (spawn via loop_supervisor.spawn_ib)."""
    from constants_ibkr import IBKR_COMPLETED_ORDERS_REPROBE_SEC

    while True:
        await asyncio.sleep(float(IBKR_COMPLETED_ORDERS_REPROBE_SEC))
        try:
            await reprobe_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("IBKR: completed-orders re-probe failed", exc_info=True)


def reset_for_testing() -> None:
    global _unanswered_since
    _unanswered_since = None
