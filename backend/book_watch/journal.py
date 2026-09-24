"""The book watcher's journal (ADR 033): flags, large pulls and one line per symbol-minute.

Owner: this module -- the only writer of ``<book watch dir>/YYYY-MM-DD.jsonl``
(``NOVA_BOOK_WATCH_DIR``, else ``F:\\Nova\\book_watch`` when F: is mounted, else
``<cache>/book_watch``), a file per Eastern date of the wall clock. A line is
``{schema_version, wall_ts, event: "flag" | "pull" | "minute", symbol, ...}``
in the detector's event shapes. ``record_many`` only enqueues; one daemon thread
writes; a full queue drops and counts. ``NOVA_BOOK_WATCH_JOURNAL=0`` turns it off.
Invalidation: none -- nothing prunes it (like the eyes' journal, retention is
the operator's call). Read by bots and analysis, never by the desk.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from book_watch.constants_book_watch import (
    BOOK_WATCH_DEFAULT_ROOT_WIN,
    BOOK_WATCH_DIR_ENV,
    BOOK_WATCH_JOURNAL_ENV,
    BOOK_WATCH_JOURNAL_FLUSH_SEC,
    BOOK_WATCH_JOURNAL_QUEUE_MAX,
    BOOK_WATCH_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


def journal_dir() -> Path:
    configured = (os.environ.get(BOOK_WATCH_DIR_ENV) or "").strip()
    if configured:
        return Path(configured)
    if Path("F:/").exists():
        return Path(BOOK_WATCH_DEFAULT_ROOT_WIN)
    from paths import cache_dir

    return Path(cache_dir()) / "book_watch"


def enabled() -> bool:
    return (os.environ.get(BOOK_WATCH_JOURNAL_ENV) or "1").strip() != "0"


def line(event: dict[str, Any], *, wall_ts: float) -> str:
    row = {"schema_version": BOOK_WATCH_SCHEMA_VERSION, "wall_ts": round(wall_ts, 3), **event}
    return json.dumps(row, default=str, separators=(",", ":"), allow_nan=False)


class _Writer:
    def __init__(self) -> None:
        self.q: queue.Queue = queue.Queue(maxsize=BOOK_WATCH_JOURNAL_QUEUE_MAX)
        self.thread: threading.Thread | None = None
        self.lock = threading.Lock()
        self.written = 0
        self.dropped = 0
        self.last_error: str | None = None
        self.last_write_ts: float | None = None

    def start(self) -> None:
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return
            self.thread = threading.Thread(target=self._run, name="book-watch-journal", daemon=True)
            self.thread.start()

    def _run(self) -> None:
        while True:
            try:
                first = self.q.get(timeout=BOOK_WATCH_JOURNAL_FLUSH_SEC)
            except queue.Empty:
                continue
            batch = [first]
            while len(batch) < 2000:
                try:
                    batch.append(self.q.get_nowait())
                except queue.Empty:
                    break
            self._write(batch)
            for _ in batch:
                self.q.task_done()

    def _write(self, batch: list[tuple[float, str]]) -> None:
        by_day: dict[str, list[str]] = {}
        for wall, text in batch:
            by_day.setdefault(datetime.fromtimestamp(wall, ET).strftime("%Y-%m-%d"), []).append(text)
        try:
            folder = journal_dir()
            folder.mkdir(parents=True, exist_ok=True)
            for day, texts in by_day.items():
                with (folder / f"{day}.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write("\n".join(texts) + "\n")
            self.written += len(batch)
            self.last_write_ts = time.time()
            self.last_error = None
        except OSError as exc:
            self.dropped += len(batch)
            self.last_error = str(exc)
            logger.warning("book watch journal: could not write %d line(s): %s", len(batch), exc)


_writer = _Writer()


def record_many(events: list[dict[str, Any]]) -> None:
    """Queue the watcher's events; never blocks, never raises."""
    if not enabled() or not events:
        return
    wall = time.time()
    for event in events:
        try:
            text = line(event, wall_ts=wall)
        except (TypeError, ValueError):
            _writer.dropped += 1
            logger.warning("book watch journal: an event could not be serialised (%s)", event.get("event"))
            continue
        try:
            _writer.q.put_nowait((wall, text))
        except queue.Full:
            _writer.dropped += 1
            continue
    _writer.start()


def flush(timeout: float = 5.0) -> bool:
    """Wait until every queued line is on disk (tests, shutdown). True when drained."""
    deadline = time.time() + timeout
    while _writer.q.unfinished_tasks and time.time() < deadline:
        time.sleep(0.01)
    return not _writer.q.unfinished_tasks


def status() -> dict[str, Any]:
    return {"enabled": enabled(), "dir": str(journal_dir()), "written": _writer.written,
            "dropped": _writer.dropped, "queued": _writer.q.qsize(), "last_error": _writer.last_error,
            "last_write_ts": _writer.last_write_ts}


def reset_for_tests() -> None:
    global _writer
    flush(1.0)
    _writer = _Writer()
