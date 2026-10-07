"""Kill switch (D-037, ADR 025): no Nova-originated order of any source until reset.

``execution.service.execute`` refuses every place or bracket while the latch is
set, on every venue, manual ticket and hotkeys included; only the protective
sources (kill / flatten / cancel_working) and cancels still reach a broker. The
latch is persisted (``kill_switch/state.py``) so an API restart cannot silently
re-arm the desk; only ``reset()`` clears it. It sells nothing: positions stay.

Tripping sets and persists the latch FIRST, so no place can race in between
the cancels, then cancels every working order on every venue that has any --
Live while IBKR is connected, Paper always, Sim when a scratch ledger is loaded
(``kill_switch/sweep.py``, spec D, #656) -- except the stops that protect a held
position, which stay resting (ADR 048). The answer and the receipt say, per
venue, what was cancelled, what failed and why, and which stops were kept.
"""
from __future__ import annotations

import logging
from typing import Any

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


def _desk_venue() -> str | None:
    try:
        from sim.mode import venue

        return venue()
    except Exception:
        logger.exception("kill switch: the desk venue is unreadable -- the receipt names none")
        return None


def _record(sweep: list[dict[str, Any]], cancelled: list[int], failed: list[int], persisted: bool) -> str | None:
    """The ``kill_switch`` receipt, stamped with the desk venue; the error when it could not be written."""
    from nova_os.events import KIND_SYSTEM, record_receipt

    try:
        record_receipt(
            kind=KIND_SYSTEM,
            executed=bool(cancelled),
            payload={
                "event": "kill_switch",
                "venue": _desk_venue(),             # the desk venue, not a retired Nova OS mode
                "sweep": sweep,
                "cancelled_order_ids": cancelled,
                "failed_cancel_order_ids": failed,
                "blocks_manual_places": True,
                "persisted": persisted,
            },
        )
    except Exception as exc:
        logger.exception("kill switch: the receipt could not be written -- the trip itself stands")
        return f"{type(exc).__name__}: {exc}"
    return None


async def trip(reason: str = "kill_switch") -> dict:
    """Latch, persist, then cancel every working order on every venue that has any."""
    global _tripped
    _tripped = True
    persisted = _state.save(tripped=True, reason=reason)
    sweep = await _sweep.sweep_every_venue()
    cancelled = [oid for venue in sweep for oid in venue["cancelled"]]
    failed = [oid for venue in sweep for oid in venue["failed"]]
    kept = [row["order_id"] for venue in sweep for row in venue.get("kept") or []]
    receipt_error = _record(sweep, cancelled, failed, persisted)
    from short_proof import observe as _proof

    _proof.note_freeze(sweep)       # the Live short proof's freeze drill (ADR 048 step 6); never raises
    logger.warning(
        "KILL SWITCH -- every new order refused until reset; sweep %s",
        "; ".join(f"{v['venue']}: cancelled={v['cancelled']} failed={v['failed']} "
                  f"kept={[k['order_id'] for k in v.get('kept') or []]}"
                  + (f" ({v['error']})" if v["error"] else "") for v in sweep),
    )
    return {**status(), "persisted": persisted, "sweep": sweep, "cancelled_order_ids": cancelled,
            "failed_cancel_order_ids": failed, "kept_order_ids": kept, "receipt_error": receipt_error}


def reset() -> dict:
    """Sole invalidation trigger for the persisted latch."""
    global _tripped
    _tripped = False
    persisted = _state.save(tripped=False, reason="reset_kill_switch")
    return {**status(), "persisted": persisted}


def reset_for_tests() -> None:
    global _tripped
    _tripped = None
