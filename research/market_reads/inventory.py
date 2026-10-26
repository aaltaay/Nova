"""What is on disk, and the bulk build of the seek indexes that make any stock-day read in about a second."""
from __future__ import annotations

import ctypes
import logging
import os
import queue
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, as_completed, wait
from pathlib import Path
from typing import Any

from market_reads import REPO  # noqa: F401  (puts backend/ on sys.path)

from constants_sim import SIM_MASSIVE_MINUTES, SIM_MASSIVE_QUOTES, SIM_MASSIVE_TRADES
from sim import massive_files, massive_index

from market_reads import index_watch

DAY_AGGS = "day_aggs_v1"
DATASETS = (SIM_MASSIVE_MINUTES, SIM_MASSIVE_TRADES, SIM_MASSIVE_QUOTES)    # a day's files, small first
BELOW_NORMAL_PRIORITY_CLASS = 0x4000
INDEX_LOG = "index-build.log"
INDEX_STOP = "STOP"            # <root>/sim/index/STOP: a bulk build stops after the files in progress

log = logging.getLogger("market_reads")


def day_files(dataset: str, first: str | None = None, last: str | None = None) -> list[Path]:
    """Every whole day file of ``dataset`` (``.csv.gz``; a ``.part`` still arriving is not one), oldest first."""
    base = massive_files.root() / dataset
    out = []
    for year in sorted(p for p in base.glob("[12][0-9][0-9][0-9]") if p.is_dir()):
        for month in sorted(p for p in year.iterdir() if p.is_dir()):
            for path in sorted(month.glob("*.csv.gz")):
                day = path.name[:10]
                if (first is None or day >= first) and (last is None or day <= last):
                    out.append(path)
    return out


def below_normal() -> None:
    """Run this process below normal priority, so the desk keeps the CPU (Windows; elsewhere a no-op)."""
    if os.name == "nt":
        ctypes.windll.kernel32.SetPriorityClass(ctypes.c_void_p(-1), BELOW_NORMAL_PRIORITY_CLASS)


# ---- status -------------------------------------------------------------------------------------------------------
def status() -> dict[str, Any]:
    """Each dataset's days and indexed days, the day movers index, the past-day boards and the relative-volume
    table."""
    root = massive_files.root()
    out: dict[str, Any] = {"root": str(root), "datasets": {}}
    reason = massive_files.unavailable_reason()
    if reason:
        out["unavailable"] = reason
        return out
    for dataset in (*DATASETS, DAY_AGGS):
        files = day_files(dataset)
        row: dict[str, Any] = {"days": len(files), "first": files[0].name[:10] if files else None,
                               "last": files[-1].name[:10] if files else None}
        if dataset != DAY_AGGS:
            row["indexed"] = sum(massive_index.is_current(path, root) for path in files)
        out["datasets"][dataset] = row
    out["index_build"] = index_watch.read_status(root / "sim" / "index")
    out["movers_index"] = _movers_status()
    out["boards"] = _boards_status()
    out["rvol_table"] = _rvol_status()
    out["signal_table"] = _signals_status()
    return out


def _movers_status() -> dict[str, Any]:
    from day_movers import store as movers_store
    try:
        db = movers_store.read_only()
    except Exception as exc:  # noqa: BLE001 -- a status line names what failed, it never fails the status
        return {"error": f"{type(exc).__name__}: {exc}"}
    if db is None:
        return {"error": "no index yet"}
    try:
        n, first, last = db.execute("SELECT COUNT(*), MIN(session_date), MAX(session_date) FROM sessions").fetchone()
        return {"sessions": n, "first": first, "last": last, "path": str(movers_store.path())}
    finally:
        db.close()


def _rvol_status() -> dict[str, Any]:
    from market_reads import rvol_store
    try:
        return rvol_store.status()
    except Exception as exc:  # noqa: BLE001 -- as above
        return {"error": f"{type(exc).__name__}: {exc}"}


def _signals_status() -> dict[str, Any]:
    from market_reads import signals_store
    try:
        return signals_store.status()
    except Exception as exc:  # noqa: BLE001 -- as above
        return {"error": f"{type(exc).__name__}: {exc}"}


