#!/usr/bin/env python3
"""Does a hidden seller (or buyer) on Level 2 say anything about what the price does next?

Runs the book watcher's hidden tracker (``backend/book_watch/hidden.py``, ADR 033 amendment) over
every Session Record's books and prints. A **flagged** stretch is one the ladder would mark: at a
price that held, at least ``--min-shares`` printed there and at least ``--mult`` x the most the
book ever showed there. A **busy** one printed as much at a price that held while the book showed
enough to explain it. For both, from that moment: how often a print went through the price within
10 s .. 5 min, and where the mid went in basis points toward that break (up for an offer, down for
a bid). A horizon past the end of its recorded stretch is not measured. Read-only: it opens the
recordings and never writes beside them.

Usage:

  py -3 tools/hidden_study.py [--session 2026-09-24:GCTK ...] [--min-shares 5000] [--mult 3]
  py -3 tools/hidden_study.py --grid          # every rule in the grid, by group and side
  py -3 tools/hidden_study.py --json --out F:\\Nova\\hidden_study.json

Few recordings and many rules find one that looks good by chance: read ``--by-day`` before
trusting a rule, and check a winner on days it never saw (``--session`` for each half).
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


def _recordings(root: Path, sessions: list[str] | None) -> list[Path]:
    if sessions:
        return [root / d / s.upper() for d, s in (x.split(":", 1) for x in sessions)]
    return sorted(p.parent for p in root.glob("20*/*/l2.jsonl"))


def _load(folder: Path):
    from book_watch.hidden_study import read
    from capture.schema import read_manifest
    from capture.sessions import is_ibkr_source
    from sim.capture_spans import load_spans

    manifest, _legacy = read_manifest(folder)
    if not is_ibkr_source(manifest):
        raise ValueError("not an IBKR recording")
    rec = read(folder)
    if rec.first_ts is None:
        raise ValueError("no rows")
    _segments, spans = load_spans(manifest, folder, live=False, first_ts=rec.first_ts, last_ts=rec.last_ts)
    if spans:
        rec.spans = [(float(a), float(b)) for a, b in spans]
    return rec


def _row(name: str, block: dict) -> str:
    cells = [f"{name:<14} n={block['n']:>4} ({block['per_hour'] if block['per_hour'] is not None else '-':>5}/h)"]
    for h, v in block["horizons"].items():
        tb = v["toward_bp"]
        brk = "-" if v["broke_pct"] is None else f"{v['broke_pct']:>3.0f}%"
        past = "-" if v["beyond_pct"] is None else f"{v['beyond_pct']:>3.0f}%"
        mean = "-" if tb["mean"] is None else f"{tb['mean']:+6.1f}bp"
        t = "" if tb["t"] is None else f" t{tb['t']:+.1f}"
        cells.append(f"{h:>3}s: broke {brk} past {past} {mean}{t}")
    return "  ".join(cells)


def render(answer: dict, *, by_day: bool, examples: int) -> str:
    rule = answer["rule"]
    lines = [f"Rule: at least {rule['min_shares']:,.0f} printed at a price that held {rule['min_hold_sec']:g} s or "
             f"more, and at least {rule['shown_mult']:g}x the most the book showed there.",
             f"{len(answer['recordings'])} recordings, {answer['depth_hours']:.1f} hours with a fresh book.",
             "Broke = a print went through the price by then. Past = the mid is beyond the price then. "
             "bp = the mid's move toward the break (up for an offer, down for a bid).", ""]
    names = {"flagged_ask": "hidden seller", "busy_ask": "busy offer", "flagged_bid": "hidden buyer",
             "busy_bid": "busy bid"}
    for key in ("flagged_ask", "busy_ask", "flagged_bid", "busy_bid"):
        lines.append(_row(names[key], answer["groups"][key]))
    if by_day:
        for day, groups in answer["by_day"].items():
            lines += ["", day]
            lines += [_row(names[k], groups[k]) for k in ("flagged_ask", "busy_ask", "flagged_bid", "busy_bid")]
    if answer.get("grid"):
        lines += ["", "Grid (60 s): n, past %, toward bp -- hidden seller | busy offer | hidden buyer | busy bid"]
        for g in answer["grid"]:
            cells = []
            for key in ("flagged_ask", "busy_ask", "flagged_bid", "busy_bid"):
                b = g["groups"][key]
                v = b["horizons"]["60"]
                mean = v["toward_bp"]["mean"]
                cells.append(f"{b['n']:>4} {v['beyond_pct'] if v['beyond_pct'] is not None else '-':>5}% "
                             f"{'-' if mean is None else f'{mean:+.1f}':>6}")
            lines.append(f"  hold {g['min_hold_sec']:>4g}s min {g['min_shares']:>6,.0f} x{g['shown_mult']:<4g}  "
                         + " | ".join(cells))
    if examples:
        flagged = [e for e in answer["events"] if e["group"] == "flagged"][:examples]
        lines += ["", f"First {len(flagged)} flagged:"]
        for e in flagged:
            at = datetime.fromtimestamp(e["at"], ET).strftime("%H:%M:%S")
            brk = "held 5 min" if e["broke_after_sec"] is None else f"broke after {e['broke_after_sec']:.0f} s"
            lines.append(f"  {e['date']} {at} {e['symbol']:<5} {'seller' if e['side'] == 'ask' else 'buyer':<6} "
                         f"{e['price']:<8g} printed {e['printed']:>8,.0f} shown max {e['shown_max']:>7,.0f} "
                         f"held {e['held_sec']:>5.1f} s  {brk}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from book_watch.constants_book_watch import (
        BOOK_WATCH_HIDDEN_MIN_HOLD_SEC,
        BOOK_WATCH_HIDDEN_MIN_SHARES,
        BOOK_WATCH_HIDDEN_SHOWN_MULT,
    )
    from book_watch.hidden_study import study
    from capture.storage import capture_root

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=None, help="the Session Records folder (default: Nova's)")
    parser.add_argument("--session", action="append", help="DATE:SYMBOL, repeatable (default: every recording)")
    parser.add_argument("--min-shares", type=float, default=BOOK_WATCH_HIDDEN_MIN_SHARES)
    parser.add_argument("--mult", type=float, default=BOOK_WATCH_HIDDEN_SHOWN_MULT)
    parser.add_argument("--hold", type=float, default=BOOK_WATCH_HIDDEN_MIN_HOLD_SEC,
                        help="seconds the price must have held before a stretch counts")
    parser.add_argument("--grid", action="store_true", help="every rule in the grid as well")
    parser.add_argument("--by-day", action="store_true", help="the rule's groups day by day")
    parser.add_argument("--examples", type=int, default=15, help="flagged moments to list (default 15)")
    parser.add_argument("--json", action="store_true", help="the whole answer as JSON")
    parser.add_argument("--out", type=Path, default=None, help="write the JSON answer here")
    args = parser.parse_args(argv)
    root = args.root or capture_root()
    recs = []
    for folder in _recordings(root, args.session):
        t = time.time()
        try:
            rec = _load(folder)
        except (ValueError, OSError) as exc:
            print(f"  skip {folder.parent.name} {folder.name}: {exc}", file=sys.stderr)
            continue
        print(f"  read {rec.date} {rec.symbol:<6} {rec.books:>7} books {rec.prints:>8} prints "
              f"{rec.depth_hours:5.2f} h with a book  ({time.time() - t:.1f}s)", file=sys.stderr)
        recs.append(rec)
    answer = study(recs, min_shares=args.min_shares, shown_mult=args.mult, min_hold=args.hold, grid=args.grid)
    if args.out:
        args.out.write_text(json.dumps(answer, default=str), encoding="utf-8")
    if args.json:
        print(json.dumps(answer, default=str))
    else:
        print(render(answer, by_day=args.by_day, examples=args.examples))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
