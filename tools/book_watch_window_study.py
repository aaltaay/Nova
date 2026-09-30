#!/usr/bin/env python3
"""Does the book watcher's matching window call fills "pulled"? Measured over the Session Records.

Runs the book watcher's own detector (``backend/book_watch/detector.py``) over every Session Record with
its matching window at 0.5, 1, 2 and 3 s either side of a drop's two books, then asks what a wider window
adds that chance would not: the prints no drop claimed at 0.5 s, against the same prints moved 30-60 s
(kept in the same place against the quote) and moved one tick away from the inside. Also the evidence
test (unclaimed size at the quote with a pulled drop at its price nearby, against the same prints moved)
and a direct one: how long IBKR's book took to show a best level that a print traded through. Cross
prints and prints with no book within 5 s are left out. Read-only: it opens the recordings and never
writes beside them. ADR 033 amendment 2026-09-30; the module is ``backend/book_watch/window_study.py``.

Usage:

  py -3 tools/book_watch_window_study.py                 # every recording, per day and in all
  py -3 tools/book_watch_window_study.py --by-recording
  py -3 tools/book_watch_window_study.py --session 2026-09-24:GCTK --session 2026-09-29:SSTI
  py -3 tools/book_watch_window_study.py --json --out F:\\Nova\\window_study.json

Heavy: the busiest recordings take minutes each. Not during market hours on the desk PC.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))


def _recordings(root: Path, sessions: list[str] | None) -> list[Path]:
    if sessions:
        return [root / d / s.upper() for d, s in (x.split(":", 1) for x in sessions)]
    return sorted(p.parent for p in root.glob("20*/*/l2.jsonl"))


def _load(folder: Path):
    from book_watch.window_study import read
    from capture.schema import read_manifest
    from capture.sessions import is_ibkr_source

    manifest, _legacy = read_manifest(folder)
    if not is_ibkr_source(manifest):
        raise ValueError("not an IBKR recording")
    rec = read(folder)
    if len(rec.books) < 2:
        raise ValueError("no depth line recorded")
    return rec


def _pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:5.1f}" if whole else "    -"


def _sweep_line(name: str, m: dict) -> str:
    sw = m["sweep"]
    keys = list(sw)
    base = sw[keys[0]]
    filled = " ".join(_pct(sw[k]["filled"], sw[k]["dropped"]) for k in keys)
    large = " ".join(f"{sw[k]['large_pulls']:>6,}" for k in keys)
    flags = " ".join(f"{sum(sw[k]['flags'].values()):>5,}" for k in keys)
    traded = " ".join(_pct(sw[k]["large_traded"], sw[k]["large_drops"]) for k in keys)
    return f"  {name:<18} {base['dropped']:>12,.0f} | {filled} | {large} | {flags} | {traded}"


def _extension_lines(name: str, m: dict) -> list[str]:
    ext = m["extension"]
    pulled = ext["pulled"]
    out = []
    for side in ("before", "after"):
        cells = []
        for s, c in ext[side].items():
            vs_moved = c["moved_real"] - c["moved"]
            vs_tick = c["real"] - c["tick_out"]
            lo, hi = sorted((vs_moved, vs_tick))
            cells.append(f"{s}s adds {_pct(c['real'], pulled)}% ({_pct(lo, pulled).strip()} to {_pct(hi, pulled).strip()})")
        out.append(f"  {name if side == 'before' else '':<18} {side:<6} " + "   ".join(cells))
    return out


def _evidence_line(name: str, m: dict) -> str:
    ev = m["evidence"]
    real, moved = ev["real"], ev["moved"]
    cells = [f"{_pct(real[k], real['volume'])} vs {_pct(moved[k], moved['volume'])}"
             for k in ("print_late_0.5_3", "print_early_0.5_1", "print_early_1_3")]
    return f"  {name:<18} {real['volume']:>12,.0f} | " + " | ".join(cells)


def _depth_line(name: str, m: dict) -> str:
    d = m["depth_late"]
    n = d["through"]
    cells = " ".join(_pct(d[k], n) for k in ("<=0.5", "0.5-1", "1-3", "3-10", "never"))
    return f"  {name:<18} {n:>9,} | {cells}"


def render(answer: dict, *, by_recording: bool) -> str:
    groups: list[tuple[str, dict]] = []
    if by_recording:
        groups += [(f"{r['date'][5:]} {r['symbol']}", r) for r in answer["recordings"]]
    groups += list(answer["by_day"].items())
    if answer["total"] is not None:
        groups.append(("all", answer["total"]))
    windows = "/".join(f"{w:g}" for w in answer["windows_sec"])
    lines = [
        f"{len(answer['recordings'])} Session Records. Cross prints and prints with no book within 5 s left out.",
        "",
        f"1. The detector with its window {windows} s either side of a drop's two books",
        f"  {'':<18} {'dropped':>12} | filled % of dropped   | large pulls                 | flags"
        f"                   | large drops traded %",
    ]
    lines += [_sweep_line(n, m) for n, m in groups]
    lines += [
        "",
        "2. What a wider window adds, % of the size the 0.5 s window calls pulled (in brackets: beyond chance,",
        "   against the same prints moved 30-60 s and moved one tick out; the rest is chance)",
    ]
    for n, m in groups:
        lines += _extension_lines(n, m)
    lines += [
        "",
        "3. The evidence test: unclaimed size at the quote with a pulled drop at its price, real vs moved 30-60 s",
        f"  {'':<18} {'volume':>12} | drop 0.5-3 s before | drop 0.5-1 s after | drop 1-3 s after",
    ]
    lines += [_evidence_line(n, m) for n, m in groups]
    lines += [
        "",
        "4. Depth late: a lit print through the displayed best price; when a book showed that level smaller or gone",
        f"  {'':<18} {'prints':>9} | <=0.5s 0.5-1s   1-3s  3-10s  never  (% of prints)",
    ]
    lines += [_depth_line(n, m) for n, m in groups]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from book_watch.window_study import measure, study
    from capture.storage import capture_root

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=None, help="the Session Records folder (default: Nova's)")
    parser.add_argument("--session", action="append", help="DATE:SYMBOL, repeatable (default: every recording)")
    parser.add_argument("--by-recording", action="store_true", help="each recording as well as each day")
    parser.add_argument("--json", action="store_true", help="the whole answer as JSON")
    parser.add_argument("--out", type=Path, default=None, help="write the JSON answer here")
    args = parser.parse_args(argv)
    root = args.root or capture_root()
    measured = []
    for folder in _recordings(root, args.session):
        t = time.time()
        try:
            rec = _load(folder)
        except (ValueError, OSError) as exc:
            print(f"  skip {folder.parent.name} {folder.name}: {exc}", file=sys.stderr)
            continue
        measured.append((rec, measure(rec)))
        print(f"  read {rec.date} {rec.symbol:<6} {len(rec.books):>7} books {len(rec.prints):>8} prints "
              f"({time.time() - t:.0f}s)", file=sys.stderr)
    answer = study(measured)
    if args.out:
        args.out.write_text(json.dumps(answer, default=str), encoding="utf-8")
    if args.json:
        print(json.dumps(answer, default=str))
    else:
        print(render(answer, by_recording=args.by_recording))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
