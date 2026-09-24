#!/usr/bin/env python3
"""Does the tape flow score say anything about the next minutes? (ADR 034)

Reads every recorded second of the Session Records through the tape flow score
(the lanes' own rule, ``backend/setup_scanner/tape_flow.py``) and measures where
the mid price went 10 s to 5 min later -- after every burst and flush onset, and
by score bucket. Read-only: it opens the recordings, never writes beside them.

Usage:

  py -3 tools/flow_study.py [--session 2026-09-24:GLND ...] [--set KEY=VALUE ...]
  py -3 tools/flow_study.py --grid flow_window_sec=5,10,20 --grid flow_flush_at=0.4,0.5,0.6 [--horizon 60]

``KEY`` is a template parameter (the Bots page's Tape flow group: ``flow_window_sec``,
``flow_w_imbalance``, ``flow_flush_at`` ...); unset ones are the default template's.
``--grid`` runs every combination and ranks them at ``--horizon`` seconds by
``--rank``: ``separation`` (a burst onset's mean move minus a flush onset's, the
default), ``flush_after_rise`` (how far the mid kept falling after a flush that
followed a rise -- the exit question) or ``burst_after_rise`` (how far it kept
rising -- the entry question), among combinations with at least
``--min-onsets`` of what is ranked. ``--out FILE`` writes the full answer as
JSON. Without ``--session`` every usable Session Record is read.

Many combinations on a few recordings will find one that looks good by chance:
rank on a first set of days, then check the winner on days it never saw
(``--session`` for each half).
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
SETUP = "first_pullback"     # the flow parameters are the same on every setup; this one names them


def _pairs(items: list[str] | None, many: bool) -> list[tuple[str, list[str]]]:
    out = []
    for item in items or []:
        key, sep, raw = item.partition("=")
        if not sep:
            raise SystemExit(f"{item!r} is not KEY=VALUE")
        out.append((key.strip(), [v for v in raw.split(",")] if many else [raw]))
    return out


def _values(overrides: dict) -> dict:
    from setup_templates import catalogue

    return catalogue.validate(SETUP, overrides)


def _flow(values: dict):
    from setup_scanner.lane_params import flow_params

    return flow_params(values)


def _load(sessions: list[str] | None) -> list:
    from eyes.recording import load, usable_sessions

    todo = [tuple(s.split(":", 1)) for s in sessions] if sessions else usable_sessions()
    recs = []
    for date, symbol in todo:
        t = time.time()
        try:
            rec = load(date, symbol.upper(), with_bars=False)
        except (ValueError, OSError) as exc:
            print(f"  skip {date} {symbol}: {exc}", file=sys.stderr)
            continue
        print(f"  read {date} {symbol:6} {len(rec.prints):>8} prints {len(rec.books):>7} books"
              f"  ({time.time() - t:.1f}s)", file=sys.stderr)
        recs.append(rec)
    return recs


def _fmt(v, width=7, unit=""):
    return f"{'--':>{width}}" if v is None else f"{v:>+{width}.1f}{unit}"


def print_answer(ans: dict) -> None:
    hs = list(ans["onsets"]["burst"].keys())
    print(f"\n{len(ans['recordings'])} recordings, {ans['seconds']:,} recorded seconds")
    print("seconds by label: " + "  ".join(f"{k} {v['pct']}%" for k, v in ans["seconds_by_label"].items()
                                           if v["n"]))
    print(f"\nonsets (first burst / flush after {ans['study']['refractory_sec']:g}s without one), mean move of the mid in bp:")
    print(f"  {'':12}{'n':>6}" + "".join(f"{'+' + h + 's':>9}" for h in hs) + f"{'spread':>9}")
    for label in ("burst", "flush"):
        row = ans["onsets"][label]
        n = row[hs[0]]["n"]
        print(f"  {label:12}{n:>6}" + "".join(f"{_fmt(row[h]['mean_bp'], 9)}" for h in hs)
              + f"{_fmt(ans['onset_spread_bp'][label], 9)}")
        print(f"  {'  up %':12}{'':>6}" + "".join(f"{row[h]['up_pct'] if row[h]['up_pct'] is not None else '--':>9}"
                                                  for h in hs))
        print(f"  {'  t':12}{'':>6}" + "".join(f"{row[h]['t'] if row[h]['t'] is not None else '--':>9}" for h in hs))
    print(f"  {'separation':12}{'':>6}" + "".join(f"{_fmt(ans['separation_bp'][h], 9)}" for h in hs))
    print(f"\nonsets by the minute before them (a move of {ans['study']['context_bp']:g} bp or more is a rise / fall):")
    for label in ("burst", "flush"):
        for ctx, row in (ans.get("onsets_by_context") or {}).get(label, {}).items():
            n = row[hs[0]]["n"] if hs[0] in row else 0
            print(f"  {label + ' ' + ctx:22}{n:>6}" + "".join(f"{_fmt(row[h]['mean_bp'], 9)}" for h in hs if h in row))
    print("\nevery second, by score bucket (mean move in bp, n):")
    for bucket, row in ans["by_bucket"].items():
        print(f"  {bucket:14}" + "".join(f"{_fmt(row[h]['mean_bp'], 9)}" for h in hs if h in row)
              + f"   n {row[hs[0]]['n'] if hs[0] in row else 0}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", action="append", help="DATE:SYMBOL, repeatable")
    ap.add_argument("--set", action="append", help="KEY=VALUE, repeatable: a template parameter")
    ap.add_argument("--grid", action="append", help="KEY=V1,V2,..., repeatable: every combination is run")
    ap.add_argument("--horizon", type=int, default=60, help="seconds the grid ranks on (default 60)")
    ap.add_argument("--min-onsets", type=int, default=20, help="onsets of what is ranked, for a grid rank")
    ap.add_argument("--rank", choices=("separation", "flush_after_rise", "burst_after_rise"), default="separation")
    ap.add_argument("--refractory", type=float, default=None, help="seconds between onsets of one kind")
    ap.add_argument("--out", help="write the full answer (or every grid answer) as JSON here")
    args = ap.parse_args()

    from eyes.flow_study import StudyParams, study
    from setup_templates import catalogue

    base = {k: catalogue.parse_text(SETUP, k, v[0]) for k, v in _pairs(args.set, False)}
    grid = [(k, [catalogue.parse_text(SETUP, k, x) for x in vs]) for k, vs in _pairs(args.grid, True)]
    sp = StudyParams() if args.refractory is None else StudyParams(refractory_sec=args.refractory)
    if args.horizon not in sp.horizons:
        sp = StudyParams(horizons=tuple(sorted(set(sp.horizons) | {args.horizon})), refractory_sec=sp.refractory_sec)
    recs = _load(args.session)
    if not recs:
        print("no usable Session Record", file=sys.stderr)
        return 1
    indexes: dict = {}
    if not grid:
        ans = study(recs, _flow(_values(base)), sp, indexes)
        print_answer(ans)
        if args.out:
            Path(args.out).write_text(json.dumps({**ans, "overrides": base}, indent=1), encoding="utf-8")
        return 0

    keys = [k for k, _ in grid]
    ranked = []
    for combo in itertools.product(*(vs for _, vs in grid)):
        overrides = {**base, **dict(zip(keys, combo))}
        try:
            values = _values(overrides)
        except catalogue.TemplateError as exc:
            print(f"  skip {overrides}: {exc.message}", file=sys.stderr)
            continue
        ans = study(recs, _flow(values), sp, indexes)
        h = str(args.horizon)
        if args.rank == "separation":
            b, f = ans["onsets"]["burst"][h], ans["onsets"]["flush"][h]
            key, n = ans["separation_bp"][h], min(b["n"], f["n"])
        else:
            label = args.rank.split("_")[0]
            b = f = ans["onsets_by_context"][label].get("after_rise", {}).get(h) or {"n": 0, "mean_bp": None, "t": None}
            key = None if b["mean_bp"] is None else (b["mean_bp"] if label == "burst" else -b["mean_bp"])
            n = b["n"]
        ranked.append({"overrides": overrides, "rank_bp": key, "n": n,
                       "burst": ans["onsets"]["burst"][h], "flush": ans["onsets"]["flush"][h], "ranked_on": b,
                       "answer": ans})
    ok = [r for r in ranked if r["n"] >= args.min_onsets and r["rank_bp"] is not None]
    ok.sort(key=lambda r: r["rank_bp"], reverse=True)
    print(f"\n{len(ranked)} combinations; {len(ok)} with at least {args.min_onsets} onsets, ranked by "
          f"{args.rank} at +{args.horizon}s (bp; bigger is better):")
    print(f"  {'rank bp':>9} {'n':>6} {'burst n':>8} {'mean':>7} {'t':>6} {'flush n':>8} {'mean':>7} {'t':>6}  combination")
    for r in ok:
        b, f = r["burst"], r["flush"]
        print(f"  {r['rank_bp']:>+9.1f} {r['n']:>6} {b['n']:>8} {_fmt(b['mean_bp'])} {b['t'] if b['t'] is not None else '--':>6}"
              f" {f['n']:>8} {_fmt(f['mean_bp'])} {f['t'] if f['t'] is not None else '--':>6}  "
              + ", ".join(f"{k}={v}" for k, v in r["overrides"].items()))
    if args.out:
        Path(args.out).write_text(json.dumps([{k: v for k, v in r.items()} for r in ranked], indent=1),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
