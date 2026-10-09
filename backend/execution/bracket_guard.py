"""A Live bracket whose leg IBKR refuses before it ever worked is taken back.

maintainer: one-concern a Live bracket is whole at IBKR, or its legs are cancelled and its row says why

``ib.bracketOrder`` transmits all three legs with the stop. A leg IBKR refuses as they transmit (a
price off the tick, a rule on the stop) closed without ever working, and the rest can stay held at
the Gateway, or the entry can work with no stop. Watching each leg from the send on, for
``IBKR_BRACKET_LEG_REFUSAL_WINDOW_SEC``: a leg that goes Cancelled / Inactive before any working
status, with a hard error from IBKR, is a refusal, and the legs still open are cancelled
(``ibkr.order_bracket.take_back``) right after the callback, on the IB loop. A leg that worked and
then closed (an OCA sibling), or closed with no error (a cancel), is not a refusal. If the entry has
filled, nothing is cancelled: the row and the log say the position has no stop.

The row's write goes through ``persist_queue`` (no SQLite on the IB loop, ADR 010); ``execution.
live_send`` checks ``refused`` under ``lock`` before it writes ``acked``, so the two never cross.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from constants_ibkr import IBKR_BRACKET_LEG_REFUSAL_WINDOW_SEC
from execution import inflight, persist_queue, store
from execution.order_watch import TERMINAL_REJECT_STATUSES, WORKING_ACK_STATUSES, _Flag

logger = logging.getLogger(__name__)

REASON = "BRACKET_LEG_REFUSED"
_ROLE_WORDS = {"parent": "entry", "target": "target", "stop": "stop"}


def _closed(watch: Any) -> bool:
    status = watch.latest_status or ""
    return status == "Filled" or status in TERMINAL_REJECT_STATUSES


class BracketGuard:
    """Watches one bracket's legs (``{role: watch}``, roles ``parent`` / ``target`` / ``stop``)."""

    def __init__(self, execution_id: str, legs: dict[str, Any], *, window_sec: float | None = None) -> None:
        self.execution_id = execution_id
        self.legs = {role: watch for role, watch in legs.items() if watch is not None}
        self.lock = threading.Lock()
        self.refused: str | None = None   # the leg IBKR refused; set once its take-back has been sent
        self.error: str | None = None
        self._judged = False
        self._refused_flag = _Flag()   # wakes the send's ack wait the moment a leg is refused
        self._deadline = time.monotonic() + float(
            IBKR_BRACKET_LEG_REFUSAL_WINDOW_SEC if window_sec is None else window_sec
        )
        self._listeners = {role: self._listener(role) for role in self.legs}
        for role, watch in self.legs.items():
            watch.add_status_listener(self._listeners[role])
        try:
            asyncio.get_running_loop().call_later(self._deadline - time.monotonic(), self.close)
        except RuntimeError:  # maintainer: allow-swallow no running loop (tests): the next status past the window closes it
            pass

    def _listener(self, role: str):
        return lambda status: self._on_status(role, status)

    def close(self) -> None:
        for role, watch in self.legs.items():
            watch.remove_status_listener(self._listeners[role])

    def _on_status(self, role: str, status: str) -> None:
        if time.monotonic() > self._deadline:
            self.close()
            return
        watch = self.legs[role]
        if status not in TERMINAL_REJECT_STATUSES or watch.has_fill():
            return
        if any(s in WORKING_ACK_STATUSES for s in watch._status_history[:-1]):
            return  # it worked, then closed: a cancel or an OCA sibling, not a refusal
        try:
            # Judged after this callback: ib_async emits a refusal's error after its Cancelled status.
            asyncio.get_running_loop().call_soon(self._judge, role)
        except RuntimeError:
            self._judge(role)  # no running loop (tests): judge now

    def _judge(self, role: str) -> None:
        """A leg closed before it worked: a refusal when IBKR said why (a hard error), else a cancel."""
        watch = self.legs[role]
        if watch.error_code is None:
            logger.info("execution: bracket %s's %s closed before it worked with no error -- a cancel, not a refusal",
                        self.execution_id, _ROLE_WORDS.get(role, role))
            return
        if self._judged:
            return
        self._judged = True       # on the IB loop only: one leg's refusal takes the bracket back once
        self.close()
        error = self._take_back(role)
        with self.lock:           # the receipt reads both under the lock, never one without the other
            self.refused, self.error = role, error
        self._refused_flag.set()

    async def wait_refused(self) -> bool:
        return await self._refused_flag.wait()

    def _take_back(self, role: str) -> str:
        """Cancel the legs still open (unless the entry filled) and write the row; the words for both."""
        from ibkr.order_bracket import take_back

        watch = self.legs[role]
        error = f"IBKR refused the bracket's {_ROLE_WORDS.get(role, role)} (Error {watch.error_code}: {watch.error_message})"
        entry = self.legs.get("parent")
        if entry is not None and (entry.has_fill() or entry.latest_status == "Filled"):
            error = f"{error}; the entry had filled, so the position has NO STOP -- set one now"
        else:
            open_ids = [int(w.order_id) for w in self.legs.values() if not _closed(w)]
            cancelled, failed = take_back(open_ids) if open_ids else ([], [])
            if failed:
                error = f"{error}; Nova could NOT cancel order(s) {', '.join(map(str, failed))}: cancel them in TWS"
            elif cancelled:
                error = f"{error}; Nova cancelled the rest ({', '.join(map(str, cancelled))})"
            inflight.release_execution(self.execution_id)
        logger.error("execution: bracket %s -- %s", self.execution_id, error)
        self._persist(error)
        return error

    def _persist(self, error: str) -> None:
        execution_id = self.execution_id
        persist_queue.submit(
            f"bracket refusal {execution_id}",
            lambda: store.update_stages(execution_id, status="failed", reason_code=REASON, error=error),
        )
