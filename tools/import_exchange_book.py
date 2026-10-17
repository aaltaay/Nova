"""Import an exchange's own book for a past stock-day into the Sim (ADR 057).

Side effect, on purpose: writes the Sim's exchange book store
(``<NOVA_MARKET_DATA_DIR>/sim/exchange_books.sqlite3``, or ``--store``). It reads one local MBP-10 file -- DBN or
CSV, plain, gzip, or zstd with the ``zstandard`` package -- and never touches the network. The desk only reads
the store: a Sim replay of that symbol-day shows the venue's book on its Level 2, labelled as that venue's.

    py -3 tools/import_exchange_book.py import FILE --symbol XYZ --date 2026-09-18 [--dataset XNAS.ITCH]
    py -3 tools/import_exchange_book.py list [--symbol XYZ] [--date 2026-09-18]
    py -3 tools/import_exchange_book.py remove --symbol XYZ --date 2026-09-18 --dataset XNAS.ITCH

``--json`` prints the result as JSON. Exit 0 on success, 1 when the import is refused (nothing written).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from sim import exchange_book_import as importer  # noqa: E402
from sim import exchange_book_store as store  # noqa: E402
from sim.exchange_book_files import ExchangeBookError  # noqa: E402

ET = ZoneInfo("America/New_York")


def _et(ns: int) -> str:
    return datetime.fromtimestamp(ns / 1e9, ET).strftime("%H:%M:%S")


def _describe(book: dict) -> str:
    return (f"{book['symbol']} {book['date']} {book['label']} ({book['dataset']}): "
            f"{_et(book['known_from_ns'])}-{_et(book['known_to_ns'])} ET, {book['events']:,} events")


def _print(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2))
        return
    if not result.get("ok"):
        print(f"Refused: {result['error']}")
        return
    if "book" in result:
        read = result["read"]
        print(f"Imported {_describe(result['book'])} in {result['seconds']:.1f} s")
        print(f"  read {read['records']:,} records, {read['mbp10']:,} MBP-10; kept {read['kept']:,}; skipped "
              f"{read['other_instruments']:,} of other instruments, {read['not_last']:,} mid-event, "
              f"{read['before_day']:,} before 04:00 and {read['after_day']:,} from 20:00")
        if read["regressions"] or read["maybe_bad_book"]:
            print(f"  {read['regressions']:,} events stamped before the one before them (kept in file order); "
                  f"{read['maybe_bad_book']:,} the venue flagged as a possibly incomplete book")
    elif "books" in result:
        print(f"{len(result['books'])} imported book(s) in {result['store']}")
        for book in result["books"]:
            print(f"  {_describe(book)}")
    else:
        print("Removed." if result["removed"] else "No such book.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("import", help="import one MBP-10 file's book of a symbol-day")
    one.add_argument("file")
    one.add_argument("--symbol", required=True)
    one.add_argument("--date", required=True, help="the stock-day, YYYY-MM-DD (Eastern)")
    one.add_argument("--dataset", help="the file's venue dataset, e.g. XNAS.ITCH (required for a CSV)")
    one.add_argument("--instrument-id", type=int, help="the symbol's instrument id, when nothing in the file names it")
    shown = sub.add_parser("list", help="list imported books")
    shown.add_argument("--symbol")
    shown.add_argument("--date")
    gone = sub.add_parser("remove", help="drop one imported book")
    gone.add_argument("--symbol", required=True)
    gone.add_argument("--date", required=True)
    gone.add_argument("--dataset", required=True)
    for each in (one, shown, gone):
        each.add_argument("--store", help="the store file (default: <NOVA_MARKET_DATA_DIR>/sim/exchange_books.sqlite3)")
        each.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)
    try:
        if args.command == "import":
            result = importer.run(args.file, args.symbol, args.date, dataset=args.dataset,
                                  instrument_id=args.instrument_id, where=args.store,
                                  progress=None if args.json else
                                  lambda done: print(f"  ... {done['records']:,} records read, {done['kept']:,} kept",
                                                     flush=True))
        elif args.command == "list":
            result = dict(ok=True, store=str(args.store or store.path()),
                          books=importer.listing(args.store, args.symbol, args.date))
        else:
            result = dict(ok=True, removed=importer.remove(args.symbol, args.date, args.dataset, args.store))
    except (ExchangeBookError, sqlite3.Error, OSError) as exc:
        # Every refusal and every file or store that cannot be read answers in the same shape (--json included).
        result = dict(ok=False, error=str(exc))
    _print(result, args.json)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
