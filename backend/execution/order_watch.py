"""One order's watch: what IBKR's (or a practice venue's) callbacks say about it.

Owner: ``OrderWatch`` -- the ack / fill / reject marks of a single order. Where the watches
are kept, by venue, and how IBKR's events reach them is ``execution.telemetry``'s.

IBKR's callbacks run on the IB loop while the order's request waits on the socket loop, so the
ack and the fill wake their waiters through ``_Flag``, which is safe from any thread (#725).
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any, Callable

from execution import telemetry_persist as _persist

logger = logging.getLogger(__name__)

# Broker ack beyond local PendingSubmit. Fast MKT fills may skip orderStatus.
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


def _resolve(future: asyncio.Future) -> None:
    if not future.done():
        future.set_result(True)


class _Flag:
    """A one-way flag set from any thread and awaited on any loop (#725).

    ``asyncio.Event`` is not thread-safe. Set from the IB loop while the order's request waited
    on the socket loop, it woke the waiter only when something else woke that loop, and a set
    landing between the waiter's check and its wait was lost until the ack timed out (5 s).
    """

    __slots__ = ("_lock", "_set", "_waiters")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._set = False
        self._waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Future]] = []

    def is_set(self) -> bool:
        return self._set

    def set(self) -> None:
        with self._lock:
            if self._set:
                return
            self._set = True
            waiters, self._waiters = self._waiters, []
        for loop, future in waiters:
            try:
                loop.call_soon_threadsafe(_resolve, future)
            except RuntimeError:  # maintainer: allow-swallow the waiter's loop is closed: nobody waits there
                pass

    async def wait(self) -> bool:
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._set:
                return True
            future = loop.create_future()
            self._waiters.append((loop, future))
        await future
        return True


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
        self.error_events: list[tuple[int, str]] = []
        self.commission: float | None = None
        self._fill_audit_emitted: bool = False
        self._ack_event = _Flag()
        self._fill_event = _Flag()
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
            # A bracket's exit legs share its row, which is the entry's: an exit's own
            # permId there broke every join on it (TNMG 2026-10-02: the row read the
            # stop leg's 79, not the entry's 77).
            perm_id=self.perm_id if self.aggregate_eligible else None,
            filled_qty=self.last_filled_qty,
            avg_fill_price=self.last_avg_fill,
            commission=self.commission,
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
        self._remember_facts(perm_id=perm_id)
        self.latest_status = status
        if status:
            self._status_history.append(status)
            if len(self._status_history) > 16:
                self._status_history = self._status_history[-16:]

        if status in WORKING_ACK_STATUSES:
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
        from execution.order_outcome import latest_hard_error

        try:
            code = int(error_code)
        except (TypeError, ValueError):
            return
        message = str(error_message or "").strip() or None
        self.error_events.append((code, message or ""))
        hard_code, hard_msg = latest_hard_error(self.error_events)
        self.error_code = hard_code
        self.error_message = hard_msg

    def note_commission(self, commission: float | None) -> None:
        """Sum IBKR CommissionReport dollars. Never invent from avg_cost."""
        try:
            value = float(commission)
        except (TypeError, ValueError):
            return
        if self.commission is None:
            self.commission = value
        else:
            self.commission += value
        self._persist_facts()

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
        return bool(self.fills)

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