def _boards_status() -> dict[str, Any]:
    from leaderboard import store as board_store
    try:
        db = board_store.read_only()
    except Exception as exc:  # noqa: BLE001 -- as above
        return {"error": f"{type(exc).__name__}: {exc}"}
    if db is None:
        return {"error": "no store yet"}
    try:
        by_board = {board: {"days": n, "first": first, "last": last} for board, n, first, last in db.execute(
            "SELECT board, COUNT(DISTINCT session_date), MIN(session_date), MAX(session_date) FROM coverage"
            " GROUP BY board")}
        n, first, last = db.execute(
            "SELECT COUNT(DISTINCT session_date), MIN(session_date), MAX(session_date) FROM coverage").fetchone()
        return {"days": n, "first": first, "last": last, "by_board": by_board, "path": str(board_store.path())}
    finally:
        db.close()


# ---- the bulk index build -----------------------------------------------------------------------------------------
def _desc(day: str) -> str:
    """A sort key that orders ISO days newest first."""
    return "".join(chr(ord("9") - ord(c) + ord("0")) if c.isdigit() else c for c in day)


STOPPED = "stopped"
LOW_RAM = "low memory"          # a build that waited RAM_WAIT_SEC for free memory and never started
STAGE_DIR = "nova-index-stage"  # inside --stage: the copies, ours alone, cleared at the start of a run
STAGE_READ = 64 << 20           # the copy's reads off the hard drive


def _build_one(path_str: str, bulk_read: int, staged_str: str | None = None,
               ram_floor_gb: float = index_watch.RAM_FLOOR_GB,
               ram_wait_sec: float = index_watch.RAM_WAIT_SEC) -> tuple[str, str, float, int]:
    below_normal()
    path, root = Path(path_str), massive_files.root()
    staged = Path(staged_str) if staged_str else None
    t0 = time.monotonic()
    try:
        if (root / "sim" / "index" / INDEX_STOP).exists():       # each task checks: no task is ever left unrun
            return path_str, STOPPED, 0.0, 0
        if massive_index.is_current(path, root):
            return path_str, "current", 0.0, path.stat().st_size
        stop_file = root / "sim" / "index" / INDEX_STOP
        if not index_watch.wait_for_ram(ram_floor_gb, ram_wait_sec, stop_file):
            return path_str, LOW_RAM, time.monotonic() - t0, 0
        if stop_file.exists():                                    # it appeared while this build waited for memory
            return path_str, STOPPED, 0.0, 0
        if massive_index.build(path, root, bulk_read=bulk_read, read_from=staged) is not None:
            state = "built"
        elif massive_index.is_current(path, root):
            state = "current (another build finished it)"
        elif massive_index.path_for(path, root).with_name(f"{massive_index.path_for(path, root).name}.lock").exists():
            state = "skipped (another build holds it)"
        else:   # build() logs why and returns None when the index cannot be written (a full disk, a read-only folder)
            raise RuntimeError(f"{path_str}: the index was not saved, so this day still reads the slow way")
        return path_str, state, time.monotonic() - t0, path.stat().st_size
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def _copy(path: Path, stage: Path) -> Path:
    """``path`` copied to ``stage`` in one stream of big reads; the copy appears only once it is whole."""
    dst = stage / f"{path.parents[2].name}__{path.name}"
    part = dst.with_name(f"{dst.name}.part")
    buf = bytearray(STAGE_READ)
    view = memoryview(buf)
    with open(path, "rb", buffering=0) as src, open(part, "wb", buffering=0) as out:
        while n := src.readinto(buf):
            written = 0
            while written < n:
                written += out.write(view[written:n])
    os.replace(part, dst)
    return dst


