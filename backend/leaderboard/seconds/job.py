"""Asking for a rebuilt day's Gappers by the second, and its state (ADR 023 amendment 2026-10-13).

``request`` is the desk's one door (``POST /api/leaderboard/{date}/seconds``): it says why a day cannot be built
(``unavailable``), leaves a ready, queued or building day alone, and otherwise starts the build in its own process
(``worker``), below normal priority. One day at a time: asking for another day ends the running build, whose job
then reads ``stopped``; so does a backend shutting down (``stop_all``, from ``app_lifespan``). A watcher marks a build whose process ended without finishing ``failed`` (or ``stopped``
when it was ended on purpose); a ``building`` job no process rewrites for ``LEADERBOARD_SECONDS_STALE_SEC`` -- a
restart killed it -- reads ``failed`` too. ``status`` is what the route answers.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from constants_leaderboard import (
    LEADERBOARD_SECONDS_ACTIVE,
    LEADERBOARD_SECONDS_BOARD,
    LEADERBOARD_SECONDS_FAILED,
    LEADERBOARD_SECONDS_NONE,
    LEADERBOARD_SECONDS_QUEUED,
    LEADERBOARD_SECONDS_READY,
    LEADERBOARD_SECONDS_STALE_SEC,
    LEADERBOARD_SECONDS_STOP_WAIT_SEC,
    LEADERBOARD_SECONDS_STOPPED,
    LEADERBOARD_SECONDS_UNAVAILABLE,
)
from constants_sim import SIM_MASSIVE_MINUTES, SIM_MASSIVE_TRADES
from leaderboard import store as board_store
from leaderboard.seconds import inputs, store
from sim import massive_files

logger = logging.getLogger(__name__)
BOARD = LEADERBOARD_SECONDS_BOARD
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_lock = threading.RLock()
_running: dict[str, "_Handle"] = {}

RECORDED = ("Nova recorded this day: its Gappers are the list the desk showed, kept per minute")
NOT_REBUILT = "This day has no rebuilt Gappers list to fill in"


class _Handle:
    def __init__(self, day: str):
        self.day, self.stopping = day, False

    def alive(self) -> bool:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def wait(self, timeout: float) -> bool:
        """True once the build has ended (within ``timeout`` seconds)."""
        raise NotImplementedError


class _ProcessHandle(_Handle):
    def __init__(self, day: str, proc: subprocess.Popen):
        super().__init__(day)
        self.proc = proc

    def alive(self) -> bool:
        return self.proc.poll() is None

    def stop(self) -> None:
        self.stopping = True
        self.proc.terminate()

    def wait(self, timeout: float) -> bool:
        try:
            self.proc.wait(timeout)
        except subprocess.TimeoutExpired:
            return False
        return True


class _ThreadHandle(_Handle):
    """The build on a thread (tests): the same ``run``, ended through its stop event."""

    def __init__(self, day: str):
        super().__init__(day)
        self.event = threading.Event()
        self.thread = threading.Thread(target=_thread_main, args=(self,), daemon=True, name="board-seconds")

    def alive(self) -> bool:
        return self.thread.is_alive()

    def stop(self) -> None:
        self.stopping = True
        self.event.set()

    def wait(self, timeout: float) -> bool:
        self.thread.join(timeout)
        return not self.thread.is_alive()


def _thread_main(handle: _ThreadHandle) -> None:
    from leaderboard.seconds import run

    try:
        run.run(handle.day, handle.event)
    except BaseException as exc:  # noqa: BLE001 -- the job says why, as the process's watcher would
        _ended(handle, str(exc) or type(exc).__name__)
        return
    _forget(handle)


def worker_command(day: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--board-seconds", "--date", day]
    return [sys.executable, "-m", "leaderboard.seconds.worker", "--date", day]


def _launch_process(day: str) -> _Handle:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_BACKEND_DIR) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env.setdefault("PYTHONIOENCODING", "utf-8:backslashreplace")
    try:
        from paths import log_dir

        errors = open(log_dir() / "board_seconds.err", "ab")
    except OSError:
        errors = subprocess.DEVNULL
    flags = 0x08000000 | 0x00004000 if sys.platform == "win32" else 0   # CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS
    proc = subprocess.Popen(worker_command(day), cwd=str(_BACKEND_DIR), env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=errors, creationflags=flags)
    handle = _ProcessHandle(day, proc)

    def watch():
        code = proc.wait()
        if errors is not subprocess.DEVNULL:
            errors.close()
        _ended(handle, f"The build process ended before finishing (exit code {code})")

    threading.Thread(target=watch, daemon=True, name="board-seconds-watch").start()
    return handle


def _launch_thread(day: str) -> _Handle:
    handle = _ThreadHandle(day)
    handle.thread.start()
    return handle


# How a build is started: its own process in the desk, a thread when a test swaps it.
launch = _launch_process


def _forget(handle: _Handle) -> None:
    with _lock:
        if _running.get(handle.day) is handle:
            _running.pop(handle.day, None)


def _ended(handle: _Handle, error: str) -> None:
    """A build ended: a job it left active reads ``stopped`` (ended on purpose) or ``failed`` with why."""
    try:
        with _lock:
            current = _running.get(handle.day) in (None, handle)
        job = store.read_job(handle.day, BOARD) if current else None
        if job is not None and job.get("status") in LEADERBOARD_SECONDS_ACTIVE:
            if handle.stopping:
                store.write_job(handle.day, BOARD, status=LEADERBOARD_SECONDS_STOPPED, stage=None, error=None)
            else:
                store.write_job(handle.day, BOARD, status=LEADERBOARD_SECONDS_FAILED, stage=None, error=error)
    except Exception:
        logger.exception("Gappers by the second: could not record how the build of %s ended", handle.day)
    finally:
        _forget(handle)


def _alive(day: str) -> bool:
    with _lock:
        handle = _running.get(day)
        return handle is not None and handle.alive()


def unavailable_reason(day: str) -> str | None:
    """Why the day cannot be built, or None."""
    why = massive_files.unavailable_reason()
    if why:
        return why
    if inputs.recorded(day):
        return RECORDED
    for dataset, what in ((SIM_MASSIVE_MINUTES, "minute"), (SIM_MASSIVE_TRADES, "trades")):
        if massive_files.day_file(dataset, day) is None:
            return f"The day's Massive {what} file is not on disk"
    return None


def _stored_fingerprint(day: str) -> str | None:
    db = board_store.read_only()
    if db is None:
        return None
    try:
        return inputs.fingerprint(db, day)
    finally:
        db.close()


def status(day: str) -> dict[str, Any]:
    """The job as the route says it: ``none`` before any request; a dead ``building`` job reads ``failed``."""
    job = store.read_job(day, BOARD)
    if job is None:
        return {"status": LEADERBOARD_SECONDS_NONE}
    if job.get("status") in LEADERBOARD_SECONDS_ACTIVE and not _alive(day):
        if time.time() - float(job.get("updated_ts") or 0.0) > LEADERBOARD_SECONDS_STALE_SEC:
            job = {**job, "status": LEADERBOARD_SECONDS_FAILED, "stage": None,
                   "error": "The build stopped answering (the backend restarted while it ran); asking again starts it over"}
    if job.get("status") == LEADERBOARD_SECONDS_READY and not store.data_path(day, BOARD).is_file():
        return {"status": LEADERBOARD_SECONDS_NONE}
    return job


def request(day: str) -> dict[str, Any]:
    """Build the day unless it is ready (for the rebuilt day as stored now), queued or building."""
    why = unavailable_reason(day)
    if why:
        return {"status": LEADERBOARD_SECONDS_UNAVAILABLE, "reason": why}
    mark = _stored_fingerprint(day)
    if mark is None:
        return {"status": LEADERBOARD_SECONDS_UNAVAILABLE, "reason": NOT_REBUILT}
    with _lock:
        job = status(day)
        state = job.get("status")
        if state == LEADERBOARD_SECONDS_READY and job.get("fingerprint") == mark:
            return job
        if state in LEADERBOARD_SECONDS_ACTIVE:
            # Running here, or still rewritten by a build an earlier backend started: never a second one.
            return job
        for other, handle in list(_running.items()):
            if other != day and handle.alive():
                logger.info("Gappers by the second: %s asked for; ending the build of %s", day, other)
                handle.stop()
        job = store.write_job(day, BOARD, status=LEADERBOARD_SECONDS_QUEUED, stage=None, done=None, total=None,
                              started_ts=time.time(), finished_ts=None, error=None, summary=None, fingerprint=None)
        try:
            _running[day] = launch(day)
        except Exception as exc:  # noqa: BLE001 -- the job says why the build could not start
            logger.exception("Gappers by the second: the build of %s could not start", day)
            return store.write_job(day, BOARD, status=LEADERBOARD_SECONDS_FAILED, error=f"The build could not start: {exc}")
        return job


def stop_all(wait_sec: float = LEADERBOARD_SECONDS_STOP_WAIT_SEC) -> None:
    """End every running build and wait for it (the backend is shutting down: ``app_lifespan``). A build left
    running would outlive the backend, and the next one could not end it when another day is asked for."""
    with _lock:
        handles = [handle for handle in _running.values() if handle.alive()]
    for handle in handles:
        handle.stop()
    for handle in handles:
        if handle.wait(wait_sec):
            _ended(handle, "")             # stopped on purpose: the job reads ``stopped``
        else:
            logger.warning("Gappers by the second: the build of %s did not end within %.0f s", handle.day, wait_sec)


def reset_for_tests() -> None:
    stop_all()
    with _lock:
        _running.clear()
