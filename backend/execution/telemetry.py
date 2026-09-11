"""IBKR callback telemetry — real ack/fill marks (not local orderId)."""
from __future__ import annotations

import asyncio
import logging
import time
import weakref
from typing import Any, Callable

from execution import telemetry_persist as _persist

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

# Working (non-reject) ack statuses -- a later one upgrades a false Cancelled.
WORKING_ACK_STATUSES = frozenset({
    "PreSubmitted",
    "Submitted",
    "ApiPending",
    "Filled",
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
        self.latest_status: str | None = None
        self.filled_ns: int | None = None
        self.fills: list[dict[str, Any]] = []
        self.error_code: int | None = None
        self.error_message: str | None = None
        self._ack_event = asyncio.Event()
        self._fill_event = asyncio.Event()
        # Called synchronously on the IB loop from note_status, so a verifier
        # awaiting on that same loop can wake on the callback instead of polling.
        self._status_listeners: list[Callable[[str], None]] = []
        self._last_status_filled = 0.0
        self._reconciled_fill_keys: set[tuple[str, str, str]] = set()
        self._status_history: list[str] = []
        self.perm_id: int | None = None
        self.last_filled_qty: float | None = None
        self.last_avg_fill: float | None = None

    def _persist_ack(self, status: str, *, allow_upgrade: bool = False) -> None:
        if not self.aggregate_eligible or self.ack_ns is None:
            return
        _persist.submit_ack(
            self.order_id, self.ack_ns, status, self.execution_id,
            allow_upgrade=allow_upgrade,
        )

    def _remember_facts(
        self,
        *,
        perm_id: int | None = None,
        filled: float | None = None,
        average_fill_price: float | None = None,
    ) -> None:
        if perm_id is not None and int(perm_id) > 0:
            self.perm_id = int(perm_id)
        if filled is not None:
            self.last_filled_qty = float(filled)
        if average_fill_price is not None and float(average_fill_price) != 0.0:
            self.last_avg_fill = float(average_fill_price)

    def _persist_facts(self) -> None:
        if not self.execution_id:
            return
        _persist.submit_facts(
            self.order_id,
            self.execution_id,
            perm_id=self.perm_id,
            filled_qty=self.last_filled_qty,
            avg_fill_price=self.last_avg_fill,
        )

    def note_status(
        self,
        status: str,
        *,
        filled: float | None = None,
        remaining: float | None = None,
        average_fill_price: float | None = None,
        perm_id: int | None = None,
        callback_wall_ns: int | None = None,
        callback_perf_ns: int | None = None,
    ) -> None:
        callback_perf = callback_perf_ns or time.perf_counter_ns()
        callback_wall = callback_wall_ns or time.time_ns()
        self._remember_facts(
            perm_id=perm_id,
            filled=filled,
            average_fill_price=average_fill_price,
        )
        self.latest_status = status
        if status:
            self._status_history.append(status)
            if len(self._status_history) > 16:
                self._status_history = self._status_history[-16:]

        if status in WORKING_ACK_STATUSES:
            # First working ack, or upgrade off a false Cancelled (Error 10349).
            if self.ack_ns is None or (
                self.ack_status in TERMINAL_REJECT_STATUSES
            ):
                upgrade = self.ack_status in TERMINAL_REJECT_STATUSES
                if self.ack_ns is None:
                    self.ack_ns = callback_perf
                self.ack_status = status
                self._ack_event.set()
                self._persist_ack(status, allow_upgrade=upgrade)
                self._persist_facts()
        elif status in _ACK_STATUSES and self.ack_ns is None:
            self.ack_ns = callback_perf
            self.ack_status = status
            self._ack_event.set()
            self._persist_ack(status)
            self._persist_facts()
        cumulative = float(filled or 0)
        complete = status == "Filled"
        if (
            self.execution_id
            and cumulative > self._last_status_filled
        ):
            _persist.submit_fill_evidence(
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
        self._fire_status_listeners(status)

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
        perm_id: int | None = None,
        callback_wall_ns: int | None = None,
        callback_perf_ns: int | None = None,
    ) -> None:
        # execDetails often arrives when orderStatus is skipped for fast fills.
        callback_perf = callback_perf_ns or time.perf_counter_ns()
        callback_wall = callback_wall_ns or time.time_ns()
        self._remember_facts(
            perm_id=perm_id,
            filled=cumulative_shares,
            average_fill_price=avg_price,
        )
        if self.ack_ns is None:
            self.ack_ns = callback_perf
            self.ack_status = self.ack_status or "ExecDetails"
            self._ack_event.set()
            self._persist_ack(self.ack_status)
            self._persist_facts()
        if not hasattr(self, "fills") or self.fills is None:
            self.fills = []
        self.fills.append(
            {"avg_price": avg_price, "shares": shares, "ns": callback_perf}
        )
        if self.execution_id:
            _persist.submit_fill_evidence(
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
        self._persist_facts()

    def note_filled(self) -> None:
        if self.filled_ns is None:
            self.filled_ns = time.perf_counter_ns()
        self._fill_event.set()
        if self.ack_ns is None:
            self.ack_ns = self.filled_ns
            self.ack_status = "Filled"
            self._ack_event.set()
        if self.aggregate_eligible:
            _persist.submit_filled(
                self.order_id, self.filled_ns, self.execution_id,
            )
        self._persist_facts()
        _persist.submit_round_trip(self)

    def note_error(self, error_code: int, error_message: str) -> None:
        """Record the first IBKR errorEvent for this order (e.g. Error 10243)."""
        if self.error_code is None:
            try:
                self.error_code = int(error_code)
            except (TypeError, ValueError):
                self.error_code = None
            self.error_message = str(error_message or "").strip() or None

    def add_status_listener(self, listener: Callable[[str], None]) -> None:
        if listener not in self._status_listeners:
            self._status_listeners.append(listener)

    def remove_status_listener(self, listener: Callable[[str], None]) -> None:
        if listener in self._status_listeners:
            self._status_listeners.remove(listener)

    def _fire_status_listeners(self, status: str) -> None:
        for listener in list(self._status_listeners):
            try:
                listener(status)
            except Exception:
                logger.exception(
                    "execution.telemetry: status listener failed for order %s",
                    self.order_id,
                )

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

        on_err, on_status, on_exec = make_handlers(_watches.get)
        ib.orderStatusEvent += on_status
        ib.execDetailsEvent += on_exec
        if hasattr(ib, "errorEvent"):
            ib.errorEvent += on_err
        _wired_instances.add(ib)
        logger.info("execution.telemetry: IBKR order status/exec handlers wired")
    except Exception:
        logger.exception("execution.telemetry: failed to wire IB handlers")


def note_reconciliation_fill(fill: Any, *, complete: bool = True) -> bool:
    from execution.telemetry_handlers import note_reconciliation_fill as _note

    return _note(fill, _watches.get, complete=complete)


def reset_for_tests() -> None:
    _watches.clear()
    _wired_instances.clear()
    if hasattr(ensure_handlers, "_hopping"):
        ensure_handlers._hopping = False
