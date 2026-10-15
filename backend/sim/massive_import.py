"""The jobs that import stock-days from the operator's Massive flat files (ADR 046).

An import (``massive_read.run``) reads one ticker's day from the day's files and
writes it into the Massive store in one transaction -- whole or absent. Its identity
is the stock-day (``day_spec``: the session, 04:00-20:00 ET), so the files are read
once per symbol and day whatever window asked (amendment 2026-10-09): it keeps the
whole session when the day fits a selection, else only the window asked for (its
focus). ``holds`` says whether an import holds a window, ``held_spec`` what it holds.
This module owns the job around it: starting one (``begin``), pausing it, its status
and progress for the desk. An import runs in its own process (``massive_worker``),
one at a time, beside (never instead of) an IBKR download: the inflating and parsing
never share the API's GIL.

An import of one window, made before stock-days, keeps playing; the next load of it
starts the day's import, which drops it when it completes holding that window.

A day whose quotes file was not on disk at the first import says so
(``quote_status: "not_downloaded"``); asking again once that file is down imports
the window again, now with its bid and ask, while the stored window keeps playing.
What an import holds, and when it is read again, are ``massive_rules``.

Once its job is complete, an import's process builds the indexes of the day files
it read without one (``massive_index``). It holds no slot then: an import of the
same day runs beside it (and finds the index once it is saved), an import of another
day ends it.

A running import rewrites its job at least every ``SIM_MASSIVE_PROGRESS_EVERY_SEC``;
a ``running`` job that stopped being rewritten belongs to an import a restart killed,
and lists as ``interrupted``. Importing again starts it over.
"""
from __future__ import annotations

import logging
import math
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from constants_sim import (
    SIM_MASSIVE_DAY_END, SIM_MASSIVE_DAY_START, SIM_MASSIVE_MINUTES, SIM_MASSIVE_QUOTES, SIM_MASSIVE_SOURCE,
    SIM_MASSIVE_TRADES,
)
from sim import history_store, massive_files as files, massive_store as store
from sim.massive_rules import cap_raised, holds, import_again
from sim.massive_read import TooLarge, run  # noqa: F401  (``run`` is looked up here, so a test can stand in for it)

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_active: dict[str, "_Handle"] = {}
# Imports whose job is complete and whose process still builds the day files' indexes; they hold no slot.
_indexing: list["_Handle"] = []
# Seconds without a rewrite before a running job counts as killed (a running import rewrites every second).
STALE_AFTER_SEC = 60.0
_BACKEND_DIR = Path(__file__).resolve().parent.parent


class _Handle:
    """A running import: alive or not, and how to end it (a pause)."""

    def __init__(self, job_id: str):
        self.job_id, self.pausing = job_id, False

    def alive(self) -> bool:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError


class _ProcessHandle(_Handle):
    def __init__(self, job_id: str, proc: subprocess.Popen):
        super().__init__(job_id)
        self.proc = proc

    def alive(self) -> bool:
        return self.proc.poll() is None

    def stop(self) -> None:
        self.pausing = True
        self.proc.terminate()


class _ThreadHandle(_Handle):
    """In-process import (tests): the same ``run`` on a thread, ended through ``run``'s stop event."""

    def __init__(self, job_id: str):
        super().__init__(job_id)
        self.event = threading.Event()
        self.thread = threading.Thread(target=_worker, args=(job_id, self.event), daemon=True, name="massive-import")

    def alive(self) -> bool:
        return self.thread.is_alive()

    def stop(self) -> None:
        self.pausing = True
        self.event.set()