class _Stager(threading.Thread):
    """Copies the files, in order and one at a time, off the hard drive to the stage folder and hands each copy to
    the pool, so the drive serves a single stream (6 builds reading it at once, 2026-10-12: 121 MB/s with the head
    busy; one stream: 213 MB/s). At most ``budget`` bytes of copies wait or build at once; a copy that cannot be
    made (a full stage) stops the copying, and the builds in progress finish."""

    def __init__(self, pool: ProcessPoolExecutor, files: list[Path], stage: Path, budget: int, stop_file: Path,
                 ram_floor_gb: float = index_watch.RAM_FLOOR_GB, ram_wait_sec: float = index_watch.RAM_WAIT_SEC):
        super().__init__(name="index-stager", daemon=True)
        self.pool, self.files, self.stage, self.budget, self.stop_file = pool, files, stage, budget, stop_file
        self.ram_floor_gb, self.ram_wait_sec = ram_floor_gb, ram_wait_sec
        self.futures: queue.Queue = queue.Queue()
        self.room = threading.Condition()
        self.held = 0
        self.stopped = self.broke = False
        self.broke_reason = ""
        self.skipped = 0

    def _release(self, size: int) -> None:
        with self.room:
            self.held -= size
            self.room.notify_all()

    def run(self) -> None:
        root = massive_files.root()
        try:
            for path in self.files:
                if self.stop_file.exists():
                    self.stopped = True
                    return
                if massive_index.is_current(path, root):     # built since the run started (an import, another run)
                    self.skipped += 1
                    continue
                size = path.stat().st_size
                with self.room:
                    self.room.wait_for(lambda: self.held == 0 or self.held + size <= self.budget)  # noqa: B023
                    self.held += size
                try:
                    copy = _copy(path, self.stage)
                except OSError as exc:
                    self._release(size)
                    self.broke = True
                    self.broke_reason = f"could not copy {path} to {self.stage} ({exc})"
                    log.warning("index: %s; no more files start", self.broke_reason)
                    return
                try:
                    future = self.pool.submit(_build_one, str(path), 0, str(copy), self.ram_floor_gb,
                                               self.ram_wait_sec)
                except RuntimeError as exc:   # a broken pool (a worker died): nothing more can build
                    copy.unlink(missing_ok=True)
                    self._release(size)
                    self.broke = True
                    self.broke_reason = f"the builds stopped ({exc})"
                    log.warning("index: %s; no more files start", self.broke_reason)
                    return
                future.add_done_callback(lambda _f, size=size: self._release(size))
                self.futures.put(future)
        finally:
            self.futures.put(None)

    def completed(self):
        """Each build as it finishes, until the copying is over and every build it handed out has finished."""
        pending: set = set()
        feeding = True
        while feeding or pending:
            try:
                while feeding:
                    item = self.futures.get(timeout=0 if pending else 0.5)
                    if item is None:
                        feeding = False
                    else:
                        pending.add(item)
            except queue.Empty:
                pass
            if pending:
                done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                yield from done


def _clear_stage(stage: Path) -> None:
    """The copies a run that ended without cleaning up left behind (only ours: the stage folder is ours)."""
    for left in [*stage.glob("*__*.csv.gz"), *stage.glob("*__*.csv.gz.part")]:
        left.unlink(missing_ok=True)


def todo(datasets: list[str], start: str | None, end: str | None, oldest_first: bool) -> list[Path]:
    """The day files without a current index: a day at a time (minutes, trades, quotes), newest day first."""
    root = massive_files.root()
    keyed = [(path.name[:10], rank, path) for rank, dataset in enumerate(datasets)
             for path in day_files(dataset, start, end)]
    keyed.sort(key=lambda item: (item[0] if oldest_first else _desc(item[0]), item[1]))
    return [path for _day, _rank, path in keyed if not massive_index.is_current(path, root)]


