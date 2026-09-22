"""Independent bounded recording sinks for immutable normalized AllLast prints."""

from __future__ import annotations

import logging
import time
from queue import Queue, Full, Empty
from threading import Lock, Thread
from types import MappingProxyType

from ibkr.constants_tape_recording import (
    TAPE_RECORD_PENDING,
    TAPE_RECORD_STALE_SEC,
    TAPE_RECORD_SHUTDOWN_SEC,
    TAPE_RECORD_POLL_SEC,
)

logger = logging.getLogger(__name__)
_last: dict[str, float] = {}
_since: dict[str, float] = {}
_errors: dict[str, str] = {}
dispatch_errors: dict[str, str] = {}


class Sink:
    """One lazy daemon per sink; sticky failure sheds input until explicitly reset."""

    def __init__(self, write, capacity=TAPE_RECORD_PENDING):
        self.write = write
        self.queue = Queue(maxsize=capacity)
        self.lock = Lock()
        self.thread = None
        self.error = None
        self.written = 0
        self.closed = False

    def submit(self, payload) -> bool:
        with self.lock:
            if self.error or self.closed:
                return False
            if self.thread is None:
                self.thread = Thread(target=self._run, name="l2-tape-writer", daemon=True)
                self.thread.start()
            try:
                self.queue.put_nowait(MappingProxyType(dict(payload)))
            except Full:
                self.error = "L2 tape backlog full; prints lost; restart application after recovery"
                logger.exception(self.error)
                return False
            return True

    def _run(self):
        while True:
            try:
                payload = self.queue.get(timeout=TAPE_RECORD_POLL_SEC)
            except Empty:
                if self.closed:
                    return
                continue
            try:
                self.write(payload)
                with self.lock:
                    self.written += 1
            except Exception as exc:
                with self.lock:
                    self.error = f"L2 tape write failed: {exc}"
                logger.exception("L2 tape write failed")
            finally:
                self.queue.task_done()

    def status(self):
        with self.lock:
            return {"error": self.error, "pending": self.queue.qsize(), "written": self.written}

    def close(self):
        """Close ingress and drain accepted rows, with bounded shutdown latency."""
        with self.lock:
            self.closed = True
        if self.thread is not None:
            self.thread.join(TAPE_RECORD_SHUTDOWN_SEC)
            if self.thread.is_alive():
                with self.lock:
                    self.error = "L2 tape shutdown timed out; accepted rows may be incomplete"
                logger.error(self.error)


def _write_l2(payload):
    from l2.tape import persist_print

    persist_print(payload)


l2_sink = Sink(_write_l2)


def dispatch(payload) -> None:
    """No disk I/O or waiting for sink completion on the IB loop."""
    from capture.bridge_ibkr import enqueue_print

    _last[payload["symbol"]] = payload["receive_ts"]
    for name, enqueue in (("capture", enqueue_print), ("l2", _enqueue_l2)):
        try:
            enqueue(payload)
        except Exception:
            logger.exception("IBKR %s recording dispatch failed", name)
            dispatch_errors[name] = f"{name} recording dispatch failed"
        else:
            # A later print that dispatches cleanly clears the sticky error, so
            # one bad print does not mark every recording failed forever (QA C55).
            dispatch_errors.pop(name, None)


def _enqueue_l2(payload):
    from l2 import tape

    if tape.is_watched(payload["symbol"]):
        # Snapshot ownership before enqueue so delayed rows cannot enter a new session.
        l2_sink.submit(
            dict(payload)
            | {
                "session_id": tape.session_id(payload["symbol"]),
                "watch_started": tape.watch_started(payload["symbol"]),
            }
        )


def rejected(symbol: str, error: str) -> None:
    _errors[symbol] = error


def subscribed(symbol: str) -> None:
    _errors.pop(symbol, None)
    _last.pop(symbol, None)
    _since[symbol] = time.time()


def producer_status(symbol: str) -> dict:
    last = _last.get(symbol)
    error = _errors.get(symbol)
    stale = time.time() - (last or _since.get(symbol, time.time())) > TAPE_RECORD_STALE_SEC
    state = "error" if error else "stale" if stale else "waiting" if last is None else "receiving"
    return {"state": state, "healthy": state == "receiving", "last_print_ts": last, "error": error}
