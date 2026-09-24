"""The L2 tape archive writer: a bounded queue one thread drains in batches.

maintainer: one-concern a lost print is counted and stated, and never stops the writer

Prints arrive on the IB loop (``tape_recording.dispatch``), which never waits
on disk: ``submit`` only enqueues. One daemon thread takes up to
``TAPE_RECORD_BATCH_MAX`` prints at a time and writes them in one transaction
(``write_many``), or one by one (``write``).

A print is lost in one of two ways, and each is stated rather than hidden:
the backlog is full (``backlog_full``: ``submit`` sheds the print) or a write
raised (``write_failed``: that batch is gone). Consecutive losses of one cause
are one **loss episode** ``{cause, since, until, dropped, symbols,
first_print_ts, last_print_ts, detail}``. It ends (``until``) at the next print
accepted (backlog) or written (write), and the sink keeps taking prints
throughout. ``status()["error"]`` states an episode still open or one that
ended within ``TAPE_RECORD_LOSS_RECENT_SEC``; ``losses`` keeps the last
``TAPE_RECORD_LOSS_KEEP``.

Until 2026-09-24 the first full backlog latched the sink: it shed every later
print until the process restarted. The Paper practice matcher reads resting
orders' prints from this archive, so it went blind for the rest of the
morning (APUS: a SELL limit 50 cents under the market rested unfilled).

``written_through(now)`` is the time the archive is complete through: every
accepted print stamped earlier has been written or counted lost. The Paper
matcher reads no further, so a print the writer reaches late is still read.
"""
from __future__ import annotations

import logging
import math
import time
from collections import deque
from datetime import datetime
from queue import Empty, Full, Queue
from threading import Lock, Thread
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping
from zoneinfo import ZoneInfo

from ibkr.constants_tape_recording import (
    TAPE_RECORD_BATCH_MAX,
    TAPE_RECORD_LOSS_KEEP,
    TAPE_RECORD_LOSS_RECENT_SEC,
    TAPE_RECORD_LOSS_SYMBOLS,
    TAPE_RECORD_PENDING,
    TAPE_RECORD_POLL_SEC,
    TAPE_RECORD_SHUTDOWN_SEC,
)

logger = logging.getLogger(__name__)

LOSS_BACKLOG_FULL = "backlog_full"
LOSS_WRITE_FAILED = "write_failed"
ET = ZoneInfo("America/New_York")


def _print_ts(row: Mapping[str, Any]) -> float:
    for key in ("ts", "receive_ts"):
        try:
            value = float(row.get(key))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            return value
    return time.time()


def _clock(ts: float | None) -> str:
    return datetime.fromtimestamp(float(ts), ET).strftime("%H:%M:%S") if ts is not None else "?"


def loss_statement(episode: Mapping[str, Any]) -> str:
    """One loss episode in plain words, for ``error``, logs and diagnostics."""
    what = "backlog full" if episode.get("cause") == LOSS_BACKLOG_FULL else "write failed"
    until = episode.get("until")
    when = (f"since {_clock(episode.get('since'))} ET" if until is None
            else f"{_clock(episode.get('since'))}-{_clock(until)} ET")
    symbols = ", ".join(episode.get("symbols") or [])
    text = f"L2 tape {what} {when}: {episode.get('dropped', 0)} print(s) lost"
    if symbols:
        text += f" ({symbols})"
    if episode.get("cause") == LOSS_WRITE_FAILED and episode.get("detail"):
        text += f": {episode['detail']}"
    return text + ("; still losing prints" if until is None else "; writing again")


