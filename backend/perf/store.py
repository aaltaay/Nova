"""Performance files on disk (ADR 026) -- one writer thread, never a loop.

Persisted state (``persisted-state.mdc``):

- **Owner:** this module writes ``<cache_dir>/perf/YYYY-MM-DD.jsonl`` (Eastern
  date of each line's ``ts``) and ``<cache_dir>/perf/stalls/<id>.json``;
  ``tools/perf_report.py`` reads them.
- **Invalidation:** each Eastern day starts a new file; files older than
  ``PERF_RETENTION_DAYS`` are removed at start and at each day rollover. A day
  file stops taking ``sample`` and ``client`` lines past
  ``PERF_DAY_FILE_MAX_MB`` (stall lines still go in).
- **schema_version:** on every line and every stall report. A reader skips and
  counts an unknown version.

Producers call :meth:`PerfStore.put` / :meth:`PerfStore.put_stall`, which
only enqueue; a full queue drops the line and counts it.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from constants_perf import (
    PERF_DAY_FILE_MAX_MB,
    PERF_DIR_NAME,
    PERF_RETENTION_DAYS,
    PERF_STALL_FILES_PER_HOUR,
    PERF_STALLS_DIR_NAME,
    PERF_WRITE_QUEUE_MAX,
)

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_BATCH_MAX = 500


def et_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, _ET).strftime("%Y-%m-%d")


def default_dir() -> Path:
    from paths import cache_dir

    return cache_dir() / PERF_DIR_NAME


class PerfStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.stalls_dir = self.root / PERF_STALLS_DIR_NAME
        self._queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue(maxsize=PERF_WRITE_QUEUE_MAX)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._day: str | None = None
        self._capped_days: set[str] = set()
        self._stall_hour: int | None = None
        self._stall_files_this_hour = 0
        self.write_dropped = 0
        self.stall_files_skipped = 0
        self.last_error: str | None = None

    # -- producers (any thread) -------------------------------------------
    def put(self, line: dict[str, Any]) -> None:
        self._enqueue("line", line)

    def put_stall(self, report: dict[str, Any]) -> bool:
        """Queue a full stall report; False when this hour's file budget is spent."""
        hour = int(time.time() // 3600)
        if hour != self._stall_hour:
            self._stall_hour, self._stall_files_this_hour = hour, 0
        if self._stall_files_this_hour >= PERF_STALL_FILES_PER_HOUR:
            self.stall_files_skipped += 1
            return False
        self._stall_files_this_hour += 1
        self._enqueue("stall", report)
        return True

    def stall_path(self, stall_id: str) -> Path:
        return self.stalls_dir / f"{stall_id}.json"

    def _enqueue(self, kind: str, obj: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait((kind, obj))
        except queue.Full:
            self.write_dropped += 1

    # -- writer thread -----------------------------------------------------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="nova-perf-writer", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._thread = None
        self.drain()

    def _run(self) -> None:
        self.sweep()
        while not self._stop.is_set():
            try:
                first = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            self._write([first, *self._take(_BATCH_MAX - 1)])

    def drain(self) -> None:
        """Write whatever is queued, on the calling thread (shutdown, tests)."""
        items = self._take(PERF_WRITE_QUEUE_MAX)
        if items:
            self._write(items)

    def _take(self, n: int) -> list[tuple[str, dict[str, Any]]]:
        out = []
        for _ in range(n):
            try:
                out.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return out

    def _write(self, items: list[tuple[str, dict[str, Any]]]) -> None:
        by_day: dict[str, list[str]] = {}
        for kind, obj in items:
            try:
                if kind == "stall":
                    self._write_stall(obj)
                    continue
                day = et_date(float(obj.get("ts") or time.time()))
                if obj.get("kind") in ("sample", "client") and day in self._capped_days:
                    continue
                by_day.setdefault(day, []).append(json.dumps(obj, separators=(",", ":")))
            except (OSError, TypeError, ValueError) as exc:
                self._error(f"{type(exc).__name__}: {exc}")
        for day, lines in by_day.items():
            if day != self._day:
                self._day = day
                self.sweep()
            path = self.root / f"{day}.jsonl"
            try:
                self.root.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write("\n".join(lines) + "\n")
                if path.stat().st_size > PERF_DAY_FILE_MAX_MB * 1_000_000 and day not in self._capped_days:
                    self._capped_days.add(day)
                    logger.warning("perf: %s passed %d MB; samples stop for the day", path, PERF_DAY_FILE_MAX_MB)
            except OSError as exc:
                self._error(f"{type(exc).__name__}: {exc}")

    def _write_stall(self, report: dict[str, Any]) -> None:
        self.stalls_dir.mkdir(parents=True, exist_ok=True)
        path = self.stall_path(str(report["id"]))
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(report, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, path)

    def _error(self, message: str) -> None:
        if message != self.last_error:
            logger.warning("perf: write failed: %s", message)
        self.last_error = message

    def sweep(self, now: float | None = None) -> int:
        """Remove day files and stall reports older than the retention window."""
        now = time.time() if now is None else now
        cutoff_day = (datetime.fromtimestamp(now, _ET) - timedelta(days=PERF_RETENTION_DAYS)).strftime("%Y-%m-%d")
        cutoff_ts = now - PERF_RETENTION_DAYS * 86400
        removed = 0
        try:
            for path in list(self.root.glob("*.jsonl")):
                if path.stem < cutoff_day:
                    path.unlink(missing_ok=True)
                    removed += 1
            for path in list(self.stalls_dir.glob("*.json")):
                if path.stat().st_mtime < cutoff_ts:
                    path.unlink(missing_ok=True)
                    removed += 1
        except OSError as exc:
            self._error(f"retention sweep: {type(exc).__name__}: {exc}")
        return removed
