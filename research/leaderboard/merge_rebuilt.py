"""Copy rebuilt days from staging stores into Nova's leaderboard store, a few minutes of a day per transaction.

Why (2026-10-12): the live recorder writes the same store all session, gives up on a write after
``LEADERBOARD_SQLITE_TIMEOUT_SEC`` and loses that batch (``leaderboard/queue.py``). A ten-year rebuild
writing an hour of a day per transaction from several processes would hold the store's lock long enough
to cost recorded minutes. So the rebuilds build into their own stores (``build_leaderboard.py --db``),
in parallel, and this copies each day they finished into the store in short transactions -- rows and
coverage of ``--minutes`` boundaries at a time -- with a pause between them. A day already whole in the
store is skipped; a day the store holds in part (an older rebuild) is replaced chunk by chunk.

Usage (from the repo root):
    py -3 research/leaderboard/merge_rebuilt.py --stage F:/Nova/leaderboard/staging/a.sqlite3 --stage ...
    py -3 research/leaderboard/merge_rebuilt.py --stage ... --loop 600     # again every 10 min until stopped
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lb_config import BACKEND_DIR  # noqa: E402

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import build_leaderboard  # noqa: E402
from constants_leaderboard import LEADERBOARD_SOURCE_RECONSTRUCTED  # noqa: E402
from leaderboard import store  # noqa: E402
from leaderboard.schema import COVERAGE_COLUMNS, ROW_COLUMNS  # noqa: E402

MINUTES_PER_TRANSACTION = 10
PAUSE_SEC = 0.2
SOURCE = LEADERBOARD_SOURCE_RECONSTRUCTED


def merge_day(db: sqlite3.Connection, day: str, minutes: int = MINUTES_PER_TRANSACTION,
              pause: float = PAUSE_SEC) -> int:
    """Copy one reconstructed day from the attached ``stage`` into ``main``; the rows copied."""
    stamps = [r[0] for r in db.execute(
        "SELECT DISTINCT minute_ts FROM stage.coverage WHERE session_date = ? AND source = ? ORDER BY minute_ts",
        (day, SOURCE))]
    rows_cols, cov_cols = ", ".join(ROW_COLUMNS), ", ".join(COVERAGE_COLUMNS)
    copied = 0
    for i in range(0, len(stamps), max(1, minutes)):
        lo, hi = stamps[i], stamps[min(i + minutes, len(stamps)) - 1]
        with db:                # an older rebuild's rows of these minutes go in the same short transaction
            for table in ("rows", "coverage"):
                db.execute(f"DELETE FROM main.{table} WHERE session_date = ? AND source = ?"
                           " AND minute_ts BETWEEN ? AND ?", (day, SOURCE, lo, hi))
            copied += db.execute(
                f"INSERT OR REPLACE INTO main.rows ({rows_cols}) SELECT {rows_cols} FROM stage.rows"
                " WHERE session_date = ? AND source = ? AND minute_ts BETWEEN ? AND ?", (day, SOURCE, lo, hi)).rowcount
            db.execute(
                f"INSERT OR REPLACE INTO main.coverage ({cov_cols}) SELECT {cov_cols} FROM stage.coverage"
                " WHERE session_date = ? AND source = ? AND minute_ts BETWEEN ? AND ?", (day, SOURCE, lo, hi))
        if pause:
            time.sleep(pause)
    return copied


def merge(stages: list[Path], database: Path | None = None, *, minutes: int = MINUTES_PER_TRANSACTION,
          pause: float = PAUSE_SEC, log=print) -> int:
    """Every day whole in a staging store and not whole in the store; the days copied."""
    done = build_leaderboard.complete_days(database)
    merged = 0
    for stage in stages:
        if not stage.is_file():
            log(f"{stage}: no staging store yet")
            continue
        ready = sorted(build_leaderboard.complete_days(stage) - done, reverse=True)
        if not ready:
            continue
        log(f"{stage}: {len(ready)} days to copy")
        with store.connect(database) as db:
            db.execute("ATTACH DATABASE ? AS stage", (str(stage),))
            try:
                for day in ready:
                    t0 = time.monotonic()
                    rows = merge_day(db, day, minutes, pause)
                    done.add(day)
                    merged += 1
                    log(f"{day}: {rows} rows copied from {stage.name} in {time.monotonic() - t0:.1f} s")
            finally:
                db.execute("DETACH DATABASE stage")
    return merged


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--stage", type=Path, action="append", required=True, help="a staging store (repeat)")
    ap.add_argument("--db", type=Path, default=None, help=f"the store (default {store.path()})")
    ap.add_argument("--minutes", type=int, default=MINUTES_PER_TRANSACTION, help="boundaries per transaction")
    ap.add_argument("--pause", type=float, default=PAUSE_SEC, help="seconds between transactions")
    ap.add_argument("--loop", type=float, default=0, help="merge again every this many seconds (0: once)")
    args = ap.parse_args(argv)

    def log(line: str) -> None:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}", flush=True)

    while True:
        merged = merge(args.stage, args.db, minutes=args.minutes, pause=args.pause, log=log)
        log(f"merged {merged} days")
        if not args.loop:
            return 0
        time.sleep(args.loop)


if __name__ == "__main__":
    sys.exit(main())