class Sink:
    """One lazy daemon per sink; a loss is counted and stated, and the sink keeps going."""

    def __init__(
        self,
        write: Callable[[Mapping[str, Any]], None],
        capacity: int = TAPE_RECORD_PENDING,
        *,
        write_many: Callable[[list[Mapping[str, Any]]], None] | None = None,
        batch_max: int = TAPE_RECORD_BATCH_MAX,
    ) -> None:
        self.write = write
        self.write_many = write_many
        self.batch_max = max(1, int(batch_max))
        self.queue: Queue = Queue(maxsize=capacity)
        self.lock = Lock()
        self.thread: Thread | None = None
        self.error: str | None = None  # not a loss: the shutdown that timed out
        self.written = 0
        self.dropped = 0
        self.closed = False
        self.losses: deque[dict[str, Any]] = deque(maxlen=TAPE_RECORD_LOSS_KEEP)
        self._open: dict[str, dict[str, Any]] = {}
        # ``ts`` of every accepted print not yet written or lost, in queue order.
        self._unwritten: deque[float] = deque()

    # ----------------------------------------------------------------- ingress
    def submit(self, payload: Mapping[str, Any]) -> bool:
        """Enqueue one print without waiting; False when shed (full) or closed."""
        row = MappingProxyType(dict(payload))
        with self.lock:
            if self.closed:
                return False
            if self.thread is None:
                self.thread = Thread(target=self._run, name="l2-tape-writer", daemon=True)
                self.thread.start()
            try:
                self.queue.put_nowait(row)
            except Full:
                started = self._lose_locked([row], LOSS_BACKLOG_FULL, "backlog full")
                ended = None
            else:
                self._unwritten.append(_print_ts(row))
                started, ended = None, self._end_locked(LOSS_BACKLOG_FULL)
        if started is not None:
            logger.warning("%s -- the writer keeps taking prints once it has room", loss_statement(started))
        if ended is not None:
            logger.warning(loss_statement(ended))
        return started is None

    # ------------------------------------------------------------------ worker
    def _run(self) -> None:
        while True:
            try:
                first = self.queue.get(timeout=TAPE_RECORD_POLL_SEC)
            except Empty:
                if self.closed:
                    return
                continue
            batch = [first]
            while len(batch) < self.batch_max:
                try:
                    batch.append(self.queue.get_nowait())
                except Empty:
                    break
            try:
                groups = [batch] if self.write_many is not None else [[row] for row in batch]
                for group in groups:
                    self._write_group(group)
            finally:
                for _ in batch:
                    self.queue.task_done()

    def _write_group(self, group: list[Mapping[str, Any]]) -> None:
        try:
            if self.write_many is not None:
                self.write_many(group)
            else:
                self.write(group[0])
        except Exception as exc:
            with self.lock:
                started = self._lose_locked(group, LOSS_WRITE_FAILED, f"{type(exc).__name__}: {exc}")
                self._pop_unwritten_locked(len(group))
            if started is not None:
                logger.exception("%s -- the writer keeps going", loss_statement(started))
            else:
                logger.debug("L2 tape: another %d print(s) lost to a failed write", len(group))
            return
        with self.lock:
            self.written += len(group)
            self._pop_unwritten_locked(len(group))
            ended = self._end_locked(LOSS_WRITE_FAILED)
        if ended is not None:
            logger.warning(loss_statement(ended))

    # ------------------------------------------------------------ bookkeeping
    def _lose_locked(self, rows: Iterable[Mapping[str, Any]], cause: str, detail: str) -> dict[str, Any] | None:
        """Count ``rows`` lost; returns a copy of the episode when this loss opened one."""
        rows = list(rows)
        self.dropped += len(rows)
        episode = self._open.get(cause)
        opened = episode is None
        if episode is None:
            episode = {"cause": cause, "since": time.time(), "until": None, "dropped": 0, "symbols": [],
                       "first_print_ts": _print_ts(rows[0]), "last_print_ts": None, "detail": detail}
            self._open[cause] = episode
            self.losses.append(episode)
        episode["dropped"] += len(rows)
        episode["last_print_ts"] = _print_ts(rows[-1])
        episode["detail"] = detail
        for row in rows:
            sym = row.get("symbol")
            if sym and sym not in episode["symbols"] and len(episode["symbols"]) < TAPE_RECORD_LOSS_SYMBOLS:
                episode["symbols"].append(sym)
        return dict(episode, symbols=list(episode["symbols"])) if opened else None

    def _end_locked(self, cause: str) -> dict[str, Any] | None:
        episode = self._open.pop(cause, None)
        if episode is None:
            return None
        episode["until"] = time.time()
        return dict(episode, symbols=list(episode["symbols"]))

    def _pop_unwritten_locked(self, count: int) -> None:
        for _ in range(min(count, len(self._unwritten))):
            self._unwritten.popleft()

    # ------------------------------------------------------------------- reads
    def written_through(self, now: float | None = None) -> float:
        """Every accepted print stamped before this is written or counted lost."""
        ts = time.time() if now is None else float(now)
        with self.lock:
            oldest = min(self._unwritten) if self._unwritten else None
        # A print stamped exactly ``oldest`` may share its second with ones
        # already written; stop just short so the next read takes all of them.
        return ts if oldest is None else min(ts, math.nextafter(oldest, -math.inf))

    def status(self, now: float | None = None) -> dict[str, Any]:
        ts = time.time() if now is None else float(now)
        with self.lock:
            losses = [dict(ep, symbols=list(ep["symbols"])) for ep in self.losses]
            out = {
                "error": self.error,
                "pending": self.queue.qsize(),
                "written": self.written,
                "dropped": self.dropped,
                "losing": bool(self._open),
                "losses": losses,
            }
        if out["error"] is None:
            recent = [ep for ep in losses
                      if ep["until"] is None or ts - float(ep["until"]) <= TAPE_RECORD_LOSS_RECENT_SEC]
            if recent:
                out["error"] = loss_statement(recent[-1])
        return out

    def close(self) -> None:
        """Close ingress and drain accepted rows, with bounded shutdown latency."""
        with self.lock:
            self.closed = True
        if self.thread is not None:
            self.thread.join(TAPE_RECORD_SHUTDOWN_SEC)
            if self.thread.is_alive():
                with self.lock:
                    self.error = "L2 tape shutdown timed out; accepted rows may be incomplete"
                logger.error(self.error)
