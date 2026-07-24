"""IBKR callback telemetry — real ack/fill marks (not local orderId)."""
from __future__ import annotations

import asyncio
import logging
import time
import weakref
from typing import Any

logger = logging.getLogger(__name__)

# Statuses that mean the broker/system has acknowledged the order beyond
# local PendingSubmit assignment. IBKR may skip orderStatus for immediate
# market fills — execDetails is the fallback (see TWS API docs).
_ACK_STATUSES = frozenset({
    "PreSubmitted",
    "Submitted",
    "ApiPending",
    "ApiCancelled",
    "Cancelled",
    "Filled",
    "Inactive",
})

# Broker terminal statuses that unblock wait_ack but must not count as place
# success when there is no fill (Error 10243 fractional cancel).
TERMINAL_REJECT_STATUSES = frozenset({
    "Cancelled",
    "ApiCancelled",
    "Inactive",
})


class OrderWatch:
    """Per-order waiters for first real ack and complete fill."""

    def __init__(
        self,
        order_id: int,
        execution_id: str | None = None,
        *,
        leg_role: str = "single",
        side: str | None = None,
        reference_price: float | None = None,
        reference_source: str | None = None,
        aggregate_eligible: bool = True,
    ) -> None:
        self.order_id = order_id
        self.execution_id = execution_id
        self.leg_role = leg_role
        self.side = side
        self.reference_price = reference_price
        self.reference_source = reference_source
        self.aggregate_eligible = aggregate_eligible
        self.ack_ns: int | None = None
        self.ack_status: str | None = None
        self.filled_ns: int | None = None
        self.fills: list[dict[str, Any]] = []
        self.error_code: int | None = None
        self.error_message: str | None = None
        self._ack_event = asyncio.Event()
        self._fill_event = asyncio.Event()
        self._last_status_filled = 0.0
        self._reconciled_fill_keys: set[tuple[str, str, str]] = set()

    def _persist_ack(self, status: str) -> None:
        if not self.aggregate_eligible or self.ack_ns is None:
            return
        try:
            from execution import store as _store

            _store.mark_ack_by_order_id(
                self.order_id, self.ack_ns, broker_status=status,
                execution_id=self.execution_id,
            )
        except Exception:
            logger.exception(
                "execution.telemetry: failed to persist ack for order %s",
                self.order_id,
            )

    def note_status(
        self,
        status: str,
        *,
        filled: float | None = None,
        remaining: float | None = None,
        average_fill_price: float | None = None,
        callback_wall_ns: int | None = None,
        callback_perf_ns: int | None = None,
    ) -> None:
        callback_perf = callback_perf_ns or time.perf_counter_ns()
        callback_wall = callback_wall_ns or time.time_ns()
        if status in _ACK_STATUSES and self.ack_ns is None:
            self.ack_ns = callback_perf
            self.ack_status = status
            self._ack_event.set()
            self._persist_ack(status)
        cumulative = float(filled or 0)
        complete = status == "Filled"
        if (
            self.execution_id
            and cumulative > self._last_status_filled
        ):
            from execution import evidence_store

            evidence_store.record_fill(
                execution_id=self.execution_id,
                order_id=self.order_id,
                provenance="orderStatus",
                complete=complete,
                callback_wall_ns=callback_wall,
                callback_perf_ns=callback_perf,
                cumulative_shares=cumulative,
                remaining_qty=remaining,
                average_fill_price=average_fill_price,
                broker_status=status,
                leg_role=self.leg_role,
                side=self.side,
                reference_price=self.reference_price,
                reference_source=self.reference_source,
                aggregate_eligible=self.aggregate_eligible,
            )
            self._last_status_filled = cumulative
        if complete and self.filled_ns is None:
            self.filled_ns = callback_perf
            self._fill_event.set()

    def note_execution(
        self,
        *,
        avg_price: float | None = None,
        price: float | None = None,
        shares: float | None = None,
        cumulative_shares: float | None = None,
        remaining: float | None = None,
        exchange_time: Any = None,
        complete: bool = False,
        callback_wall_ns: int | None = None,
        callback_perf_ns: int | None = None,
    ) -> None:
        # execDetails often arrives when orderStatus is skipped for fast fills.
        callback_perf = callback_perf_ns or time.perf_counter_ns()
        callback_wall = callback_wall_ns or time.time_ns()
        if self.ack_ns is None:
            self.ack_ns = callback_perf
            self.ack_status = self.ack_status or "ExecDetails"
            self._ack_event.set()
            self._persist_ack(self.ack_status)
        if not hasattr(self, "fills") or self.fills is None:
            self.fills = []
        self.fills.append(
            {"avg_price": avg_price, "shares": shares, "ns": callback_perf}
        )
        if self.execution_id:
            from execution import evidence_store

            evidence_store.record_fill(
                execution_id=self.execution_id,
                order_id=self.order_id,
                provenance="execDetails",
                complete=complete,
                exchange_time=exchange_time,
                callback_wall_ns=callback_wall,
                callback_perf_ns=callback_perf,
                price=price,
                shares=shares,
                cumulative_shares=cumulative_shares,
                remaining_qty=remaining,
                average_fill_price=avg_price,
                broker_status=self.ack_status,
                leg_role=self.leg_role,
                side=self.side,
                reference_price=self.reference_price,
                reference_source=self.reference_source,
                aggregate_eligible=self.aggregate_eligible,
            )

    def note_filled(self) -> None:
        if self.filled_ns is None:
            self.filled_ns = time.perf_counter_ns()
        self._fill_event.set()
        if self.ack_ns is None:
            self.ack_ns = self.filled_ns
            self.ack_status = "Filled"
            self._ack_event.set()
        try:
            from execution import store as _store

            if self.aggregate_eligible:
                _store.mark_filled_by_order_id(
                    self.order_id, self.filled_ns,
                    execution_id=self.execution_id,
                )
        except Exception:
            logger.exception(
                "execution.telemetry: failed to persist fill for order %s",
                self.order_id,
            )

    def note_error(self, error_code: int, error_message: str) -> None:
        """Record the first IBKR errorEvent for this order (e.g. Error 10243)."""
        if self.error_code is None:
            try:
                self.error_code = int(error_code)
            except (TypeError, ValueError):
                self.error_code = None
            self.error_message = str(error_message or "").strip() or None

    def has_fill(self) -> bool:
        return self.filled_ns is not None or bool(self.fills)

    async def wait_ack(self, timeout_sec: float) -> bool:
        if self.ack_ns is not None:
            return True
        try:
            await asyncio.wait_for(self._ack_event.wait(), timeout=timeout_sec)
            return True
        except asyncio.TimeoutError:
            return False

    async def wait_fill(self, timeout_sec: float) -> bool:
        if self.filled_ns is not None:
            return True
        try:
            await asyncio.wait_for(self._fill_event.wait(), timeout=timeout_sec)
            return True
        except asyncio.TimeoutError:
            return False


