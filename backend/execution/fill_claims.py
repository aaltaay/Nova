"""Who a fill or an order error belongs to when no live handler claimed it, and the watches it catches up.

- ``unwatched_fill``: a fill no watch holds -- an IBKR liquidation (loud), a fill another client sent
  (logged), or one of Nova's own orders from before a restart, whose row the sweep owns.
- ``unwatched_order_error``: an IBKR error on an order this session knows and no watch holds (logged).
  A data request's error has no order behind it and belongs to its own handler.
- ``catch_up``: the fills a new session read back that no handler heard (``ibkr.session_fills``). A
  watched order's go to its watch as if heard live, so its ledger row, its in-flight shares and its
  fill evidence see them; the rest are claimed as above.

A read-back fill's commission reaches the watch through IBKR's commission event when the session knows
the order. When it does not, no event will ever carry that commission: an arrived report is noted here,
and a missing one marks the watch's commission unknown -- never $0.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from execution import inflight
from ibkr import unclaimed

logger = logging.getLogger(__name__)


def _our_client_id(ib: Any) -> int | None:
    try:
        return int(ib.client.clientId)
    except (AttributeError, TypeError, ValueError):
        return None


def _trades(ib: Any) -> list[Any] | None:
    """The session's trades; None when unreadable (never "no orders")."""
    if ib is None:
        return None
    try:
        return list(ib.trades())
    except Exception:
        logger.exception("execution: IBKR's session trades could not be read")
        return None


def unwatched_fill(ib: Any, fill: Any) -> str:
    """Claim a fill no watch holds: ``liquidation``, ``outside`` (another client) or ``nova``."""
    execution = getattr(fill, "execution", None)
    if unclaimed.is_liquidation(execution):
        unclaimed.note_liquidation(fill)
        return "liquidation"
    ours = _our_client_id(ib)
    try:
        client = int(getattr(execution, "clientId", 0) or 0)
    except (TypeError, ValueError):
        client = 0
    if ours is not None and client != ours:
        unclaimed.note_outside_fill(fill)
        return "outside"
    logger.info(
        "execution: a fill of Nova's order %s that no watch holds (an earlier run's order; the sweep owns its row)",
        getattr(execution, "orderId", None),
    )
    return "nova"


def unwatched_order_error(ib: Any, order_id: int, code: int, message: str) -> bool:
    """Say an IBKR error on an order no watch holds; False when ``order_id`` is no order (a data request)."""
    if ib is None or order_id <= 0:
        return False
    trades = _trades(ib)
    if trades is not None and not any(int(getattr(t.order, "orderId", 0) or 0) == order_id for t in trades):
        return False   # no such order: a data request's error (unreadable trades: said, to be safe)
    unclaimed.note_order_error(order_id, code, message)
    return True


def _report(fill: Any, execution: Any) -> float | None:
    report = getattr(fill, "commissionReport", None)
    report_id = str(getattr(report, "execId", "") or "")
    if not report_id or report_id != str(getattr(execution, "execId", "") or ""):
        return None
    try:
        return float(getattr(report, "commission", None))
    except (TypeError, ValueError):
        return None


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _note_missed(watch: Any, fill: Any, ib: Any) -> None:
    """One read-back fill into ``watch``, as ``telemetry_handlers.on_exec_details`` would have."""
    execution = fill.execution
    perm = int(getattr(execution, "permId", 0) or 0)
    trades = _trades(ib)
    trade = next((t for t in trades or [] if int(getattr(t.order, "permId", 0) or 0) == perm and perm), None)
    cumulative = _num(getattr(execution, "cumQty", None))
    requested = _num(getattr(getattr(trade, "order", None), "totalQuantity", None))
    status = str(getattr(getattr(trade, "orderStatus", None), "status", "") or "")
    complete = status == "Filled" or bool(cumulative and requested and cumulative >= requested)
    # No order for it in this session (or the session's orders unreadable): IBKR's commission event may
    # never carry this fill's, so only an arrived report counts.
    commission = _report(fill, execution) if trade is None else None
    if trade is None and commission is None:
        watch.commission_unknown = True        # set first, so the facts written next carry it
        logger.warning("execution: order %s's read-back fill %s has no commission yet -- unknown, not $0",
                       watch.order_id, getattr(execution, "execId", None))
    watch.note_execution(
        avg_price=_num(getattr(execution, "avgPrice", None)),
        price=_num(getattr(execution, "price", None)),
        shares=_num(getattr(execution, "shares", None)),
        cumulative_shares=cumulative,
        exchange_time=getattr(execution, "time", None),
        complete=complete,
        perm_id=perm or None,
    )
    if commission is not None:
        watch.note_commission(commission)
    if complete:
        watch.note_filled()
        inflight.release_order(watch.order_id, "live")


def catch_up(ib: Any, fills: list[Any], get_watch: Callable[[int], Any]) -> dict[str, int]:
    """Give each fill no handler heard to its watch, or claim it; counts by what each turned out to be."""
    counts = {"caught_up": 0, "liquidation": 0, "outside": 0, "nova": 0}
    for fill in fills:
        execution = getattr(fill, "execution", None)
        try:
            order_id = int(getattr(execution, "orderId", 0) or 0)
            watch = get_watch(order_id) if order_id > 0 else None
            perm = int(getattr(execution, "permId", 0) or 0)
            if watch is not None and (watch.perm_id is None or not perm or watch.perm_id == perm):
                _note_missed(watch, fill, ib)
                counts["caught_up"] += 1
                logger.warning("execution: order %s filled %s while Nova was not listening -- caught up",
                               order_id, getattr(execution, "shares", None))
            else:
                counts[unwatched_fill(ib, fill)] += 1
        except Exception:
            logger.exception("execution: a read-back fill could not be caught up (%s)",
                             getattr(execution, "execId", None))
    return counts
