#!/usr/bin/env python3
"""Run the book watcher (ADR 033) over a Session Record: what it would have flagged.

The same detector the live desk runs (``backend/book_watch/detector.py``), fed
the recording's ``l2.jsonl`` and ``prints.jsonl`` in arrival order: resting
size that traded away (filled) against size that left without trading
(pulled), the large pulls, and the flags -- hints consistent with spoofing,
never a detection. Recordings made before ADR 033 kept at most 8 books a
second, so their drops span longer gaps; the report prints the rate it read.

Usage:

  py -3 tools/book_watch_replay.py F:\\Nova\\sim_capture\\2026-09-24\\GCTK
  py -3 tools/book_watch_replay.py <recording dir> [--flags 20] [--json]

Read-only: it never writes.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from book_watch.constants_book_watch import BOOK_WATCH_CAVEATS, BOOK_WATCH_NOTE  # noqa: E402
from book_watch.replay import replay  # noqa: E402

ET = ZoneInfo("America/New_York")


def _et(ts: float | None) -> str:
    return "-" if ts is None else datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S")


def render(result: dict, flags: int) -> str:
    lines = [
        f"{result['symbol']}  {result['dir']}",
        f"  {_et(result['first_ts'])}-{_et(result['last_ts'])} ET  books {result['books']:,}"
        f" ({result['books_per_sec']} a second)  prints {result['prints']:,}",
        f"  filled {result['filled_shares']:,.0f} shares in {result['fills']:,} drops;"
        f" pulled {result['pulled_shares']:,.0f} in {result['pulls']:,}",
        f"  large pulls {len(result['large_pulls']):,}  flags {len(result['flags']):,}",
    ]
    for flag in result["flags"][:flags]:
        lines.append(f"    {_et(flag['ts'])}  {flag['kind']:<19} {flag['why']}")
    if len(result["flags"]) > flags:
        lines.append(f"    ... {len(result['flags']) - flags} more (--flags N)")
    lines.append(f"  {BOOK_WATCH_NOTE}")
    lines += [f"  - {caveat}" for caveat in BOOK_WATCH_CAVEATS]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("dir", help="a Session Record directory (holds l2.jsonl and prints.jsonl)")
    parser.add_argument("--flags", type=int, default=20, help="flags to list (default 20)")
    parser.add_argument("--json", action="store_true", help="the whole result as JSON")
    args = parser.parse_args(argv)
    directory = Path(args.dir)
    if not (directory / "l2.jsonl").is_file():
        print(f"No l2.jsonl in {directory}", file=sys.stderr)
        return 2
    result = replay(directory)
    if args.json:
        print(json.dumps(result, default=str))
    else:
        print(render(result, args.flags))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
