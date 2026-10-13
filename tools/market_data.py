#!/usr/bin/env python3
"""The market data front door: what the operator's Massive files and Nova's stores hold, and one stock-day out of them.

Agents start here instead of writing a reader (``docs/market-data.md`` is the catalog and the traps). Read-only on the
data; ``index`` writes only the seek indexes the Sim's own reader keeps (ADR 046). The library is
``research/market_reads`` (Python: ``from market_reads import reads``).

  status    What is on disk: each dataset's days and how many are indexed, the day movers index, the past-day boards.
  index     Build the missing seek indexes (newest day first), so any stock-day reads in about a second.
  trades    One stock-day's trades, every column as delivered, in a window; to the screen or a .parquet / .csv file.
  quotes    One stock-day's NBBO (one best bid and offer across venues; Level 1, never depth).
  bars      One stock-day's bars: minutes from the minute file, seconds built from its trades by the Sim's rules.
  movers    Search the day movers index with the agent endpoint's arguments (key=value), without the API.
  board     A past day's Scanner list at a minute, as the Sim plays it back (recorded, else rebuilt).
  splits    A stock's splits, and with --day the factor that puts that day's raw prices in today's terms.
  bench     Time each read on real files.

trades / quotes / bars are raw (the files are never split-adjusted); --adjust puts them in today's terms.

Usage (from the repo root):

  py -3 tools/market_data.py status
  py -3 tools/market_data.py index --workers 3
  py -3 tools/market_data.py index --workers 6 --stage C:\\Nova-stage   (each file copied to an SSD, then built)
  py -3 tools/market_data.py trades GME 2021-01-27 --from 09:30 --to 09:35 --out gme.parquet
  py -3 tools/market_data.py quotes GME 2021-01-27 --from 09:30 --to 09:31
  py -3 tools/market_data.py bars GME 2021-01-27 --tf 10s --from 09:30 --to 10:00
  py -3 tools/market_data.py movers date_from=2021-01-01 date_to=2021-12-31 high_min=100 price_max=20
  py -3 tools/market_data.py board 2026-09-09 --at 09:45 --list gainers --top 20
  py -3 tools/market_data.py splits GRML --day 2026-07-15
  py -3 tools/market_data.py bars GRML 2026-07-15 --tf 5m --adjust
  py -3 tools/market_data.py bench
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))

from market_reads import inventory  # noqa: E402

SHOW_ROWS = 15


def _show(frame, args) -> int:
    """Write ``--out`` (.parquet / .csv), else print what was read and its first rows."""
    meta = {k: v for k, v in getattr(frame, "attrs", {}).items() if k != "file"}
    if args.out:
        out = Path(args.out)
        frame.to_parquet(out, index=False) if out.suffix == ".parquet" else frame.to_csv(out, index=False)
        print(json.dumps({**meta, "rows": len(frame), "out": str(out)}, default=str))
        return 0
    print(json.dumps({**meta, "rows": len(frame)}, default=str))
    if len(frame):
        print(frame.head(args.head).to_string(index=False))
    return 0


def cmd_status(args) -> int:
    out = inventory.status()
    if args.json or "unavailable" in out:
        print(json.dumps(out, indent=1))
        return 1 if "unavailable" in out else 0
    print(f"Massive files under {out['root']}")
    for dataset, row in out["datasets"].items():
        indexed = f"  indexed {row['indexed']:>5} of {row['days']}" if "indexed" in row else ""
        print(f"  {dataset:<15} {row['days']:>5} days  {row['first']} .. {row['last']}{indexed}")
    movers, boards = out["movers_index"], out["boards"]
    print(f"Day movers index: {movers.get('sessions', 0)} sessions  {movers.get('first')} .. {movers.get('last')}"
          + (f"  ({movers['error']})" if movers.get("error") else ""))
    print(f"Past-day boards: {boards.get('days', 0)} days  {boards.get('first')} .. {boards.get('last')}"
          + (f"  ({boards['error']})" if boards.get("error") else ""))
    for board, row in sorted((boards.get("by_board") or {}).items()):
        print(f"  {board:<11} {row['days']:>5} days  {row['first']} .. {row['last']}")
    return 0


def cmd_index(args) -> int:
    from sim import massive_index
    if not massive_index.available():
        print("indexed_gzip is not installed: py -3 -m pip install -r backend/requirements.txt", file=sys.stderr)
        return 2
    datasets = args.datasets.split(",") if args.datasets else list(inventory.DATASETS)
    stage = Path(args.stage) if args.stage else None
    return 1 if inventory.build_indexes(datasets, workers=args.workers, read_mb=args.read_mb, start=args.start,
                                        end=args.end, oldest_first=args.oldest_first, stage=stage,
                                        stage_gb=args.stage_gb) else 0


def _adjusted(frame, args):
    """The read in today's terms when ``--adjust`` asks; raw otherwise."""
    if not args.adjust:
        return frame
    from market_reads import splits
    return splits.adjust(frame, args.symbol, args.day)


