"""What is on disk, and the bulk build of the seek indexes that make any stock-day read in about a second."""
from __future__ import annotations

import ctypes
import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from market_reads import REPO  # noqa: F401  (puts backend/ on sys.path)

from constants_sim import SIM_MASSIVE_MINUTES, SIM_MASSIVE_QUOTES, SIM_MASSIVE_TRADES
from sim import massive_files, massive_index

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
    """Each dataset's days and indexed days, the day movers index and the past-day boards."""
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
    out["movers_index"] = _movers_status()
    out["boards"] = _boards_status()
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


def _build_one(path_str: str, bulk_read: int) -> tuple[str, str, float, int]:
    below_normal()
    path, root = Path(path_str), massive_files.root()
    t0 = time.monotonic()
    if (root / "sim" / "index" / INDEX_STOP).exists():       # each task checks: no task is ever left unrun
        return path_str, STOPPED, 0.0, 0
    if massive_index.is_current(path, root):
        return path_str, "current", 0.0, path.stat().st_size
    if massive_index.build(path, root, bulk_read=bulk_read) is not None:
        state = "built"
    elif massive_index.is_current(path, root):
        state = "current (another build finished it)"
    elif massive_index.path_for(path, root).with_name(f"{massive_index.path_for(path, root).name}.lock").exists():
        state = "skipped (another build holds it)"
    else:   # build() logs why and returns None when the index cannot be written (a full disk, a read-only folder)
        raise RuntimeError(f"{path_str}: the index was not saved, so this day still reads the slow way")
    return path_str, state, time.monotonic() - t0, path.stat().st_size


def todo(datasets: list[str], start: str | None, end: str | None, oldest_first: bool) -> list[Path]:
    """The day files without a current index: a day at a time (minutes, trades, quotes), newest day first."""
    root = massive_files.root()
    keyed = [(path.name[:10], rank, path) for rank, dataset in enumerate(datasets)
             for path in day_files(dataset, start, end)]
    keyed.sort(key=lambda item: (item[0] if oldest_first else _desc(item[0]), item[1]))
    return [path for _day, _rank, path in keyed if not massive_index.is_current(path, root)]


def build_indexes(datasets: list[str], *, workers: int, read_mb: int, start: str | None = None,
                  end: str | None = None, oldest_first: bool = False) -> int:
    """Build every missing index, ``workers`` files at a time; the number that failed. Logged to the index folder.

    Stops after the files in progress when ``<root>/sim/index/STOP`` appears: every task left checks the file and
    returns at once, so the run ends. (Cancelling the pool's queue instead left a task it had already handed out
    unrun, and the run waited on it forever, 2026-10-12.) Resumable: a rerun skips what is built.
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
    log.info("index: %d day files to index (%.1f GB of gzip) in %s, %d workers, %d MB reads", len(files),
             total / 1e9, ",".join(datasets), workers, read_mb)
    log.info("index: pid %d; to stop after the files in progress, create %s", os.getpid(), stop_file)
    done_bytes, t0, failed, stopped = 0, time.monotonic(), 0, 0
    with ProcessPoolExecutor(workers) as pool:
        futures = [pool.submit(_build_one, str(path), read_mb << 20) for path in files]
        for future in as_completed(futures):
            try:
                path_str, state, secs, size = future.result()
            except Exception as exc:  # noqa: BLE001 -- one bad file is logged; the rest go on
                failed += 1
                log.warning("index: a build failed: %s: %s", type(exc).__name__, exc)
                continue
            if state == STOPPED:
                if not stopped:
                    log.info("index: %s found; finishing the files in progress, starting no more", stop_file)
                stopped += 1
                continue
            done_bytes += size
            rate = done_bytes / max(time.monotonic() - t0, 1e-6)
            left = (total - done_bytes) / rate if rate else 0
            log.info("index: %s %s in %.0f s; %.1f of %.1f GB, %.0f MB/s, about %.1f h left", path_str, state,
                     secs, done_bytes / 1e9, total / 1e9, rate / 1e6, left / 3600)
    log.info("index: %s, %d failed", f"stopped with {stopped} files left" if stopped else "finished", failed)
    return failed
