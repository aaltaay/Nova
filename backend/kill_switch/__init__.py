"""Kill switch (D-037, ADR 025): no Nova-originated spend of any source until reset.

``execution.service.execute`` refuses every place or bracket while the latch is
set, manual ticket and hotkeys included; only the protective sources (kill /
flatten / cancel_working) still reach the broker. The latch is persisted
(``kill_switch/state.py``) so an API restart cannot silently re-arm the desk;
only ``reset()`` clears it.

Tripping sets and persists the latch FIRST, so no place can race in between
the cancels, then cancels every working order on the account.
"""
from __future__ import annotations

import logging

from constants_nova_os import NOVA_OS_MODE_SIGNAL
from kill_switch import state as _state
from kill_switch import sweep as _sweep

logger = logging.getLogger(__name__)

__all__ = ["is_tripped", "reset", "status", "trip"]

# None = not hydrated from disk yet; read through is_tripped().
_tripped: bool | None = None


def is_tripped() -> bool:
    global _tripped
    if _tripped is None:
        _tripped = bool(_state.load()["tripped"])
        if _tripped:
            logger.warning(
                "kill switch restored TRIPPED from disk -- every place is refused "
                "until it is reset",
            )
    return _tripped


def status() -> dict:
    saved = _state.load()
    return {
        "tripped": is_tripped(),
        "reason": saved.get("reason"),
        "ts": saved.get("ts"),
    }


def trip(reason: str = "kill_switch") -> dict:
    """Latch, persist, then cancel every working order on the account."""
    global _tripped
    _tripped = True
    _state.save(tripped=True, reason=reason)
    cancelled, failed = _sweep.cancel_open_orders()
    from nova_os.events import KIND_SYSTEM, record_receipt

    record_receipt(
        kind=KIND_SYSTEM,
        mode=NOVA_OS_MODE_SIGNAL,
        payload={
            "event": "kill_switch",
            "cancelled_order_ids": cancelled,
            "failed_cancel_order_ids": failed,
            "blocks_manual_places": True,
            "persisted": True,
        },
    )
    logger.warning(
        "KILL SWITCH -- cancelled=%s failed=%s (every place blocked until reset)",
        cancelled, failed,
    )
    return {**status(), "cancelled_order_ids": cancelled, "failed_cancel_order_ids": failed}


def reset() -> dict:
    """Sole invalidation trigger for the persisted latch."""
    global _tripped
    _tripped = False
    _state.save(tripped=False, reason="reset_kill_switch")
    return status()


def reset_for_tests() -> None:
    global _tripped
    _tripped = None
