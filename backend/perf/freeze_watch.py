"""A freeze names itself: every thread's stack when the whole process stopped (ADR 045).

The stall catcher (``stall_watch``) samples a stuck loop from its own thread, which needs the GIL;
when the whole process stops -- one long call holding the GIL, or the process not scheduled -- it
stops too. On 2026-10-05 at 08:31 ET the backend stopped for 8.8 s (no perf sample, "ib loop lag
8811ms") and left no stack.

``faulthandler``'s watchdog is a C thread that needs no GIL. This module's thread re-arms it every
``PERF_FREEZE_REARM_SEC``; if the process stops for ``PERF_FREEZE_DUMP_SEC`` the re-arm does not come
and the watchdog writes every Python thread's stack (file, line, function: no values) to
``<perf>/freezes/YYYY-MM-DD.txt``. When the thread runs again it sees the file grew and logs the
freeze to ``freezes.jsonl`` -- ``{schema_version, armed_at, noticed_at, frozen_sec, file, offset}``,
``frozen_sec`` from the last re-arm to when it noticed -- and at WARNING. ``last()`` answers the
``perf_freezes`` checklist row.
"""
from __future__ import annotations

import faulthandler
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from constants_perf import (
    PERF_FREEZE_DUMP_SEC,
    PERF_FREEZE_LOG_NAME,
    PERF_FREEZE_REARM_SEC,
    PERF_FREEZE_SCHEMA_VERSION,
    PERF_FREEZES_DIR_NAME,
    PERF_RETENTION_DAYS,
)

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


def freeze_record(*, armed_at: float, noticed_at: float, file: str, offset: int) -> dict[str, Any]:
    """One freeze, as ``freezes.jsonl`` keeps it (pure)."""
    return {
        "schema_version": PERF_FREEZE_SCHEMA_VERSION,
        "armed_at": round(armed_at, 3),
        "noticed_at": round(noticed_at, 3),
        "frozen_sec": round(max(0.0, noticed_at - armed_at), 2),
        "file": file,
        "offset": int(offset),
    }


class FreezeWatch:
    """Owns the ``faulthandler`` watchdog for the process (there is one per process)."""

    def __init__(self, root: Path, *, dump_sec: float = PERF_FREEZE_DUMP_SEC,
                 rearm_sec: float = PERF_FREEZE_REARM_SEC) -> None:
        self.dir = Path(root) / PERF_FREEZES_DIR_NAME
        self.dump_sec = dump_sec
        self.rearm_sec = rearm_sec
        self._fh = None
        self._day: str | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last: dict[str, Any] | None = None
        self.count = 0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        self._prune()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="nova-freeze-watch", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._thread = None
        try:
            faulthandler.cancel_dump_traceback_later()
        finally:
            self._close()

    def last(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._last) if self._last else None

    def _close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                logger.warning("perf freeze watch: closing the dump file failed", exc_info=True)
            self._fh = None

    def _open(self, day: str) -> None:
        faulthandler.cancel_dump_traceback_later()
        self._close()
        self._fh = open(self.dir / f"{day}.txt", "a", encoding="utf-8")  # noqa: SIM115 -- held for faulthandler
        self._day = day

    def _size(self) -> int:
        return os.fstat(self._fh.fileno()).st_size if self._fh is not None else 0

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                logger.exception("perf freeze watch: tick failed")
                self._stop.wait(self.rearm_sec)

    def _tick(self) -> None:
        day = datetime.now(_ET).strftime("%Y-%m-%d")
        if day != self._day:
            self._open(day)
        before = self._size()
        armed_at = time.time()
        faulthandler.dump_traceback_later(self.dump_sec, repeat=False, file=self._fh, exit=False)
        self._stop.wait(self.rearm_sec)
        if self._size() > before:
            self._noted(armed_at, time.time(), before)

    def _noted(self, armed_at: float, noticed_at: float, offset: int) -> None:
        name = f"{self._day}.txt"
        record = freeze_record(armed_at=armed_at, noticed_at=noticed_at, file=name, offset=offset)
        with self._lock:
            self._last = record
            self.count += 1
        try:
            with open(self.dir / PERF_FREEZE_LOG_NAME, "a", encoding="utf-8") as log:
                log.write(json.dumps(record) + "\n")
        except OSError:
            logger.warning("perf freeze watch: the freeze log could not be written", exc_info=True)
        logger.warning(
            "perf: the whole process stopped for %.1f s; every thread's stack is in %s at byte %d",
            record["frozen_sec"], self.dir / name, offset,
        )

    def _prune(self) -> None:
        cutoff = (datetime.now(_ET) - timedelta(days=PERF_RETENTION_DAYS)).strftime("%Y-%m-%d")
        for path in self.dir.glob("*.txt"):
            if path.stem < cutoff:
                try:
                    path.unlink()
                except OSError:
                    logger.warning("perf freeze watch: could not remove %s", path, exc_info=True)


_watch: FreezeWatch | None = None


def start(root: Path) -> FreezeWatch:
    global _watch
    if _watch is None:
        _watch = FreezeWatch(root)
    _watch.start()
    return _watch


def status() -> dict[str, Any]:
    """``{running, count, last}`` for the checklist."""
    watch = _watch
    if watch is None:
        return {"running": False, "count": 0, "last": None}
    return {"running": watch._thread is not None and watch._thread.is_alive(),
            "count": watch.count, "last": watch.last()}
