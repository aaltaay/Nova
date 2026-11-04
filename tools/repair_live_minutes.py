#!/usr/bin/env python3
"""Correct the live 1-minute volumes master's builder got wrong -- a dry run unless --apply.

The rule and its limits are ``backend/archive/live_minute_repair.py``: a stored live minute moves only when
it carries a fingerprint of the two defects (cut down to its last updates, or counted a second counter's
return), to the builder's own count from ``l1_ticks``; IBKR's history rows are never touched. The dry run
opens ``archive.db`` read-only. ``--apply`` writes in short batches, each row only if it still holds the
volume the plan read.

Usage (repo root; pass the desk's cache -- a worktree's own ``backend/.cache`` has no archive):
  py -3 tools/repair_live_minutes.py --cache C:/Users/<you>/github/Nova/backend/.cache
  py -3 tools/repair_live_minutes.py --cache ... --day 2026-11-04
  py -3 tools/repair_live_minutes.py --cache ... --apply
  py -3 tools/repair_live_minutes.py --cache ... --json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from archive import live_minute_repair as repair  # noqa: E402
from constants import ARCHIVE_DB_FILENAME  # noqa: E402


def _below_normal() -> None:
    """The desk shares this PC: a long read yields to it."""
    try:
        import psutil

        proc = psutil.Process()
        proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS") else 10)
    except Exception as exc:  # noqa: BLE001 -- the run goes on at normal priority, and says so
        print(f"(normal priority: {exc})", file=sys.stderr)


def _connect(db: Path, *, write: bool) -> sqlite3.Connection:
    if write:
        conn = sqlite3.connect(str(db), timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn
    return sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=30)


def _print(result: dict) -> None:
    cols = ("whole", "fragment", "phantom", "other", "gap", "no_ticks", "recent")
    print(f"{'day':10} " + " ".join(f"{c:>8}" for c in cols) + f" {'shares added':>15} {'shares removed':>15}")
    for row in [*result["days"], {"day": "all", **result["totals"]}]:
        print(f"{row['day']:10} " + " ".join(f"{row[c]:8}" for c in cols)
              + f" {row['shares_added']:15,} {row['shares_removed']:15,}")
    if result["top"]:
        print("most shares moved:")
        for row in result["top"]:
            print(f"  {row['day']} {row['symbol']:6} {row['shares_moved']:>14,}")
    print("written:", "nothing (dry run)" if result["applied"] is None else f"{result['applied']:,} rows")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=Path, help="the desk's backend/.cache (holds archive.db)")
    parser.add_argument("--day", action="append", help="YYYY-MM-DD; repeat for several (default: every day)")
    parser.add_argument("--apply", action="store_true", help="write the raises (default: dry run)")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)

    if args.cache is None:
        from paths import cache_root

        args.cache = Path(cache_root())
    db = args.cache / ARCHIVE_DB_FILENAME
    if not db.is_file():
        print(f"no archive at {db}", file=sys.stderr)
        return 2
    _below_normal()
    conn = _connect(db, write=args.apply)
    try:
        days = repair.live_days(conn)
        if args.day:
            days = {d: days.get(d, []) for d in args.day}
        now = time.time()
        plans = [repair.plan_day(conn, day, symbols, now=now) for day, symbols in days.items()]
        applied = repair.apply(conn, [c for p in plans for c in p.changes]) if args.apply else None
    finally:
        conn.close()
    result = repair.report(plans, applied=applied)
    if args.json:
        print(json.dumps(result, indent=1))
    else:
        _print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
