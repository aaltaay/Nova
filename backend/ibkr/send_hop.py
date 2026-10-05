"""An order send from the socket loop to the IB loop: awaited, and sent once or provably never (#725).

maintainer: one-concern the exactly-once-or-never hand-off of an order send to the IB loop

The execution door runs on the socket loop, and every ``ib.*`` call runs on the IB loop (ADR 010).
``ibkr.orders`` reached it with ``call_on_ib``, which blocks the calling thread until the IB loop
has run the call: while the IB loop was busy, every Level 2, Time & Sales and quote socket waited
with the order, for up to 15 s. Its timeout also left one question open -- did the order go out?
``client_bridge.run_coro`` cancels the hop's future, and a send the IB loop had already started
reached IBKR while the caller logged "cancel too late" and recorded a failure.

``send`` awaits the IB loop instead, and settles that question under a lock both loops take:

- the IB loop starts the send only while the caller still waits for it, and marks it running;
- a caller that gives up (its timeout, its deadline, its own cancellation) marks a send that has
  not started abandoned, and the IB loop never starts it (``SendNotSent``). A send already running
  reached IBKR, so it is awaited to its end and its result returned;
- ``not_after`` (epoch seconds) is the last moment the send may start: a desk order may not reach
  IBKR more than ``ORDER_MAX_SEND_MS`` after the operator acted (ADR 045). The IB loop refuses to
  start it later (``SendTooLate``), and the caller stops waiting then.

With no IB loop running (tests, before start), or already on it, the send runs inline; the
deadline still applies.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Callable, TypeVar

from constants_ibkr import IBKR_SEND_HOP_TIMEOUT_SEC, IBKR_SEND_RUNNING_GRACE_SEC
from ibkr import loop_supervisor as _supervisor

logger = logging.getLogger(__name__)

T = TypeVar("T")

_WAITING = "waiting"
_RUNNING = "running"
_ABANDONED = "abandoned"


class SendNotSent(Exception):
    """The send never reached IBKR and never will: the IB loop did not start it in time."""

    def __init__(self, message: str, *, waited_sec: float) -> None:
        super().__init__(message)
        self.waited_sec = waited_sec


class SendTooLate(SendNotSent):
    """The send's deadline passed before the IB loop could start it."""

    def __init__(self, late_ms: float, *, waited_sec: float = 0.0) -> None:
        super().__init__(
            f"the send's deadline passed {late_ms:.0f} ms before IBKR's thread could start it",
            waited_sec=waited_sec,
        )
        self.late_ms = late_ms


class SendOutcomeUnknown(Exception):
    """The IB loop started the send and did not finish it within the grace: nobody can tell."""


class _Hop:
    """One send's hand-off. ``state`` moves waiting -> running or waiting -> abandoned, once."""

    __slots__ = ("lock", "state", "late_ms")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state = _WAITING
        self.late_ms: float | None = None

    def start(self, not_after: float | None, now: float) -> bool:
        """On the IB loop: True when the send may run now (it is marked running)."""
        with self.lock:
            if self.state != _WAITING:
                return False
            if not_after is not None and now > not_after:
                self.state = _ABANDONED
                self.late_ms = (now - not_after) * 1000.0
                return False
            self.state = _RUNNING
            return True

    def give_up(self) -> bool:
        """On the caller's loop: True when the send had not started, and now never will."""
        with self.lock:
            if self.state == _WAITING:
                self.state = _ABANDONED
                return True
            return False


def _not_started(hop: _Hop, not_after: float | None, timeout: float, label: str, began: float) -> SendNotSent:
    waited = time.monotonic() - began
    if hop.late_ms is not None:
        return SendTooLate(hop.late_ms, waited_sec=waited)
    now = time.time()
    if not_after is not None and now >= not_after:
        return SendTooLate((now - not_after) * 1000.0, waited_sec=waited)
    return SendNotSent(f"IBKR's thread did not take the {label} within {timeout:.0f} s", waited_sec=waited)


async def send(
    fn: Callable[[], T],
    *,
    not_after: float | None = None,
    timeout: float = IBKR_SEND_HOP_TIMEOUT_SEC,
    label: str = "send",
) -> T:
    """Run ``fn`` on the IB loop and await its result without holding the caller's loop.

    Raises ``SendTooLate`` past ``not_after`` and ``SendNotSent`` when the IB loop did not take it
    within ``timeout`` -- in both cases ``fn`` never ran and never will -- and
    ``SendOutcomeUnknown`` when it started and did not finish within the grace. ``fn``'s own
    exceptions propagate.
    """
    now = time.time()
    if not_after is not None and now > not_after:
        raise SendTooLate((now - not_after) * 1000.0)
    if not _supervisor.is_started() or _supervisor.is_ib_loop() or _supervisor.is_ib_thread():
        return fn()
    loop = _supervisor.get_loop()
    if loop is None:
        raise SendNotSent("IBKR's thread is not running", waited_sec=0.0)
    hop = _Hop()

    async def _on_ib():
        _supervisor.assert_ib_loop()
        if not hop.start(not_after, time.time()):
            return hop  # declined: abandoned by the caller, or past the deadline
        return fn()

    began = time.monotonic()
    future = asyncio.wrap_future(asyncio.run_coroutine_threadsafe(_on_ib(), loop))
    wait = timeout if not_after is None else max(0.0, min(timeout, not_after - time.time()))
    try:
        done, _ = await asyncio.wait({future}, timeout=wait)
    except asyncio.CancelledError:
        if hop.give_up():
            future.cancel()
        else:
            logger.warning("send hop: the %s reached IBKR while its caller was cancelled", label)
        raise
    if not done:
        if hop.give_up():
            future.cancel()
            refusal = _not_started(hop, not_after, timeout, label, began)
            logger.warning("send hop: %s not sent -- %s", label, refusal)
            raise refusal
        # The IB loop started it, so it is reaching IBKR: wait it out, never report it unsent.
        try:
            await asyncio.wait_for(asyncio.shield(future), IBKR_SEND_RUNNING_GRACE_SEC)
        except asyncio.TimeoutError as exc:
            logger.exception(
                "send hop: the %s started on IBKR's thread and has not finished in %.0f s",
                label, IBKR_SEND_RUNNING_GRACE_SEC,
            )
            raise SendOutcomeUnknown(label) from exc
    result = future.result()
    if result is hop:
        refusal = _not_started(hop, not_after, timeout, label, began)
        logger.warning("send hop: %s not sent -- %s", label, refusal)
        raise refusal
    return result
