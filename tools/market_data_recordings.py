"""The recorded-session subcommands of ``tools/market_data.py`` (ADR 059, #1064): Nova's own IBKR recordings, split
along the same seam as the MCP's ``nova_data_recordings.py``. ``add_parsers`` registers them; ``HANDLERS`` runs them.
Read-only on the desk's stores; each read takes a heavy-read slot. Times are ET.

  py -3 tools/market_data.py recorded-depth GRML 2026-10-14 --at 09:31:30
  py -3 tools/market_data.py recorded-depth GRML 2026-10-14 --at 09:31:30 --source capture --max-age 300
  py -3 tools/market_data.py recorded-tape GRML 2026-10-14 --from 09:31 --to 09:35
  py -3 tools/market_data.py recorded-tape GRML 2026-10-14 --source archive --limit 50000 --out grml.parquet
"""
from __future__ import annotations

import json


def cmd_depth(args, show) -> int:
    from market_reads import recordings
    print(json.dumps(recordings.depth(args.symbol, args.day, args.at, args.source, args.max_age), default=str, indent=1))
    return 0


def cmd_tape(args, show) -> int:
    from market_reads import recordings
    return show(recordings.tape(args.symbol, args.day, args.start, args.end, args.source, args.limit), args)


HANDLERS = {"recorded-depth": cmd_depth, "recorded-tape": cmd_tape}


def add_parsers(sub, output) -> None:
    depth = sub.add_parser("recorded-depth", help="Nova's recorded Level 2 book at an ET moment")
    depth.add_argument("symbol")
    depth.add_argument("day", help="YYYY-MM-DD (the ET calendar day)")
    depth.add_argument("--at", required=True, help="ET HH:MM or HH:MM:SS: the newest book at or before it")
    depth.add_argument("--source", default="auto", choices=["auto", "capture", "l2_db"],
                       help="auto = the newer of a Session Record and l2.db")
    depth.add_argument("--max-age", dest="max_age", type=float, default=60.0,
                       help="seconds before --at a book still counts (default 60, at most 3600)")
    tape = sub.add_parser("recorded-tape", help="Nova's recorded prints in an ET window")
    tape.add_argument("symbol")
    tape.add_argument("day", help="YYYY-MM-DD (the ET calendar day)")
    tape.add_argument("--from", dest="start", help="ET HH:MM[:SS], inclusive (default: the start of the day)")
    tape.add_argument("--to", dest="end", help="ET HH:MM[:SS], exclusive (default: the end of the day)")
    tape.add_argument("--source", default="auto", choices=["auto", "capture", "archive"],
                      help="auto = a Session Record when one exists for the symbol-day, else the archive")
    tape.add_argument("--limit", type=int, default=200_000, help="at most this many rows (up to 1,000,000)")
    output(tape)
