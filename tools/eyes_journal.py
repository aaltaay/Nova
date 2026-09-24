#!/usr/bin/env python3
"""Read the eyes' journal (ADR 029): what the setup scanner's lanes saw, day by day.

The journal is one JSON line per observation -- legs, arms (levels, grade,
pillars), filtered setups, near, each tape verdict change, triggers, fails,
proposals, scores -- stamped with the template, the bot's level / Activate and
the venue. This is where an analysis of the eyes starts.

Usage:

  py -3 tools/eyes_journal.py days
  py -3 tools/eyes_journal.py summary [--date 2026-09-24] [--source live|sim] [--template ID]
  py -3 tools/eyes_journal.py setups  [--date ...] [--symbol IPDN] [--template ID] [--json]
  py -3 tools/eyes_journal.py events  [--date ...] [--symbol IPDN] [--event armed,near,tape] [--json] [--limit 200]

``--date`` defaults to the newest day on file. The folder is ``--dir``, else
``NOVA_EYES_DIR``/journal, else ``F:\\Nova\\eyes\\journal`` when F: is mounted,
else ``backend/.cache/eyes/journal``. Read-only: it never writes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from eyes import reader  # noqa: E402

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


def _clock(ts) -> str:
    return datetime.fromtimestamp(float(ts), ET).strftime("%H:%M:%S") if ts else "--:--:--"


def _path(folder: Path, date: str | None) -> Path:
    if date:
        return folder / f"{date}.jsonl"
    days = reader.days(folder)
    if not days:
        raise SystemExit(f"no journal days under {folder}")
    return Path(days[0]["path"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["days", "summary", "setups", "events"])
    ap.add_argument("--dir")
    ap.add_argument("--date")
    ap.add_argument("--source")
    ap.add_argument("--template")
    ap.add_argument("--symbol")
    ap.add_argument("--event")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    folder = journal_dir(args.dir)

    if args.command == "days":
        for d in reader.days(folder):
            print(f"{d['date']}  {d['bytes'] / 1e6:8.2f} MB  {d['path']}")
        return 0

    path = _path(folder, args.date)
    skipped: dict[str, int] = {}
    rows = reader.lines(path, source=args.source, symbol=args.symbol, template=args.template, event=args.event,
                        skipped=skipped)
    if args.command == "summary":
        out = reader.counts(rows)
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(f"{path.name}")
            for key, block in out.items():
                print(f"  {key}: {len(block['symbols'])} symbols; events {block['events']}; tape {block['tape']}")
    elif args.command == "setups":
        recs = reader.setups(rows)
        if args.json:
            print(json.dumps(recs, indent=2, default=str))
        else:
            for r in recs:
                s = r.get("setup") or {}
                print(f"{_clock(r.get('armed_ts'))} {r.get('source'):4} {r.get('template'):12} {r.get('symbol'):6} "
                      f"trig {s.get('trigger')} stop {s.get('stop')} grade {r.get('grade')} "
                      f"near {r.get('near_tape') or '-'} trigger {r.get('trigger_tape') or '-'} "
                      f"{'FILTERED ' + str(r['filtered']) if r.get('filtered') else ''}"
                      f"{'outcome ' + str(r['outcome']) + ' R ' + str(r.get('bar_r')) if r.get('outcome') else ''}")
    else:
        for i, row in enumerate(rows):
            if i >= args.limit:
                print(f"... more (raise --limit)")
                break
            if args.json:
                print(json.dumps(row, default=str))
            else:
                extra = row.get("reason") or row.get("verdict") or row.get("status") or ""
                print(f"{_clock(row.get('ts'))} {row.get('source'):4} {row.get('template') or '-':12} "
                      f"{row.get('symbol') or '-':6} {row.get('event'):10} {extra}")
    if skipped:
        print(f"(skipped lines: {skipped})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
