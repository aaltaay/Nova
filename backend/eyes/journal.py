"""The eyes' journal (ADR 029): one JSON line for everything the setup scanner's
lanes see.

Owner: this module -- the only writer of ``<eyes dir>/journal/YYYY-MM-DD.jsonl``
(``eyes_dir()``: ``NOVA_EYES_DIR``, else ``F:\\Nova\\eyes`` when F: is mounted,
else ``<cache>/eyes``). A file per Eastern date of the wall clock; a line is
``{schema_version, wall_ts, ts, date, source, event, symbol, template, rev,
playing, bot: {level, active, venue}, ...}`` -- ``ts`` / ``date`` are the
moment and session the eyes were looking at (on a replay, the recording's).
``record`` only enqueues (never blocks a loop, ADR 010); one daemon thread
writes. A full queue drops the line and counts it. ``NOVA_EYES_JOURNAL=0``
turns it off. Invalidation: none -- nothing prunes it (retention is the
operator's call). Read by ``tools/eyes_journal.py``, ``eyes/reader.py`` and
``eyes/playback.py`` -- the Sim desk off the live edge draws every setup card
from it as it stood at the playhead.
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

from constants_eyes import (
    EYES_DEFAULT_ROOT_WIN,
    EYES_DIR_ENV,
    EYES_JOURNAL_DIRNAME,
    EYES_JOURNAL_ENV,
    EYES_JOURNAL_FLUSH_SEC,
    EYES_JOURNAL_QUEUE_MAX,
    EYES_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


def eyes_dir() -> Path:
    """``NOVA_EYES_DIR``; else ``F:\\Nova\\eyes`` when F: is mounted; else ``<cache>/eyes``."""
    configured = (os.environ.get(EYES_DIR_ENV) or "").strip()
    if configured:
        return Path(configured)
    if Path("F:/").exists():
        return Path(EYES_DEFAULT_ROOT_WIN)
    from paths import cache_dir

    return Path(cache_dir()) / "eyes"


def journal_dir() -> Path:
    return eyes_dir() / EYES_JOURNAL_DIRNAME


def enabled() -> bool:
    return (os.environ.get(EYES_JOURNAL_ENV) or "1").strip() != "0"


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%Y-%m-%d")


def line(event: dict[str, Any], *, wall_ts: float | None = None) -> str:
    """The journal line for ``event``: stamped, NaN-free JSON."""
    from scanner_wire import wire_safe

    wall = time.time() if wall_ts is None else wall_ts
    row = {"schema_version": EYES_SCHEMA_VERSION, "wall_ts": round(wall, 3), **event}
    return json.dumps(wire_safe(row), default=str, separators=(",", ":"))


class _Writer:
    def __init__(self) -> None:
        self.q: queue.Queue = queue.Queue(maxsize=EYES_JOURNAL_QUEUE_MAX)
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
            self.thread = threading.Thread(target=self._run, name="eyes-journal", daemon=True)
            self.thread.start()

    def _run(self) -> None:
        while True:
            try:
                first = self.q.get(timeout=EYES_JOURNAL_FLUSH_SEC)
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
            by_day.setdefault(_day(wall), []).append(text)
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
            logger.warning("eyes journal: could not write %d line(s): %s", len(batch), exc)


_writer = _Writer()


def record(event: dict[str, Any]) -> None:
    """Queue one observation; never blocks, never raises."""
    if not enabled():
        return
    wall = time.time()
    try:
        text = line(event, wall_ts=wall)
    except (TypeError, ValueError):
        _writer.dropped += 1
        logger.warning("eyes journal: an event could not be serialised (%s)", event.get("event"), exc_info=True)
        return
    try:
        _writer.q.put_nowait((wall, text))
    except queue.Full:
        _writer.dropped += 1
        return
    _writer.start()


def flush(timeout: float = 5.0) -> bool:
    """Wait until every queued line is on disk (tests, shutdown). True when drained."""
    deadline = time.time() + timeout
    while _writer.q.unfinished_tasks and time.time() < deadline:
        time.sleep(0.01)
    return not _writer.q.unfinished_tasks


def status() -> dict[str, Any]:
    return {"enabled": enabled(), "dir": str(journal_dir()), "written": _writer.written, "dropped": _writer.dropped,
            "queued": _writer.q.qsize(), "last_error": _writer.last_error, "last_write_ts": _writer.last_write_ts}


def reset_for_tests() -> None:
    global _writer
    flush(1.0)
    _writer = _Writer()