_watches: dict[int, OrderWatch] = {}
_wired_instances: weakref.WeakSet = weakref.WeakSet()


def watch_order(
    order_id: int,
    execution_id: str | None = None,
    *,
    fresh: bool = False,
    leg_role: str = "single",
    side: str | None = None,
    reference_price: float | None = None,
    reference_source: str | None = None,
    aggregate_eligible: bool = True,
) -> OrderWatch:
    w = _watches.get(order_id)
    if w is None or fresh or (
        execution_id is not None and w.execution_id != execution_id
    ):
        w = OrderWatch(
            order_id, execution_id, leg_role=leg_role, side=side,
            reference_price=reference_price,
            reference_source=reference_source,
            aggregate_eligible=aggregate_eligible,
        )
        _watches[order_id] = w
    elif execution_id is not None and w.execution_id is None:
        w.execution_id = execution_id
    return w


def drop_watch(order_id: int) -> None:
    _watches.pop(order_id, None)


def ensure_handlers(ib) -> None:
    """Wire IB events once per IB instance. Safe across reconnect replacement."""
    if ib is None or ib in _wired_instances:
        return
    try:
        ib.orderStatusEvent += _on_order_status
        ib.execDetailsEvent += _on_exec_details
        if hasattr(ib, "errorEvent"):
            ib.errorEvent += _on_ib_error
        _wired_instances.add(ib)
        logger.info("execution.telemetry: IBKR order status/exec handlers wired")
    except Exception:
        logger.exception("execution.telemetry: failed to wire IB handlers")


