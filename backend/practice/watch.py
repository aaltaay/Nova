"""Execution-telemetry bridge for the practice venues (ADR 020).

The practice broker settles its own orders -- a fill, a buying-power cancel, a
DAY expiry -- with no IBKR callback to carry the news, so it tells the
execution telemetry watch itself. Import failures are logged and swallowed:
telemetry is a reader of the venue, never a gate on it.

It also frees the order's in-flight commitment (``execution.inflight``) once
the order is resolved, the way the IBKR callbacks do
(``execution/telemetry_handlers.py``). Without that, every resting practice
SELL that filled kept its shares counted as "already sent", and the last
shares could not be sold or flattened until a restart (QA R7, 2026-09-22).
An order an unwind or reset erased is resolved too (``release_commitments``).

The practice broker answers a place or a replace inside the send, so that
answer is the venue's acknowledgment: ``note_answer`` records it on the
execution's own watch. The broker's notice of a fill at placement ran before
that watch existed, and a resting order had no notice at all, so the
execution door's acknowledgment wait found nothing and every Paper and Sim
order waited the full ``EXECUTION_ACK_WAIT_SEC`` (5 s) before the ticket
unlocked (operator report, 2026-09-24: 21 of 23 Paper orders answered in
5.1 s while their fills landed in under 150 ms).

Every close after that answer -- a resting fill, a cancel, an expiry, a
bracket's exits -- also ends the order's execution rows (``close_rows``): no
IBKR callback will.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Iterable

from constants_practice import PRACTICE_ORDER_STATUS_EXPIRED

logger = logging.getLogger(__name__)

#: Statuses after which a practice order holds no shares.
_RESOLVED = frozenset({"Filled", "Cancelled", "ApiCancelled", "Inactive", PRACTICE_ORDER_STATUS_EXPIRED})


def release_commitment(order_id: int, row: dict[str, Any]) -> bool:
    """Free the commitment this practice order holds; True when one was freed.

    Practice ids restart at 1 per venue and per reset, so the order id alone
    could name another venue's commitment: the venue (a practice row's own), the
    symbol and the side must match too.
    """
    try:
        from execution import inflight
    except Exception:
        logger.exception("PRACTICE: execution.inflight unavailable -- commitment for %s kept", order_id)
        return False
    oid = int(order_id)
    symbol = str(row.get("symbol") or "").strip().upper()
    side = str(row.get("side") or "").strip().upper()
    # A short entry is held as SHORT, never SELL (ADR 048): a SELL row may hold either.
    sides = {side, inflight.SHORT} if side == "SELL" else {side}
    venue = row.get("venue")
    for held in inflight.snapshot(all_venues=True):
        if held.get("order_id") != oid:
            continue
        if venue and held.get("venue") != venue:
            continue
        if symbol and held.get("symbol") != symbol:
            continue
        if side and held.get("side") not in sides:
            continue
        return inflight.release_execution(str(held.get("execution_id")))
    return False


def release_commitments(rows: Iterable[dict[str, Any]]) -> int:
    """Free the commitments of orders that no longer exist (an unwind, a reset); returns how many."""
    freed = 0
    for row in rows:
        try:
            oid = int(row.get("order_id"))
        except (TypeError, ValueError):
            continue
        freed += int(release_commitment(oid, row))
    return freed


def answer_facts(row: dict[str, Any]) -> dict[str, Any]:
    """What the venue decided about an order it just took, for the send's reply.

    ``status_reason`` / ``status_code`` say why the venue cancelled it at the
    fill (``order_rules.fill_refusal``); both are ``None`` otherwise.
    """
    return {
        "broker_status": row.get("status"),
        "filled_qty": row.get("filled_qty"),
        "remaining_qty": row.get("remaining_qty"),
        "avg_fill_price": row.get("avg_fill_price"),
        "status_reason": row.get("error"),
        "status_code": row.get("reason_code"),
    }


def note_answer(watch: Any, answer: dict[str, Any]) -> None:
    """Record the venue's answer to a place / replace on the execution's watch.

    The answer is the acknowledgment -- stamped when it was given, never
    delayed or invented. An answer without a status records nothing.
    """
    status = str(answer.get("broker_status") or "")
    if not status:
        return
    avg = answer.get("avg_fill_price")
    watch.note_status(
        status,
        filled=float(answer.get("filled_qty") or 0),
        remaining=float(answer.get("remaining_qty") or 0),
        average_fill_price=float(avg) if avg else None,
        perm_id=int(watch.order_id),
        callback_perf_ns=time.perf_counter_ns(),
    )


def notify_watch(order_id: int, row: dict[str, Any]) -> None:
    """Tell the execution telemetry watch what the practice venue decided, and close the order's rows."""
    status = str(row.get("status") or "Submitted")
    if status in _RESOLVED:
        release_commitment(int(order_id), row)
    try:
        from execution import telemetry
    except Exception:
        logger.debug("PRACTICE: telemetry import failed", exc_info=True)
        return
    watch = telemetry.watch_order(int(order_id), venue=row.get("venue"))
    avg = row.get("avg_fill_price")
    watch.note_status(
        status,
        filled=float(row.get("filled_qty") or 0),
        remaining=float(row.get("remaining_qty") or 0),
        average_fill_price=float(avg) if avg else None,
        perm_id=int(order_id),
        callback_perf_ns=time.perf_counter_ns(),
    )
    close_rows(int(order_id), row, filled_ns=watch.filled_ns)


def close_rows(order_id: int, row: dict[str, Any], *, filled_ns: int | None = None) -> None:
    """End the execution rows of an order the practice venue closed, with its outcome.

    No callback follows a practice venue's answer: before this, a resting order
    it later cancelled, expired or filled kept its row ``acked`` until the next
    restart's sweep, which read a cancel as ``failed`` (TNMG order 77, 2026-10-02).
    A row the send path is still writing has no order id yet, and is its own.
    """
    from execution.order_outcome import ledger_close

    venue = row.get("venue") or row.get("mode")
    outcome = ledger_close(row.get("status"), reason_code=row.get("reason_code"), error=row.get("error"))
    if outcome is None or not venue:
        return
    try:
        from execution.store_facts import close_venue_order

        close_venue_order(
            order_id, mode=str(venue), filled_ns=filled_ns if outcome["status"] == "filled" else None,
            **outcome,
        )
    except Exception:
        # Left open, the rows wait for the next restart's sweep -- said in the log, never hidden.
        logger.exception("PRACTICE: execution rows of order %s left open -- the ledger write failed", order_id)