def cmd_rows(args) -> int:
    from market_reads import reads
    read = {"trades": reads.trades, "quotes": reads.quotes}[args.cmd]
    return _show(_adjusted(read(args.symbol, args.day, args.start, args.end), args), args)


def cmd_bars(args) -> int:
    from market_reads import reads
    return _show(_adjusted(reads.bars(args.symbol, args.day, args.tf, args.start, args.end), args), args)


def cmd_splits(args) -> int:
    from market_reads import splits
    frame = splits.table(args.symbol)
    if args.day:
        frame.attrs.update(day=args.day, as_of=args.as_of or "latest",
                           price_factor=splits.factor(args.symbol, args.day, args.as_of))
    return _show(frame, args)


def cmd_movers(args) -> int:
    import pandas as pd

    from market_reads import reads
    params = dict(pair.split("=", 1) for pair in args.params)
    answer = reads.movers(**params)
    frame = pd.json_normalize(answer["rows"])
    frame.attrs.update(summary=answer.get("summary"), notes=answer.get("notes"), asked=answer.get("asked"))
    return _show(frame, args)


def cmd_board(args) -> int:
    from market_reads import reads
    frame = reads.board(args.day, args.at, args.list, args.source)
    if len(frame) and args.top:
        frame = frame.head(args.top)
    return _show(frame, args)


def cmd_bench(args) -> int:
    from market_reads import bench
    print(json.dumps(bench.run(args.day, args.symbol), indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    status = sub.add_parser("status", help="what is on disk")
    status.add_argument("--json", action="store_true")

    index = sub.add_parser("index", help="build the missing seek indexes")
    index.add_argument("--workers", type=int, default=3)
    index.add_argument("--read-mb", type=int, default=16,
                       help="buffer of the file object a build is handed; kept for older command lines, it changes "
                            "nothing (indexed_gzip reads through the file's descriptor)")
    index.add_argument("--stage", help="a folder on an SSD: copy each day file there in one stream and build from "
                                       "the copy, so the hard drive serves one reader; the copies are deleted as "
                                       "their builds finish")
    index.add_argument("--stage-gb", type=float, default=40.0, help="at most this many GB of copies at once")
    index.add_argument("--datasets", help=f"comma list, default {','.join(inventory.DATASETS)}")
    index.add_argument("--start", help="first day (YYYY-MM-DD)")
    index.add_argument("--end", help="last day (YYYY-MM-DD)")
    index.add_argument("--oldest-first", action="store_true")

    def output(p):
        p.add_argument("--out", help="write the table to this .parquet or .csv file")
        p.add_argument("--head", type=int, default=SHOW_ROWS, help="rows printed without --out")

    for name in ("trades", "quotes", "bars"):
        p = sub.add_parser(name)
        p.add_argument("symbol")
        p.add_argument("day", help="YYYY-MM-DD")
        p.add_argument("--from", dest="start", help="ET HH:MM, inclusive")
        p.add_argument("--to", dest="end", help="ET HH:MM, exclusive")
        if name == "bars":
            p.add_argument("--tf", default="1m", help="1m, 5m, 15m ... from the minute file; 1s, 10s ... from trades")
        p.add_argument("--adjust", action="store_true",
                       help="split-adjust to today's terms (prices x the factor, shares / it); raw without it")
        output(p)
    movers = sub.add_parser("movers", help="key=value arguments of /api/agent/movers")
    movers.add_argument("params", nargs="*")
    output(movers)
    board = sub.add_parser("board")
    board.add_argument("day")
    board.add_argument("--at", required=True, help="ET HH:MM")
    board.add_argument("--list", default="gainers", choices=["gainers", "losers", "gappers", "afterhours", "large_cap"])
    board.add_argument("--source", choices=["recorded", "reconstructed"])
    board.add_argument("--top", type=int, default=0)
    output(board)
    split = sub.add_parser("splits", help="a stock's splits and the factor for a day")
    split.add_argument("symbol")
    split.add_argument("--day", help="YYYY-MM-DD: print the factor for this day's raw prices")
    split.add_argument("--as-of", dest="as_of", help="YYYY-MM-DD: the terms to adjust into (default: latest)")
    output(split)
    bench = sub.add_parser("bench")
    bench.add_argument("--day")
    bench.add_argument("--symbol", default="TSLA")

    args = parser.parse_args(argv)
    handlers = {"status": cmd_status, "index": cmd_index, "trades": cmd_rows, "quotes": cmd_rows,
                "bars": cmd_bars, "movers": cmd_movers, "board": cmd_board, "splits": cmd_splits,
                "bench": cmd_bench}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