def worker_command(job_id: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--massive-import", "--job-id", job_id]
    return [sys.executable, "-m", "sim.massive_worker", "--job-id", job_id]


def _launch_process(job_id: str) -> _Handle:
    """Start the import in its own process; a watcher marks it paused or failed if it ends without finishing."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_BACKEND_DIR) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env.setdefault("PYTHONIOENCODING", "utf-8:backslashreplace")
    try:
        from paths import log_dir

        errors = open(log_dir() / "massive_import.err", "ab")
    except OSError:
        errors = subprocess.DEVNULL
    flags = 0x08000000 | 0x00004000 if sys.platform == "win32" else 0   # CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS
    proc = subprocess.Popen(worker_command(job_id), cwd=str(_BACKEND_DIR), env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=errors, creationflags=flags)
    handle = _ProcessHandle(job_id, proc)
    _watch(handle, errors)
    return handle


def _watch(handle: _ProcessHandle, errors) -> None:
    """When the import process ends, a job it left running is paused (the operator ended it) or failed."""
    def watch():
        code = handle.proc.wait()
        if errors is not subprocess.DEVNULL and errors is not None:
            errors.close()
        try:
            with _lock:                     # a newer import of this stock-day owns the job now: not this process's to end
                superseded = _active.get(handle.job_id) not in (None, handle)
            job = None if superseded else store.get(handle.job_id)
            if job is not None and job["status"] in store.ACTIVE:
                if handle.pausing:
                    store.update(handle.job_id, status="paused", stage=None, stages=None, error=None)
                else:
                    store.update(handle.job_id, status="failed", stage=None, stages=None,
                                 error=f"The import process ended before finishing (exit code {code})")
        except Exception:
            logger.exception("Massive import: could not record how %s ended", handle.job_id)
        finally:
            with _lock:
                if _active.get(handle.job_id) is handle:
                    _active.pop(handle.job_id, None)
    threading.Thread(target=watch, daemon=True, name="massive-import-watch").start()


def _launch_thread(job_id: str) -> _Handle:
    handle = _ThreadHandle(job_id)
    handle.thread.start()
    return handle


# How an import is started: its own process in the desk, a thread when a test swaps it.
launch = _launch_process


def spec(window: dict) -> dict:
    """An operator's validated window (``history_store.window``), as a Massive window."""
    return dict(window, source=SIM_MASSIVE_SOURCE)


def day_spec(window: dict) -> dict:
    """The import's identity: the window's whole stock-day, from the Massive files."""
    return spec(history_store.window(window["symbol"], window["date"], SIM_MASSIVE_DAY_START, SIM_MASSIVE_DAY_END))


def day_job(window: dict) -> dict | None:
    """The import of the window's stock-day, if one was ever started."""
    try:
        wanted = day_spec(window)
    except ValueError:      # a day not over yet: Massive publishes a day once it has ended, so none was imported
        return None
    return store.find(wanted)


def holder(window: dict) -> tuple[dict | None, dict | None]:
    """``(holder, job)``: the import that holds a Massive window -- an older import of exactly it, else its
    stock-day's -- and the import whose status the window shows meanwhile (the holder, else the day's)."""
    exact = store.find(spec(window))
    if holds(exact, window):
        return exact, exact
    day = day_job(window)
    if holds(day, window):
        return day, day
    return None, day or exact


def held_spec(job: dict) -> dict:
    """The window a complete import holds, as a Massive selection: its whole day, or a capped day's focus."""
    start, end = job.get("kept_start") or job["start"], job.get("kept_end") or job["end"]
    return spec(history_store.window(job["symbol"], job["date"], start, end))


def availability(day: str) -> dict:
    """What the Massive folder holds for ``day``: ``{available, reason, trades, quotes, minute_aggs}``."""
    reason = files.unavailable_reason()
    have = files.files_for(day) if reason is None else dict.fromkeys(files.DATASETS, False)
    if reason is None and not have[SIM_MASSIVE_TRADES]:
        reason = f"The Massive trades file for {day} is not on disk (yet)"
    return dict(available=reason is None, reason=reason, trades=have[SIM_MASSIVE_TRADES],
                quotes=have[SIM_MASSIVE_QUOTES], minute_aggs=have[SIM_MASSIVE_MINUTES])


def _finishing(job_id: str) -> bool:
    """A live import whose job is complete: it only builds the day files' indexes (``massive_read.run``)."""
    job = store.get(job_id)
    return job is not None and job["status"] == "complete"


def running_ids() -> list[str]:
    with _lock:
        return sorted(job_id for job_id, handle in _active.items() if handle.alive() and not _finishing(job_id))


def indexing_ids() -> list[str]:
    """Imports whose job is complete and whose process still builds the day files' indexes."""
    with _lock:
        finishing = [job_id for job_id, handle in _active.items() if handle.alive() and _finishing(job_id)]
        return sorted(set(finishing + [handle.job_id for handle in _indexing if handle.alive()]))


def effective_status(job: dict, now: float | None = None) -> str:
    """``interrupted`` for a running job nothing is advancing (no live import of ours, no recent rewrite)."""
    now = time.time() if now is None else now
    with _lock:
        handle = _active.get(job["id"])
        mine = handle is not None and handle.alive()
    if job["status"] in store.ACTIVE and not mine and now - job.get("updated", 0) > STALE_AFTER_SEC:
        return "interrupted"
    return job["status"]


def progress(job: dict, now: float | None = None) -> dict:
    """The job as the desk lists it: an IBKR download's progress fields, read off this import's own stages."""
    now = time.time() if now is None else now
    status = effective_status(job, now)
    start, end = job["start_ts"], job["end_ts"]
    ranges = job.get("ranges") or []
    covered = sum(b - a for a, b in ranges)
    pct = 100.0 if status == "complete" else float(job.get("scan_pct") or 0.0)
    eta = None
    started = job.get("started")
    if status in store.ACTIVE and started and 0 < pct < 100:
        elapsed = max(0.0, job["updated"] - started)
        eta = math.ceil(elapsed * (100 - pct) / pct) if elapsed > 0 else None
    age = max(0.0, now - job.get("updated", now))
    # ``cap_raised``: a capped import whose cap has been raised since -- its next load reads the day again.
    return dict(job, status=status, coverage=ranges, covered_seconds=covered,
                downloaded_through=end if status == "complete" else start, progress_pct=round(pct, 2),
                age_seconds=round(age, 1), stale=status == "interrupted", eta_seconds=eta, cap_raised=cap_raised(job))


def list_jobs() -> list[dict]:
    """Every import as the desk lists it; an unreadable store raises (the listing states it, never an empty list)."""
    return [progress(job) for job in store.jobs()]


def begin(window: dict) -> dict:
    """Start (or answer) the import of ``window``'s stock-day; refused with the reason when it cannot run.

    ``window`` is the import's focus: what it keeps if the day is over a cap. A running import of the
    same stock-day answers whatever its focus; a complete one answers when it holds ``window``.
    """
    found = availability(window["date"])
    if not found["available"]:
        raise ValueError(found["reason"])
    wanted = day_spec(window)
    with _lock:
        job_id = store.job_id_for(wanted)
        for other, handle in list(_active.items()):
            if not handle.alive():
                _active.pop(other, None)
            elif _finishing(other):         # its job is done: it only builds the day files' indexes
                _indexing.append(_active.pop(other))
        _indexing[:] = [handle for handle in _indexing if handle.alive()]
        if _active:
            if job_id in _active:
                return progress(store.get(job_id) or store.new_job(wanted))
            raise ValueError("Another Massive import is running; it finishes in seconds to minutes -- try again then")
        job = store.get(job_id)
        if job and job["status"] == "complete" and holds(job, window) and not import_again(job, found):
            return progress(job)
        for handle in [h for h in _indexing if (store.get(h.job_id) or {}).get("date") != window["date"]]:
            handle.stop()                   # another day's index: the day asked for now comes first
            _indexing.remove(handle)
        job = dict(job or store.new_job(wanted), status="running", stage="reading", stages=None, scan_pct=0.0,
                   error=None, started=time.time(), updated=time.time(), files=found,
                   focus_start=window["start"], focus_end=window["end"],
                   focus_start_ts=window["start_ts"], focus_end_ts=window["end_ts"])
        store.save(job)
        _active[job_id] = launch(job_id)
    return progress(job)


def wants_import(window: dict, found: dict) -> bool:
    """Would ``begin`` start an import for ``window``: the day is on disk, and its stock-day's import is not
    running and does not hold the window, or is to be read again (``massive_rules.import_again``).

    On a day over a cap, an older import of exactly ``window`` (one window at a time, before stock-days)
    already holds it, and is not read again.
    """
    if not found["available"]:
        return False
    day = day_job(window)
    if day is None:
        return True
    status = effective_status(day)
    if status in store.ACTIVE:
        return False
    if status != "complete" or import_again(day, found):
        return True
    if holds(day, window):
        return False
    older = store.find(spec(window)) if day.get("capped") else None
    return not (older is not None and older["id"] != day["id"] and effective_status(older) == "complete"
                and older.get("ranges") and not import_again(older, found))


def pause(job_id: str) -> dict:
    """End a running import; it lists as paused, and importing again starts it over."""
    with _lock:
        handle = _active.get(job_id)
    if handle is not None and handle.alive():
        handle.stop()
    job = store.get(job_id)
    if job is None:
        raise ValueError("Import not found")
    return progress(job)


def _worker(job_id: str, stop: threading.Event) -> None:
    """``run`` on a thread (tests), recording how it ended as the worker process does."""
    try:
        run(job_id, stop)
    except files.Cancelled:
        store.update(job_id, status="paused", stage=None, stages=None, error=None)
    except Exception as exc:  # the import fails with its reason; the desk shows it and offers a retry
        logger.exception("Massive import failed: %s", job_id)
        try:
            store.update(job_id, status="failed", stage=None, stages=None, error=str(exc) or type(exc).__name__)
        except Exception:
            logger.exception("Massive import: could not mark %s failed", job_id)
    finally:
        with _lock:
            handle = _active.get(job_id)
            if isinstance(handle, _ThreadHandle) and handle.thread is threading.current_thread():
                _active.pop(job_id, None)
