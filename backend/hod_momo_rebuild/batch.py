"""Many rebuilt days in a row: every calendar day of a range, each built in the desk's own worker process.

    python -m hod_momo_rebuild.batch --start 2021-09-21 --end 2026-10-16 [--workers 2] [--oldest-first]

Newest day first unless ``--oldest-first``; at most ``--workers`` builds at once (each its own ``worker`` process,
below normal priority, under the build's memory cap). A day the desk would refuse (``job.unavailable_reason``, no
rebuilt boards), a day built and current (its fingerprint against the boards and the HOD settings now) and a day
another process is building are skipped with the reason, so running the batch again resumes where it stopped. A
``STOP`` file in the batch folder starts no further day: running days finish, then the batch removes the file and
ends. One log per run in the batch folder: a line per day (outcome, build and wall seconds, prints, alerts) and the
totals. Rules: ``architecture/schema/scanner.md``, "Many rebuilt days in a row".
"""
from __future__ import annotations

import argparse
import logging
import statistics
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date as date_cls, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from constants_hod_momo import (
    HOD_MOMO_REBUILD_BATCH_POLL_SEC,
    HOD_MOMO_REBUILD_BATCH_STOP_FILE,
    HOD_MOMO_REBUILD_BATCH_SUBDIR,
    HOD_MOMO_REBUILD_STALE_SEC,
)
from constants_leaderboard import (
    LEADERBOARD_SECONDS_ACTIVE,
    LEADERBOARD_SECONDS_FAILED,
    LEADERBOARD_SECONDS_QUEUED,
    LEADERBOARD_SECONDS_READY,
)
from hod_momo_rebuild import job, store

logger = logging.getLogger("hod_momo_rebuild.batch")
BUILT = "built and current"
BUSY = "another process is building it"
_SETTINGS_TTL_SEC = 600.0          # the HOD settings are read again this often (a change makes later days differ)


class _Process(Protocol):
    def poll(self) -> int | None: ...


@dataclass
class Tally:
    built: list[tuple[str, float]] = field(default_factory=list)      # (day, build_sec)
    failed: list[str] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)                 # reason -> days
    stopped: bool = False


def days_between(start: str, end: str, *, newest_first: bool = True) -> list[str]:
    """Every calendar day from ``start`` to ``end``, both included."""
    first, last = date_cls.fromisoformat(store.day_key(start)), date_cls.fromisoformat(store.day_key(end))
    if last < first:
        raise ValueError("the range ends before it starts")
    out = [(first + timedelta(days=n)).isoformat() for n in range((last - first).days + 1)]
    return out[::-1] if newest_first else out


def folder() -> Path:
    return store.folder() / HOD_MOMO_REBUILD_BATCH_SUBDIR


def stop_path() -> Path:
    return folder() / HOD_MOMO_REBUILD_BATCH_STOP_FILE


def settings_digest() -> str:
    """The operator's HOD settings as a build reads them: a freshly loaded engine's ``config_digest``, nothing saved
    (this process's engine is never loaded otherwise, and an unloaded one would read the defaults)."""
    from hod_momo_rebuild import engine

    with engine.no_saves():
        engine.fresh_engine()
        return engine.config_digest()


def skip_reason(day: str, settings: Callable[[], str]) -> str | None:
    """Why the batch leaves ``day`` alone, or None to build it."""
    why = job.unavailable_reason(day)
    if why:
        return why
    mark = job.current_fingerprint(day, fresh=True, settings=settings())
    if mark is None:
        return job.NOT_REBUILT
    record = store.read_job(day) or {}
    status = record.get("status")
    if status == LEADERBOARD_SECONDS_READY and record.get("fingerprint") == mark and store.data_path(day).is_file():
        return BUILT
    if (status in LEADERBOARD_SECONDS_ACTIVE
            and time.time() - float(record.get("updated_ts") or 0.0) <= HOD_MOMO_REBUILD_STALE_SEC):
        return BUSY
    return None


def _settings_reader(read: Callable[[], str]) -> Callable[[], str]:
    held: list[Any] = [None, 0.0]

    def current() -> str:
        if held[0] is None or time.monotonic() - held[1] > _SETTINGS_TTL_SEC:
            held[0], held[1] = read(), time.monotonic()
        return held[0]

    return current