def build_indexes(datasets: list[str], *, workers: int, read_mb: int, start: str | None = None,
                  end: str | None = None, oldest_first: bool = False, stage: Path | None = None,
                  stage_gb: float = 40.0, ram_floor_gb: float = index_watch.RAM_FLOOR_GB,
                  streak_halt: int = index_watch.FAILURE_STREAK_HALT,
                  ram_wait_sec: float = index_watch.RAM_WAIT_SEC) -> int:
    """Build every missing index, ``workers`` files at a time; the number that failed. Logged to the index folder.

    Stops after the files in progress when ``<root>/sim/index/STOP`` appears: every task left checks the file and
    returns at once, so the run ends. (Cancelling the pool's queue instead left a task it had already handed out
    unrun, and the run waited on it forever, 2026-10-12.) Resumable: a rerun skips what is built.

    ``stage``: a folder on another drive (an SSD). Each file is copied there in one stream, at most ``stage_gb`` of
    copies at a time, and built from the copy, which is deleted after (``_Stager``); without it the builds read the
    day files where they are.

    Watched (``index_watch``, 2026-10-13): each file gets a fresh worker process, so none grows over a long run; a
    build starts only with ``ram_floor_gb`` of memory free and halts the run when none frees up; ``streak_halt``
    failures in a row halt it; every progress line counts the failures; ``<root>/sim/index/index-status.json`` says
    what the run is doing; the first failure, a halt and the end raise a Windows notification.
    """
    below_normal()
    root = massive_files.root()
    log_path = root / "sim" / "index" / INDEX_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    files = todo(datasets, start, end, oldest_first)
    total = sum(path.stat().st_size for path in files)
    stop_file = log_path.parent / INDEX_STOP
    stop_file.unlink(missing_ok=True)
    if stage is not None:
        stage = stage / STAGE_DIR
        stage.mkdir(parents=True, exist_ok=True)
        _clear_stage(stage)
    log.info("index: %d day files to index (%.1f GB of gzip) in %s, %d workers, %s", len(files), total / 1e9,
             ",".join(datasets), workers,
             f"copied one at a time to {stage} ({stage_gb:g} GB at most)" if stage else f"{read_mb} MB reads")
    log.info("index: pid %d; to stop after the files in progress, create %s; halts after %d failures in a row or "
             "%.0f min below %g GB of free memory", os.getpid(), stop_file, streak_halt,
             ram_wait_sec / 60, ram_floor_gb)
    watch = index_watch.Watch(log_path.parent, stop_file, len(files), total, workers, streak_halt)
    done_bytes, t0, failed, stopped, finished = 0, time.monotonic(), 0, 0, 0
    stager = None
    # A fresh worker per file (3.11+): the 2026-10-13 run's long-lived workers grew until builds could not start.
    fresh = {"max_tasks_per_child": 1} if sys.version_info >= (3, 11) else {}
    with ProcessPoolExecutor(workers, **fresh) as pool:
        if stage is None:
            results = as_completed([pool.submit(_build_one, str(path), read_mb << 20, None, ram_floor_gb, ram_wait_sec)
                                    for path in files])
        else:
            stager = _Stager(pool, files, stage, int(stage_gb * 1e9), stop_file, ram_floor_gb, ram_wait_sec)
            stager.start()
            results = stager.completed()
        for future in results:
            try:
                path_str, state, secs, size = future.result()
            except Exception as exc:  # noqa: BLE001 -- one bad file is logged; the rest go on
                failed += 1
                log.warning("index: a build failed (%d so far): %s: %s", failed, type(exc).__name__, exc)
                watch.failed(f"{type(exc).__name__}: {exc}")
                continue
            if state == LOW_RAM:
                watch.halt(f"less than {ram_floor_gb:g} GB of memory free for {ram_wait_sec / 60:.0f} "
                           f"min before {path_str}")
                stopped += 1
                continue
            if state == STOPPED:
                if not stopped:
                    log.info("index: %s found; finishing the files in progress, starting no more", stop_file)
                stopped += 1
                continue
            finished += 1
            done_bytes += size
            rate = done_bytes / max(time.monotonic() - t0, 1e-6)
            left = (total - done_bytes) / rate if rate else 0
            log.info("index: %s %s in %.0f s; %.1f of %.1f GB, %.0f MB/s, about %.1f h left, %d failed", path_str,
                     state, secs, done_bytes / 1e9, total / 1e9, rate / 1e6, left / 3600, failed)
            watch.built(path_str, done_bytes, rate, left)
    if stager is not None:
        stager.join()
        if stager.broke:
            failed += 1
            watch.run_failed(stager.broke_reason)
        unstarted = len(files) - finished - failed - stager.skipped
        stopped = unstarted if (stager.stopped or stager.broke or stopped) else 0
    log.info("index: %s, %d failed", f"stopped with {stopped} files left" if stopped else "finished", failed)
    watch.finish("halted" if watch.halted.is_set() else "stopped" if stopped else "finished", stopped)
    return max(failed, 1) if watch.halted.is_set() else failed    # a halt (low memory too) never exits 0
