"""One build of a rebuilt day's Gappers by the second, run out of the API process (ADR 023 amendment 2026-10-13).

    python -m leaderboard.seconds.worker --date YYYY-MM-DD
    nova-api.exe --board-seconds --date YYYY-MM-DD      (the frozen desk)

The build inflates the stocks' trades and parses them for seconds to minutes; in the API process that work would
share the GIL with the event loops that carry the desk's Level 2, tape and orders (ADR 045), so it runs here,
below normal priority and memory capped, and talks to the API only through its job file (``store.write_job``).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from constants_leaderboard import (
    LEADERBOARD_SECONDS_BOARD,
    LEADERBOARD_SECONDS_FAILED,
    LEADERBOARD_SECONDS_MEMORY_ENV,
    LEADERBOARD_SECONDS_MEMORY_MB,
)


def lower_priority() -> None:
    try:
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.kernel32.SetPriorityClass(ctypes.c_void_p(-1), 0x00004000)   # BELOW_NORMAL_PRIORITY_CLASS
        else:
            os.nice(10)
    except Exception:
        logging.getLogger(__name__).warning("board seconds: could not lower its priority", exc_info=True)


def cap_memory() -> int | None:
    """Cap the build's committed memory; the cap in MB, or None when there is none (logged, never assumed)."""
    log = logging.getLogger(__name__)
    raw = os.environ.get(LEADERBOARD_SECONDS_MEMORY_ENV, "").strip()
    try:
        cap_mb = int(raw) if raw else LEADERBOARD_SECONDS_MEMORY_MB
    except ValueError:
        log.warning("board seconds: %s=%r is not a whole number of MB; the cap stays %d MB",
                    LEADERBOARD_SECONDS_MEMORY_ENV, raw, LEADERBOARD_SECONDS_MEMORY_MB)
        cap_mb = LEADERBOARD_SECONDS_MEMORY_MB
    if cap_mb <= 0:
        return None
    try:
        from winapi import job_limit

        if not job_limit.cap_this_process(cap_mb * 2**20):
            return None
    except Exception:
        log.warning("board seconds: could not cap its memory at %d MB; it runs uncapped", cap_mb, exc_info=True)
        return None
    return cap_mb


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="board-seconds")
    parser.add_argument("--board-seconds", action="store_true")
    parser.add_argument("--date", required=True)
    args = parser.parse_args(argv)
    lower_priority()
    try:
        from paths import log_dir

        logging.basicConfig(filename=str(log_dir() / "board_seconds.log"), level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    except Exception:
        logging.basicConfig(level=logging.INFO)
    cap_mb = cap_memory()
    from leaderboard.seconds import run, store

    log = logging.getLogger("leaderboard.seconds.worker")
    log.info("Gappers by the second for %s starts (pid %s, memory cap %s MB)", args.date, os.getpid(), cap_mb)
    try:
        run.run(args.date)
    except Exception as exc:  # the job says why; the desk shows it
        log.exception("Gappers by the second for %s failed", args.date)
        error = str(exc) or type(exc).__name__
        if isinstance(exc, MemoryError) and cap_mb:
            error = (f"The build used its whole {cap_mb:,} MB memory cap and was stopped before writing anything "
                     f"({LEADERBOARD_SECONDS_MEMORY_ENV} raises it)")
        try:
            store.write_job(args.date, LEADERBOARD_SECONDS_BOARD, status=LEADERBOARD_SECONDS_FAILED, stage=None,
                            error=error)
        except Exception:
            log.exception("Gappers by the second for %s: could not mark it failed", args.date)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
