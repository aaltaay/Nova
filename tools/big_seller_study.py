#!/usr/bin/env python3
"""What did the price do after a big seller (or buyer) on Level 2?

Runs the book watcher's big-seller tracker (``backend/book_watch/big_seller.py``, #846 / #984) over every
Session Record's books and prints. For each called wall, from its call and from its end: the mid's move toward a
flush (down after a seller, up after a buyer) 10 s .. 5 min on, and how often a print went through its price.
Split by how it ended (taken, pulled, out of view, still there when the recording ended) and by how heavy it was
against the stock's lit pace (under a minute of volume, or a minute or more), beside the same recordings' every
minute as the baseline. A horizon past the end of its recorded stretch is not measured. Read-only: it opens the
recordings and never writes beside them.

Usage:

  py -3 tools/big_seller_study.py [--session 2026-09-24:GCTK ...] [--by-day]
  py -3 tools/big_seller_study.py --json --out F:\\Nova\\big_seller_study.json

Few recordings find a pattern by chance: read ``--by-day`` before trusting one. The group by how it ended looks
ahead from the call -- it describes what came with each ending, never a rule anyone could have traded.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

ET = ZoneInfo("America/New_York")
WHO = {"ask": "Big sellers", "bid": "Big buyers"}


def _recordings(root: Path, sessions: list[str] | None) -> list[Path]:
    if sessions:
        return [root / d / s.upper() for d, s in (x.split(":", 1) for x in sessions)]
    return sorted(p.parent for p in root.glob("20*/*/l2.jsonl"))


def _load(folder: Path):
    from book_watch.big_study import read
    from book_watch.hidden_study import recording_restarts
    from capture.schema import read_manifest
    from capture.sessions import is_ibkr_source
    from sim.capture_spans import load_spans

    manifest, _legacy = read_manifest(folder)
    if not is_ibkr_source(manifest):
        raise ValueError("not an IBKR recording")
    br = read(folder, restarts=recording_restarts(manifest, folder))
    if br.rec.first_ts is None:
        raise ValueError("no rows")
    _segments, spans = load_spans(manifest, folder, live=False, first_ts=br.rec.first_ts, last_ts=br.rec.last_ts)
    if spans:
        br.rec.spans = [(float(a), float(b)) for a, b in spans]
    return br


def _row(name: str, block: dict) -> str:
    cells = [f"{name:<22} n={block['n']:>4}"]
    for h, v in block["horizons"].items():
        fb = v["flush_bp"]
        brk = "-" if v["broke_pct"] is None else f"{v['broke_pct']:>3.0f}%"
        fl = "-" if v["flushed_pct"] is None else f"{v['flushed_pct']:>3.0f}%"
        mean = "-" if fb["mean"] is None else f"{fb['mean']:+6.1f}bp"
        t = "" if fb["t"] is None else f" t{fb['t']:+.1f}"
        cells.append(f"{h:>3}s: through {brk} flushed {fl} {mean}{t}")
    return "  ".join(cells)


def _base_cell(h: str, v: dict) -> str:
    fl = "-" if v["flushed_pct"] is None else f"{v['flushed_pct']:>3.0f}%"
    mean = v["flush_bp"]["mean"]
    return f"{h:>3}s: flushed {fl} {'-' if mean is None else f'{mean:+6.1f}bp'}"


def _side(groups: dict, side: str) -> list[str]:
    g = groups[side]
    lines = [_row(f"{WHO[side]}, from call", g["all"])]
    for k, v in g["by_end"].items():
        lines.append(_row(f"  {k}, from call", v["from_call"]))
        lines.append(_row(f"  {k}, from end", v["from_end"]))
    lines.append(_row("  pulled as price came", g["on_approach"]))
    for k, v in g["by_weight"].items():
        lines.append(_row(f"  {k}", v))
    return lines


def render(answer: dict, *, by_day: bool, examples: int) -> str:
    lines = [f"{len(answer['recordings'])} recordings, {answer['depth_hours']:.1f} hours with a fresh book.",
             "Through = a print went through the wall's price by then. Flushed = the mid moved toward a flush "
             "(down after a seller, up after a buyer). bp = the mid's mean move toward a flush.",
             f"Breakable = under {answer['breakable_sec']:g} s of the last minute's lit volume when called; heavy = "
             "that or more.", ""]
    lines.append("Every minute (baseline, signed as after a seller):  "
                 + "  ".join(_base_cell(h, v) for h, v in answer["baseline_seller"].items()))
    for side in ("ask", "bid"):
        lines += [""] + _side(answer["groups"], side)
    if by_day:
        for day, groups in answer["by_day"].items():
            lines += ["", day, _row("Big sellers, from call", groups["ask"]["all"]),
                      _row("Big buyers, from call", groups["bid"]["all"])]
    if examples:
        evs = answer["events"][:examples]
        lines += ["", f"First {len(evs)} walls:"]
        for e in evs:
            at = datetime.fromtimestamp(e["at"], ET).strftime("%H:%M:%S")
            clear = "-" if e["clear_sec"] is None else f"{e['clear_sec']:.0f} s"
            lines.append(f"  {e['date']} {at} {e['symbol']:<5} {'seller' if e['side'] == 'ask' else 'buyer':<6} "
                         f"{e['price']:<8g} {e['size']:>9,.0f} sh  {clear:>6} of volume  {e['ended']}"
                         f"{' (as price came)' if e['on_approach'] else ''}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from book_watch.big_study import study
    from capture.storage import capture_root

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=None, help="the Session Records folder (default: Nova's)")
    parser.add_argument("--session", action="append", help="DATE:SYMBOL, repeatable (default: every recording)")
    parser.add_argument("--by-day", action="store_true", help="each day's walls from the call")
    parser.add_argument("--examples", type=int, default=15, help="walls to list (default 15)")
    parser.add_argument("--json", action="store_true", help="the whole answer as JSON")
    parser.add_argument("--out", type=Path, default=None, help="write the JSON answer here")
    args = parser.parse_args(argv)
    root = args.root or capture_root()
    recs = []
    for folder in _recordings(root, args.session):
        t = time.time()
        try:
            br = _load(folder)
        except (ValueError, OSError) as exc:
            print(f"  skip {folder.parent.name} {folder.name}: {exc}", file=sys.stderr)
            continue
        print(f"  read {br.date} {br.symbol:<6} {br.rec.books:>7} books {br.rec.prints:>8} prints "
              f"{br.rec.depth_hours:5.2f} h with a book  {len(br.called):>3} walls  ({time.time() - t:.1f}s)",
              file=sys.stderr)
        recs.append(br)
    answer = study(recs)
    if args.out:
        args.out.write_text(json.dumps(answer, default=str), encoding="utf-8")
    if args.json:
        print(json.dumps(answer, default=str))
    else:
        print(render(answer, by_day=args.by_day, examples=args.examples))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
