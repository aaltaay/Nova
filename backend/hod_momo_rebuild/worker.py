"""One build of a rebuilt day's HOD Momo alerts, run out of the API process.

    python -m hod_momo_rebuild.worker --date YYYY-MM-DD
    nova-api.exe --hod-rebuild --date YYYY-MM-DD      (the frozen desk)

The build reads trades for minutes and runs the HOD Momo engine over millions of ticks with its clock pinned
(``time.time`` replaced): in the API process that would share the GIL with the desk's Level 2, tape and orders
(ADR 045) and hand the live engine a false clock, so it runs here, below normal priority and memory capped (the
Gappers-by-the-second build's cap), and talks to the API only through its job file.
"""
from __future__ import annotations

import argparse
import logging
import os

from constants_leaderboard import LEADERBOARD_SECONDS_FAILED, LEADERBOARD_SECONDS_MEMORY_ENV


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hod-rebuild")
    parser.add_argument("--hod-rebuild", action="store_true")
    parser.add_argument("--date", required=True)
    args = parser.parse_args(argv)
    from leaderboard.seconds.worker import cap_memory, lower_priority

    lower_priority()
    try:
        from paths import log_dir

        logging.basicConfig(filename=str(log_dir() / "hod_rebuild.log"), level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    except Exception:
        logging.basicConfig(level=logging.INFO)
    cap_mb = cap_memory()
    from hod_momo_rebuild import run, store

    log = logging.getLogger("hod_momo_rebuild.worker")
    log.info("HOD rebuild for %s starts (pid %s, memory cap %s MB)", args.date, os.getpid(), cap_mb)
    try:
        run.run(args.date)
    except Exception as exc:  # the job says why; the desk shows it
        log.exception("HOD rebuild for %s failed", args.date)
        error = str(exc) or type(exc).__name__
        if isinstance(exc, MemoryError) and cap_mb:
            error = (f"The build used its whole {cap_mb:,} MB memory cap and was stopped before writing anything "
                     f"({LEADERBOARD_SECONDS_MEMORY_ENV} raises it)")
        try:
            store.write_job(args.date, status=LEADERBOARD_SECONDS_FAILED, stage=None, error=error)
        except Exception:
            log.exception("HOD rebuild for %s: could not mark it failed", args.date)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
