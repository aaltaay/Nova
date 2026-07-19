#!/usr/bin/env python3
"""Backfill archive bars_1m from existing tape_ibkr rows, then re-compact.

Usage (repo root):
  py -3 tools/archive_backfill_bars_from_tape.py --dates 2026-07-15,2026-07-16
  py -3 tools/archive_backfill_bars_from_tape.py --dates 2026-07-15 --compact
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dates", required=True, help="Comma-separated ET session dates")
    p.add_argument(
        "--compact",
        action="store_true",
        help="Re-run compact_day after backfill (updates cold JSONL)",
    )
    args = p.parse_args()
    dates = [d.strip() for d in args.dates.split(",") if d.strip()]

    from archive import bar_builder
    from archive import db as archive_db

    archive_db.init_db()
    total = 0
    for day in dates:
        n = bar_builder.backfill_session_date(day)
        print(f"{day}: flushed {n} open buckets; bars written via upsert")
        total += n
        if args.compact:
            from archive import compact

            result = compact.compact_day(day)
            print(f"{day}: compact -> {result}")
    print(f"done dates={len(dates)} flush_calls={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
