"""IBKR callback telemetry — real ack/fill marks (not local orderId)."""
from __future__ import annotations

import asyncio
import logging
import time
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

    def __init__(self, order_id: int) -> None:
        self.order_id = order_id
        self.ack_ns: int | None = None
        self.ack_status: str | None = None
        self.filled_ns: int | None = None
        self.fills: list[dict[str, Any]] = []
        self.error_code: int | None = None
        self.error_message: str | None = None
        self._ack_event = asyncio.Event()
        self._fill_event = asyncio.Event()

    def note_status(self, status: str) -> None:
        if status in _ACK_STATUSES and self.ack_ns is None:
            self.ack_ns = time.perf_counter_ns()
            self.ack_status = status
            self._ack_event.set()
            try:
                from execution import store as _store

                _store.mark_ack_by_order_id(
                    self.order_id, self.ack_ns, broker_status=status,
                )
            except Exception:
                logger.exception(
                    "execution.telemetry: failed to persist ack for order %s",
                    self.order_id,
                )
        if status == "Filled" and self.filled_ns is None:
            self.filled_ns = time.perf_counter_ns()
            self._fill_event.set()

    def note_execution(self, avg_price: float | None = None, shares: float | None = None) -> None:
        # execDetails often arrives when orderStatus is skipped for fast fills.
        if self.ack_ns is None:
            self.ack_ns = time.perf_counter_ns()
            self.ack_status = self.ack_status or "ExecDetails"
            self._ack_event.set()
            try:
                from execution import store as _store

                _store.mark_ack_by_order_id(
                    self.order_id, self.ack_ns, broker_status=self.ack_status,
                )
            except Exception:
                logger.exception(
                    "execution.telemetry: failed to persist ack for order %s",
                    self.order_id,
                )
        if not hasattr(self, "fills") or self.fills is None:
            self.fills = []
        self.fills.append(
            {"avg_price": avg_price, "shares": shares, "ns": time.perf_counter_ns()}
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

            _store.mark_filled_by_order_id(self.order_id, self.filled_ns)
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
_handlers_wired: bool = False


def watch_order(order_id: int) -> OrderWatch:
    w = _watches.get(order_id)
    if w is None:
        w = OrderWatch(order_id)
        _watches[order_id] = w
    return w


def drop_watch(order_id: int) -> None:
    _watches.pop(order_id, None)


def ensure_handlers(ib) -> None:
    """Wire IB events once per process. Safe to call repeatedly."""
    global _handlers_wired
    if ib is None or _handlers_wired:
        return
    try:
        ib.orderStatusEvent += _on_order_status
        ib.execDetailsEvent += _on_exec_details
        if hasattr(ib, "errorEvent"):
            ib.errorEvent += _on_ib_error
        _handlers_wired = True
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
        w.note_status(status)
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
        avg = None
        shares = None
        try:
            avg = float(fill.execution.avgPrice)
            shares = float(fill.execution.shares)
        except (TypeError, ValueError, AttributeError) as exc:
            logger.debug(
                "execution.telemetry: fill price/size parse skipped: %s", exc,
            )
        w.note_execution(avg_price=avg, shares=shares)
        remaining = float(getattr(trade.orderStatus, "remaining", 1) or 0)
        if remaining <= 0 or str(trade.orderStatus.status) == "Filled":
            w.note_filled()
    except Exception:
        logger.exception("execution.telemetry: execDetails handler error")


def reset_for_tests() -> None:
    global _handlers_wired
    _watches.clear()
    _handlers_wired = False
