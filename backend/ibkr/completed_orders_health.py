"""Is the Gateway answering reqCompletedOrders? (D-058, PROBLEM_LOG 2026-09-19)

After a Gateway <-> IBKR server reconnect the Gateway can stop answering
``reqCompletedOrders`` for hours while every other request still works, so
Nova stays READY and the only symptom used to be a log line. This keeps the
first unanswered attempt so ``/api/ibkr/status``, the Trading prerequisites
panel and the morning check can say "not answering since HH:MM". The first
answered refresh clears it.

In-memory on purpose: the stamp is the first failure *this API process* saw,
not the Gateway-side onset, and it never outlives a restart that might have
fixed the Gateway.
"""
from __future__ import annotations

import time

from ibkr.errors import StaleIbRequestError

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


def reset_for_testing() -> None:
    global _unanswered_since
    _unanswered_since = None