def _on_ib_error(reqId: int, errorCode: int, errorString: str, _contract: Any = None) -> None:
    try:
        oid = int(reqId)
    except (TypeError, ValueError):
        return
    w = _watches.get(oid)
    if w is None:
        return
    try:
        w.note_error(int(errorCode), str(errorString or ""))
    except Exception:
        logger.exception("execution.telemetry: errorEvent handler error")


def _on_order_status(trade) -> None:
    try:
        oid = int(trade.order.orderId)
        status = str(trade.orderStatus.status or "")
        w = _watches.get(oid)
        if w is None:
            return
        # Deduplicate: OrderWatch only records first ack / first fill.
        callback_perf = time.perf_counter_ns()
        callback_wall = time.time_ns()
        order_status = trade.orderStatus
        w.note_status(
            status,
            filled=_float_or_none(getattr(order_status, "filled", None)),
            remaining=_float_or_none(getattr(order_status, "remaining", None)),
            average_fill_price=_float_or_none(
                getattr(order_status, "avgFillPrice", None)
            ),
            callback_perf_ns=callback_perf,
            callback_wall_ns=callback_wall,
        )
        if status == "Filled":
            w.note_filled()
    except Exception:
        logger.exception("execution.telemetry: orderStatus handler error")


def _on_exec_details(trade, fill) -> None:
    try:
        oid = int(trade.order.orderId)
        w = _watches.get(oid)
        if w is None:
            return
        execution = fill.execution
        order_status = trade.orderStatus
        remaining = _float_or_none(getattr(trade.orderStatus, "remaining", None))
        cumulative = _float_or_none(getattr(order_status, "filled", None))
        requested = _float_or_none(
            getattr(getattr(trade, "order", None), "totalQuantity", None)
        )
        complete = (
            (
                cumulative is not None
                and requested is not None
                and requested > 0
                and cumulative >= requested
            )
            or str(trade.orderStatus.status) == "Filled"
        )
        w.note_execution(
            avg_price=_float_or_none(getattr(execution, "avgPrice", None)),
            price=_float_or_none(getattr(execution, "price", None)),
            shares=_float_or_none(getattr(execution, "shares", None)),
            cumulative_shares=cumulative,
            remaining=remaining,
            exchange_time=getattr(execution, "time", None),
            complete=complete,
            callback_perf_ns=time.perf_counter_ns(),
            callback_wall_ns=time.time_ns(),
        )
        if complete:
            w.note_filled()
    except Exception:
        logger.exception("execution.telemetry: execDetails handler error")


def note_reconciliation_fill(fill: Any, *, complete: bool = True) -> bool:
    """Persist evidence from an existing poll/cache read without issuing requests."""
    execution = getattr(fill, "execution", None)
    oid = int(getattr(execution, "orderId", 0) or 0)
    watch = _watches.get(oid)
    if oid <= 0 or watch is None or watch.execution_id is None:
        return False
    from execution.reconciliation import record_reconciliation_fill

    return record_reconciliation_fill(fill, watch, complete=complete)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def reset_for_tests() -> None:
    _watches.clear()
    _wired_instances.clear()
