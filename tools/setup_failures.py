#!/usr/bin/env python3
"""Study the setups that ended (ADR 036 amendment, operator ask 2026-09-29): every setup the eyes saw
fail or fade, grouped by setup and reason, with what price did in the 15 minutes after it died.

"Higher-high failures: 23, of which 14 ran over the high first" is the question this answers: which
rule is costing trades, and which one is saving them. For each group:

  ran / fell / flat   which it crossed first after it died: over the high it was building under,
                      or under the low it would have stopped at (a candle that did both counts as
                      fell); flat: neither in 15 minutes. pend: the 15 minutes are not over yet;
                      unkn: no stored bars for it
  trades              after a run, the trade the rule refused, scored like an armed setup: 2R first,
                      stop first, still open; and its average bar R (the scoreboard's exit rules)

Scores, never fills: no tape, no slippage. A faded setup that never got past its leg is left out
(the chart does not draw it either); ``--all`` counts it. Triggered setups are totalled underneath.

Usage:

  py -3 tools/setup_failures.py                         the newest day on file
  py -3 tools/setup_failures.py --days 5                the newest five days
  py -3 tools/setup_failures.py --date 2026-09-29 --setup bull_flag --symbol NCPL --list
  py -3 tools/setup_failures.py --json

Journals come from ``--dir``, else ``NOVA_EYES_DIR``/journal, else ``F:\\Nova\\eyes\\journal`` when F:
is mounted, else ``backend/.cache/eyes/journal``; bars from the bar store under ``NOVA_CACHE_DIR``
(else ``backend/.cache``). Read-only: it never writes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from eyes import failure_study, reader  # noqa: E402

ET = ZoneInfo("America/New_York")


def journal_dir(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    configured = (os.environ.get("NOVA_EYES_DIR") or "").strip()
    if configured:
        return Path(configured) / "journal"
    if Path("F:/").exists():
        return Path("F:/Nova/eyes/journal")
    return REPO / "backend" / ".cache" / "eyes" / "journal"


def _bars(symbol: str, date: str):
    from eyes.recording import archive_bars

    return archive_bars(symbol, date)


def _clock(ts) -> str:
    return datetime.fromtimestamp(float(ts), ET).strftime("%H:%M") if ts else "--:--"


def _text(body: dict) -> str:
    out = []
    dates = body["dates"]
    span = dates[0] if len(dates) == 1 else f"{dates[-1]} .. {dates[0]} ({len(dates)} days)"
    left = body["left_out_legs"]
    out.append(f"Setups that ended, {span}: {body['ended']} failed or faded"
               + (f" ({left} faded at the leg left out; --all counts them)" if left else ""))
    out.append(f"{'setup':<18} {'end':<7} {'n':>4} {'ran':>4} {'fell':>4} {'flat':>4} {'pend':>4} {'unkn':>4}"
               f" | {'trades':>6} {'2R':>3} {'stop':>4} {'open':>4} {'avgR':>6} | reason")
    for g in body["groups"]:
        f, t = g["first"], g["trade"]
        avg = f"{t['avg_bar_r']:+.2f}" if t["avg_bar_r"] is not None else "--"
        out.append(f"{g['setup_type']:<18} {g['end']:<7} {g['count']:>4} {f['high']:>4} {f['low']:>4} {f['neither']:>4}"
                   f" {f['pending']:>4} {f['unknown']:>4} | {t['n']:>6} {t['target_first']:>3} {t['stop_first']:>4}"
                   f" {t['open']:>4} {avg:>6} | {g['example'] or g['reason_key'] or ''}")
    tr = body["triggered"]
    avg = f"{tr['avg_bar_r']:+.2f}" if tr["avg_bar_r"] is not None else "--"
    out.append(f"Triggered, for comparison: {tr['count']} (2R first {tr['target_first']}, stop first "
               f"{tr['stop_first']}, open {tr['open']}; average bar R {avg})")
    if body["missing_bars"]:
        out.append(f"No stored bars for: {', '.join(body['missing_bars'])}")
    for ep in body.get("episodes") or []:
        a = ep.get("after") or {}
        trade = a.get("trade") or {}
        out.append(f"  {ep['date']} {_clock(ep['died_at'])} {ep['symbol']:<6} {ep['setup_type']:<18} {ep['end']:<6}"
                   f" level {a.get('level')} floor {a.get('floor')} -> {a.get('first', 'unknown')}"
                   + (f" ({trade.get('outcome')}, bar R {trade.get('bar_r')})" if trade else "")
                   + f" | {ep['reason']}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", help="the journal folder")
    ap.add_argument("--date", help="one day, YYYY-MM-DD")
    ap.add_argument("--days", type=int, default=1, help="the newest N days on file (default 1)")
    ap.add_argument("--setup", help="first_pullback | bull_flag | flat_top_breakout | red_to_green")
    ap.add_argument("--symbol")
    ap.add_argument("--all", action="store_true", help="count faded setups that never got past their leg")
    ap.add_argument("--list", action="store_true", help="list every setup counted")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    folder = journal_dir(args.dir)
    if args.date:
        days = [(args.date, folder / f"{args.date}.jsonl")]
    else:
        days = [(d["date"], Path(d["path"])) for d in reader.days(folder)[: max(1, args.days)]]
    if not days or not any(p.is_file() for _, p in days):
        print(f"No journal in {folder}", file=sys.stderr)
        return 1
    body = failure_study.study(days, bars_fn=_bars, now=time.time(), setup=args.setup, symbol=args.symbol,
                               include_legs=args.all, listing=args.list)
    print(json.dumps(body, indent=2, default=str) if args.json else _text(body))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
