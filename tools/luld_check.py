#!/usr/bin/env python3
"""How close are Nova's LULD bands to the exchanges'? (ADR 047)

Replays trades and quotes through ``backend/luld/tracker.py`` and compares the bands it would have
shown with the truth. Read-only: it opens the data and writes only its own results.

  massive   The Massive flat files. Every NBBO row carries the SIP's own LULD indicator, so each
            moment the bid sat on the upper band (or the offer on the lower) gives the band's
            exact price. Ticker-days come from the halt log (the leaderboard's halt_events: the
            Nasdaq LULD pauses). Several tracker variants run on the same events (luld/study.py).
  records   Nova's Session Records (IBKR's tape and book, the live desk's data): the price the
            NBBO sat at for the 15 s before each logged pause.
  summary   Print the summary of saved massive results.

Usage:

  py -3 tools/luld_check.py massive --from 2026-09-21 --to 2026-10-05 --workers 3
  py -3 tools/luld_check.py massive --days 2026-09-22 --symbols GRML
  py -3 tools/luld_check.py records
  py -3 tools/luld_check.py summary --out F:\\Nova\\eyes\\studies\\luld-2026-10-06
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import pickle
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

DEFAULT_OUT = Path(r"F:\Nova\eyes\studies\luld-2026-10-06")
LULD_CODES = ("LUDP", "LUDS", "M")


def _leaderboard_db() -> Path:
    env = os.environ.get("NOVA_LEADERBOARD_DIR")
    return Path(env) / "leaderboard.sqlite3" if env else Path(r"F:\Nova\leaderboard\leaderboard.sqlite3")


def pauses_by_day(first: str, last: str) -> dict[str, dict[str, list[float]]]:
    """``{day: {symbol: [pause start, ...]}}`` from the Nasdaq halt feed's LULD pauses."""
    con = sqlite3.connect(f"file:{_leaderboard_db()}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "select session_date, symbol, ts from halt_events where source = 'nasdaq_trade_halt_rss' "
            f"and event = 'start' and code in ({','.join('?' * len(LULD_CODES))}) "
            "and session_date between ? and ? order by ts", (*LULD_CODES, first, last)).fetchall()
    finally:
        con.close()
    out: dict[str, dict[str, list[float]]] = {}
    for day, symbol, ts in rows:
        out.setdefault(day, {}).setdefault(symbol, []).append(float(ts))
    return out


def _one_day(day: str, pauses: dict[str, list[float]], out_dir: str) -> dict:
    import logging

    logging.disable(logging.WARNING)
    from luld import study

    started = time.time()
    tickers = sorted(pauses)
    # The day's extracted rows are kept, so a second look at the rules reads no flat file.
    cache = Path(out_dir) / "cache" / f"{day}.pkl.gz"
    if cache.exists():
        with gzip.open(cache, "rb") as fh:
            data, prev = pickle.load(fh)
    else:
        data = study.read_massive_day(day, tickers)
        prev = study.massive_prev_close(day, tickers)
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(".tmp")
        with gzip.open(tmp, "wb", compresslevel=3) as fh:
            pickle.dump((data, prev), fh, protocol=5)
        os.replace(tmp, cache)
    results = []
    for symbol in tickers:
        rows = data.get(symbol) or {}
        if not rows.get("trades"):
            continue
        results.append(study.evaluate(symbol, day, rows["trades"], rows["quotes"],
                                      prev_close=prev.get(symbol), pauses=pauses[symbol]))
    study.write_json(Path(out_dir) / f"{day}.json", results)
    return {"day": day, "tickers": len(results), "touches": sum(len(r["touches"]) for r in results),
            "secs": round(time.time() - started, 1)}


def cmd_massive(args) -> int:
    from sim import massive_files as mf

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.days:
        days = args.days
        first, last = min(days), max(days)
    else:
        first, last = args.first, args.last
        days = None
    by_day = pauses_by_day(first, last)
    todo = []
    for day in sorted(by_day):
        if days and day not in days:
            continue
        if mf.day_file("trades_v1", day) is None or mf.day_file("quotes_v1", day) is None:
            print(f"{day}: Massive files not on disk, skipped")
            continue
        if (out / f"{day}.json").exists() and not args.force:
            print(f"{day}: done before ({out / (day + '.json')})")
            continue
        pauses = by_day[day]
        if args.symbols:
            pauses = {s: v for s, v in pauses.items() if s in set(args.symbols)}
        if pauses:
            todo.append((day, pauses))
    print(f"{len(todo)} days to read, {sum(len(p) for _, p in todo)} ticker-days")
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(_one_day, day, pauses, str(out)): day for day, pauses in todo}
        for fut in as_completed(futures):
            try:
                print(json.dumps(fut.result()), flush=True)
            except Exception as exc:  # report and go on with the other days
                print(f"{futures[fut]}: failed: {exc!r}", flush=True)
    return cmd_summary(args)


def cmd_summary(args) -> int:
    from luld import study

    out = Path(args.out)
    results = []
    for path in sorted(out.glob("20*.json")):
        results += json.loads(path.read_text(encoding="utf-8"))
    summary = study.summarize(results)
    study.write_json(out / "summary.json", summary)
    print(json.dumps(summary, indent=1))
    return 0


def cmd_records(args) -> int:
    import logging

    logging.disable(logging.WARNING)
    from luld import records

    rows = records.check_all()
    for row in rows:
        print(json.dumps(row))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("massive")
    m.add_argument("--from", dest="first", default="2026-09-21")
    m.add_argument("--to", dest="last", default="2026-10-05")
    m.add_argument("--days", nargs="*")
    m.add_argument("--symbols", nargs="*")
    m.add_argument("--workers", type=int, default=2)
    m.add_argument("--out", default=str(DEFAULT_OUT))
    m.add_argument("--force", action="store_true")
    s = sub.add_parser("summary")
    s.add_argument("--out", default=str(DEFAULT_OUT))
    sub.add_parser("records")
    args = ap.parse_args()
    return {"massive": cmd_massive, "summary": cmd_summary, "records": cmd_records}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
