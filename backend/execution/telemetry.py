"""IBKR callback telemetry — real ack/fill marks (not local orderId)."""
from __future__ import annotations

import logging
import weakref
from typing import Any

from constants_sim import DESK_PRACTICE_VENUES
from execution.order_watch import (  # noqa: F401 -- the watch and its status sets, kept importable from here
    TERMINAL_REJECT_STATUSES,
    WORKING_ACK_STATUSES,
    OrderWatch,
)

logger = logging.getLogger(__name__)

#: IBKR's orders, by the id IBKR's callbacks name (the Live venue).
_watches: dict[int, OrderWatch] = {}
#: A practice venue's orders. Practice ids restart at 1 per venue, so the id alone would
#: name another venue's order (or one of IBKR's): the key is (venue, id).
_practice_watches: dict[tuple[str, int], OrderWatch] = {}
_wired_instances: weakref.WeakSet = weakref.WeakSet()

_PRACTICE_VENUES = DESK_PRACTICE_VENUES


def _book(venue: str | None) -> dict:
    """The watches of ``venue`` -- a practice venue's own, else IBKR's."""
    return _watches if venue not in _PRACTICE_VENUES else _practice_watches


def _key(order_id: int, venue: str | None):
    return order_id if venue not in _PRACTICE_VENUES else (venue, order_id)


def watch_order(
    order_id: int,
    execution_id: str | None = None,
    *,
    venue: str | None = None,
    fresh: bool = False,
    leg_role: str = "single",
    side: str | None = None,
    reference_price: float | None = None,
    reference_source: str | None = None,
    aggregate_eligible: bool = True,
) -> OrderWatch:
    book, key = _book(venue), _key(order_id, venue)
    w = book.get(key)
    if w is None or fresh or (
        execution_id is not None and w.execution_id != execution_id
    ):
        w = OrderWatch(
            order_id, execution_id, leg_role=leg_role, side=side,
            reference_price=reference_price,
            reference_source=reference_source,
            aggregate_eligible=aggregate_eligible,
        )
        book[key] = w
    elif execution_id is not None and w.execution_id is None:
        w.execution_id = execution_id
    return w


def drop_watch(order_id: int, venue: str | None = None) -> None:
    _book(venue).pop(_key(order_id, venue), None)


def ensure_handlers(ib) -> None:
    """Wire IB events once per IB instance. Safe across reconnect replacement."""
    if ib is None or ib in _wired_instances:
        return
    from ibkr.loop_supervisor import call_on_ib, is_ib_loop, is_ib_thread

    if not (is_ib_loop() or is_ib_thread()):
        if getattr(ensure_handlers, "_hopping", False):
            # call_on_ib ran inline (tests / no IB loop) -- wire here.
            pass
        else:
            ensure_handlers._hopping = True
            try:
                call_on_ib(lambda: ensure_handlers(ib), 5.0, label="ensure_handlers")
            finally:
                ensure_handlers._hopping = False
            if ib in _wired_instances:
                return
            if is_ib_loop() or is_ib_thread():
                return
    try:
        from execution.telemetry_handlers import make_handlers

        on_err, on_status, on_exec, on_comm = make_handlers(_watches.get)
        ib.orderStatusEvent += on_status
        ib.execDetailsEvent += on_exec
        if hasattr(ib, "errorEvent"):
            ib.errorEvent += on_err
        if hasattr(ib, "commissionReportEvent"):
            ib.commissionReportEvent += on_comm
        _wired_instances.add(ib)
        logger.info("execution.telemetry: IBKR order status/exec handlers wired")
    except Exception:
        logger.exception("execution.telemetry: failed to wire IB handlers")


async def wire_for_send(ib) -> str | None:
    """Wire IBKR's order events before a send, awaiting the IB loop (#725): the refusal, or None.

    READY wires them on the IB loop (``ibkr.session_usable``), so on the desk this returns at once.
    ``ensure_handlers`` from the order path hopped with ``call_on_ib``, which blocked the socket
    loop -- every socket with it -- for as long as the IB loop was busy, up to 5 s.
    """
    if ib is None or ib in _wired_instances:
        return None
    from constants_ibkr import IBKR_ORDER_EVENTS_UNWIRED_MSG, IBKR_ORDER_EVENTS_WIRE_TIMEOUT_SEC
    from ibkr.loop_supervisor import is_ib_loop, is_ib_thread, is_started, on_ib

    if not is_started() or is_ib_loop() or is_ib_thread():
        ensure_handlers(ib)
        return None

    async def _wire() -> None:
        ensure_handlers(ib)

    try:
        await on_ib(_wire(), IBKR_ORDER_EVENTS_WIRE_TIMEOUT_SEC, label="ensure_handlers")
    except TimeoutError:
        logger.warning("execution.telemetry: IBKR's thread did not wire the order events in time")
        return IBKR_ORDER_EVENTS_UNWIRED_MSG.format(sec=IBKR_ORDER_EVENTS_WIRE_TIMEOUT_SEC)
    return None


def note_reconciliation_fill(fill: Any, *, complete: bool = True) -> bool:
    from execution.telemetry_handlers import note_reconciliation_fill as _note

    return _note(fill, _watches.get, complete=complete)


def reset_for_tests() -> None:
    _watches.clear()
    _practice_watches.clear()
    _wired_instances.clear()
    if hasattr(ensure_handlers, "_hopping"):
        ensure_handlers._hopping = False
