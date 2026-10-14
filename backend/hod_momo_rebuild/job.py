"""Asking for a rebuilt day's HOD Momo alerts, and its state.

``request`` is the desk's one door (``POST /api/hod-momo/history/{date}/rebuild``): it says why a day cannot be
rebuilt (``unavailable``), leaves a current ready, queued or building day alone, and otherwise starts the build in
its own process (``worker``), below normal priority. One day at a time: asking for another day ends the running
build (``stopped``); so does the backend shutting down (``stop_all``, from ``app_lifespan``). A build whose process
ended without finishing reads ``failed`` with why; a ``building`` job nobody rewrote for ``HOD_MOMO_REBUILD_STALE_SEC``
(a restart killed it) reads ``failed`` too. A ready build made from other boards, other HOD settings or older
rebuild logic than now (``run.fingerprint``) reads ``none`` with ``STALE``, and asking builds it again.
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

from constants_hod_momo import (
    HOD_MOMO_REBUILD_FINGERPRINT_TTL_SEC,
    HOD_MOMO_REBUILD_STALE_SEC,
    HOD_MOMO_REBUILD_STOP_WAIT_SEC,
)
from constants_leaderboard import (
    LEADERBOARD_SECONDS_ACTIVE,
    LEADERBOARD_SECONDS_FAILED,
    LEADERBOARD_SECONDS_NONE,
    LEADERBOARD_SECONDS_QUEUED,
    LEADERBOARD_SECONDS_READY,
    LEADERBOARD_SECONDS_STOPPED,
    LEADERBOARD_SECONDS_UNAVAILABLE,
)
from constants_sim import SIM_MASSIVE_DAYS, SIM_MASSIVE_TRADES
from hod_momo_rebuild import run, store, watch
from leaderboard import store as board_store
from sim import massive_files

logger = logging.getLogger(__name__)
_BACKEND_DIR = Path(__file__).resolve().parents[1]
_lock = threading.RLock()
_running: dict[str, "_Handle"] = {}
_boards: dict[str, tuple[float, str | None]] = {}    # day -> (read at, boards digest)

RECORDED = "Nova recorded HOD Momo this day: these are the alerts it raised"
NOT_REBUILT = "This day has no rebuilt Scanner boards to rebuild HOD Momo from"
STALE = "The day's boards or your HOD Momo settings changed since this was built; it is being built again"


class _Handle:
    def __init__(self, day: str):
        self.day, self.stopping = day, False

    def alive(self) -> bool:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def wait(self, timeout: float) -> bool:
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
        self.thread = threading.Thread(target=self._main, daemon=True, name="hod-rebuild")

    def _main(self) -> None:
        try:
            run.run(self.day, self.event)
        except BaseException as exc:  # noqa: BLE001 -- the job says why, as the process's watcher would
            _ended(self, str(exc) or type(exc).__name__)
            return
        _forget(self)

    def alive(self) -> bool:
        return self.thread.is_alive()

    def stop(self) -> None:
        self.stopping = True
        self.event.set()

    def wait(self, timeout: float) -> bool:
        self.thread.join(timeout)
        return not self.thread.is_alive()


def worker_command(day: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--hod-rebuild", "--date", day]
    return [sys.executable, "-m", "hod_momo_rebuild.worker", "--date", day]


def _launch_process(day: str) -> _Handle:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_BACKEND_DIR) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env.setdefault("PYTHONIOENCODING", "utf-8:backslashreplace")
    try:
        from paths import log_dir

        errors = open(log_dir() / "hod_rebuild.err", "ab")
    except OSError:
        errors = subprocess.DEVNULL
    flags = 0x08000000 | 0x00004000 if sys.platform == "win32" else 0   # CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS
    proc = subprocess.Popen(worker_command(day), cwd=str(_BACKEND_DIR), env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=errors, creationflags=flags)
    handle = _ProcessHandle(day, proc)

    def watch_exit():
        code = proc.wait()
        if errors is not subprocess.DEVNULL:
            errors.close()
        _ended(handle, f"The rebuild process ended before finishing (exit code {code})")

    threading.Thread(target=watch_exit, daemon=True, name="hod-rebuild-watch").start()
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
        job = store.read_job(handle.day) if current else None
        if job is not None and job.get("status") in LEADERBOARD_SECONDS_ACTIVE:
            if handle.stopping:
                store.write_job(handle.day, status=LEADERBOARD_SECONDS_STOPPED, stage=None, error=None)
            else:
                store.write_job(handle.day, status=LEADERBOARD_SECONDS_FAILED, stage=None, error=error)
    except Exception:
        logger.exception("HOD rebuild: could not record how the build of %s ended", handle.day)
    finally:
        _forget(handle)


def _alive(day: str) -> bool:
    with _lock:
        handle = _running.get(day)
        return handle is not None and handle.alive()


def recorded(day: str) -> bool:
    import cache

    return bool(cache.hod_momo_snapshot_on_file(day))


def unavailable_reason(day: str) -> str | None:
    """Why the day cannot be rebuilt, or None."""
    if recorded(day):
        return RECORDED
    why = massive_files.unavailable_reason()
    if why:
        return why
    for dataset, what in ((SIM_MASSIVE_TRADES, "trades"), (SIM_MASSIVE_DAYS, "day-bar")):
        if massive_files.day_file(dataset, day) is None:
            return f"The day's Massive {what} file is not on disk"
    return None


def _boards_mark(day: str, *, fresh: bool = False) -> str | None:
    held = _boards.get(day)
    if not fresh and held is not None and time.monotonic() - held[0] <= HOD_MOMO_REBUILD_FINGERPRINT_TTL_SEC:
        return held[1]
    db = board_store.read_only()
    mark = None
    if db is not None:
        try:
            mark = watch.fingerprint(db, day)
        finally:
            db.close()
    _boards[day] = (time.monotonic(), mark)
    return mark


def current_fingerprint(day: str, *, fresh: bool = False) -> str | None:
    """What a build of the day would be made from now; None when the day has no rebuilt boards."""
    from hod_momo_rebuild.engine import config_digest

    boards = _boards_mark(day, fresh=fresh)
    return None if boards is None else run.fingerprint(boards, config_digest())


def status(day: str) -> dict[str, Any]:
    """The job as the route says it: ``none`` before any request or when a ready build is out of date."""
    job = store.read_job(day)
    if job is None:
        return {"status": LEADERBOARD_SECONDS_NONE}
    if job.get("status") in LEADERBOARD_SECONDS_ACTIVE and not _alive(day):
        if time.time() - float(job.get("updated_ts") or 0.0) > HOD_MOMO_REBUILD_STALE_SEC:
            job = {**job, "status": LEADERBOARD_SECONDS_FAILED, "stage": None,
                   "error": "The rebuild stopped answering (the backend restarted while it ran); it starts over"}
    if job.get("status") == LEADERBOARD_SECONDS_READY:
        if not store.data_path(day).is_file():
            return {"status": LEADERBOARD_SECONDS_NONE}
        if job.get("fingerprint") != current_fingerprint(day):
            return {"status": LEADERBOARD_SECONDS_NONE, "reason": STALE}
    return job


def request(day: str) -> dict[str, Any]:
    """Build the day unless it is current and ready, queued or building."""
    why = unavailable_reason(day)
    if why:
        return {"status": LEADERBOARD_SECONDS_UNAVAILABLE, "reason": why}
    mark = current_fingerprint(day, fresh=True)
    if mark is None:
        return {"status": LEADERBOARD_SECONDS_UNAVAILABLE, "reason": NOT_REBUILT}
    with _lock:
        job = store.read_job(day) or {}
        state = status(day).get("status")
        if state == LEADERBOARD_SECONDS_READY and job.get("fingerprint") == mark:
            return job
        if state in LEADERBOARD_SECONDS_ACTIVE:
            return job                       # running here, or rewritten by a build an earlier backend started
        for other, handle in list(_running.items()):
            if other != day and handle.alive():
                logger.info("HOD rebuild: %s asked for; ending the build of %s", day, other)
                handle.stop()
        job = store.write_job(day, status=LEADERBOARD_SECONDS_QUEUED, stage=None, done=None, total=None,
                              started_ts=time.time(), finished_ts=None, error=None, summary=None, fingerprint=None)
        try:
            _running[day] = launch(day)
        except Exception as exc:  # noqa: BLE001 -- the job says why the build could not start
            logger.exception("HOD rebuild: the build of %s could not start", day)
            return store.write_job(day, status=LEADERBOARD_SECONDS_FAILED, error=f"The rebuild could not start: {exc}")
        return job


def stop_all(wait_sec: float = HOD_MOMO_REBUILD_STOP_WAIT_SEC) -> None:
    """End every running build and wait for it (the backend is shutting down)."""
    with _lock:
        handles = [handle for handle in _running.values() if handle.alive()]
    for handle in handles:
        handle.stop()
    for handle in handles:
        if handle.wait(wait_sec):
            _ended(handle, "")
        else:
            logger.warning("HOD rebuild: the build of %s did not end within %.0f s", handle.day, wait_sec)


def reset_for_tests() -> None:
    stop_all()
    with _lock:
        _running.clear()
    _boards.clear()