def _finished(day: str, code: int, wall: float, tally: Tally, log: logging.Logger) -> None:
    record = store.read_job(day) or {}
    status = record.get("status")
    if status == LEADERBOARD_SECONDS_READY:
        summary = record.get("summary") or {}
        build = float(summary.get("build_sec") or wall)
        tally.built.append((day, build))
        log.info("%s: built in %.1f s (%.0f s wall): %s prints, %s watched, %s alerts, %s with a float",
                 day, build, wall, summary.get("prints"), summary.get("watched"), summary.get("alerts"),
                 summary.get("with_float"))
        return
    if status in LEADERBOARD_SECONDS_ACTIVE:          # the process died without saying why
        record = store.write_job(day, status=LEADERBOARD_SECONDS_FAILED, stage=None,
                                 error=f"The rebuild process ended before finishing (exit code {code})")
    tally.failed.append(day)
    log.warning("%s: failed after %.0f s wall (exit code %s): %s", day, wall, code, record.get("error"))


def run_batch(days: list[str], *, workers: int = 1, launch: Callable[[str], _Process] = job.spawn,
              settings: Callable[[], str] = settings_digest, poll_sec: float = HOD_MOMO_REBUILD_BATCH_POLL_SEC,
              log: logging.Logger = logger) -> Tally:
    """Build ``days`` in order, at most ``workers`` at once; what happened to each, tallied."""
    tally = Tally()
    pending = list(days)
    running: dict[str, tuple[_Process, float]] = {}
    current_settings = _settings_reader(settings)
    stop = stop_path()
    started = time.monotonic()
    while pending or running:
        if not tally.stopped and stop.exists():
            tally.stopped = True
            log.info("STOP file seen: no further day starts; %d running finish first, %d left for the next run",
                     len(running), len(pending))
        while not tally.stopped and pending and len(running) < max(1, workers):
            day = pending.pop(0)
            try:
                why = skip_reason(day, current_settings)
                if why:
                    tally.skipped[why] += 1
                    log.info("%s: skipped (%s)", day, why)
                    continue
                store.write_job(day, status=LEADERBOARD_SECONDS_QUEUED, stage=None, done=None, total=None,
                                started_ts=time.time(), finished_ts=None, error=None, summary=None, fingerprint=None)
                running[day] = (launch(day), time.monotonic())
            except Exception:  # one day's trouble is that day's: logged with its trace, the batch goes on
                log.exception("%s: could not start", day)
                tally.failed.append(day)
                continue
            log.info("%s: started (%d running, %d left)", day, len(running), len(pending))
        for day, (proc, began) in list(running.items()):
            code = proc.poll()
            if code is None:
                continue
            del running[day]
            _finished(day, code, time.monotonic() - began, tally, log)
        if tally.stopped and not running:
            break
        if running:
            time.sleep(poll_sec)
    if tally.stopped:
        stop.unlink(missing_ok=True)
    builds = [sec for _day, sec in tally.built]
    log.info("Batch %s after %.0f s: %d built, %d failed, %d skipped (%s); build seconds median %s, mean %s",
             "stopped" if tally.stopped else "done", time.monotonic() - started, len(tally.built),
             len(tally.failed), sum(tally.skipped.values()), dict(tally.skipped),
             round(statistics.median(builds), 1) if builds else None,
             round(statistics.fmean(builds), 1) if builds else None)
    return tally


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hod-rebuild-batch", description="Rebuild HOD Momo over a range of days.")
    parser.add_argument("--start", required=True, help="first day, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="last day, YYYY-MM-DD")
    parser.add_argument("--workers", type=int, default=1, help="builds at once, each its own process (default 1)")
    parser.add_argument("--oldest-first", action="store_true", help="oldest day first (default: newest first)")
    args = parser.parse_args(argv)
    from leaderboard.seconds.worker import lower_priority

    lower_priority()
    days = days_between(args.start, args.end, newest_first=not args.oldest_first)
    folder().mkdir(parents=True, exist_ok=True)
    log_path = folder() / f"batch-{datetime.now():%Y%m%d-%H%M%S}.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.WARNING, handlers=[handler])
    logger.setLevel(logging.INFO)
    print(log_path, flush=True)
    logger.info("Batch of %d days, %s to %s, %d at once (STOP file: %s)", len(days), days[0], days[-1],
                args.workers, stop_path())
    tally = run_batch(days, workers=args.workers)
    return 1 if tally.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
