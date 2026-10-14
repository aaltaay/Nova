#!/usr/bin/env python3
"""A day's IBKR market-data incidents, from Nova's own records -- evidence to send to IBKR support.

ADR 045 amendment 2026-10-14: "if the issue is more upstream with IBKR, then lets make sure this stuff
is in front of us and report this problem to IBKR, but we need evidence and clear reason for the
operator!" Nova never contacts IBKR itself; this writes what the operator sends.

Read only. From the perf day file (``<cache>/perf/YYYY-MM-DD.jsonl``) it takes IB Gateway's
connectivity losses and restores (Error 1100 / 1101 / 1102) and data-farm notices (``ib_notice``),
each Time & Sales line Nova read dead or silent (``tape_silence``) and Nova's Reconnect Data
attempts (``tape_recovery``). From ``<cache>/archive.db`` it measures each stall: when the line's
next tick-by-tick (AllLast) print came, and how many Level 1 last-price updates IBKR delivered for
the same stock while its tick-by-tick line delivered none.

Usage (repo root):
  py -3 tools/ibkr_feed_report.py                      # today, ET
  py -3 tools/ibkr_feed_report.py --date 2026-10-14
  py -3 tools/ibkr_feed_report.py --date 2026-10-14 --out F:/Nova/reports/ibkr-2026-10-14.md
  py -3 tools/ibkr_feed_report.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

ET = ZoneInfo("America/New_York")
SCHEMA_VERSION = 1
CONNECTIVITY_CODES = (1100, 1101, 1102)
# Only a line whose Level 1 shows trades it never printed is evidence; "silent" can be a quiet name.
DOWN_STATES = ("dead",)
# api-console.log line for IBKR's connectivity messages, for days before Nova kept them in the perf file.
_LOG_CONNECTIVITY = re.compile(
    r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),(\d+) \w+ ib_async\.wrapper Error (1100|1101|1102), reqId -?\d+: (.*)$")
# A stall with no print for this long after its start is reported as still open at the day's end.
_NEXT_PRINT_SCAN_SEC = 6 * 3600


def clock(ts: float | None) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S") if ts else "--"


def default_cache() -> Path:
    from paths import cache_root

    return Path(cache_root())


def default_log() -> Path:
    from paths import log_root

    return Path(log_root()) / "api-console.log"


def connectivity_from_log(path: Path, day: str) -> list[dict[str, Any]]:
    """IBKR's 1100 / 1101 / 1102 lines of ``day`` from the backend's text log (desk-local time = ET)."""
    out: list[dict[str, Any]] = []
    if not path.is_file():
        return out
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith(day) or "ib_async.wrapper Error 110" not in line:
                continue
            m = _LOG_CONNECTIVITY.match(line.rstrip("\r\n"))
            if not m:
                continue
            at = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
            out.append({"ts": at.timestamp() + int(m.group(2)) / 1000.0, "code": int(m.group(3)),
                        "message": m.group(4).strip(), "source": "log"})
    return out


def load_perf(path: Path) -> list[dict[str, Any]]:
    """The day file's rows this report reads; unreadable lines are skipped and counted."""
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            if '"ib_notice"' not in line and '"tape_silence"' not in line and '"tape_recovery"' not in line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("kind") in ("ib_notice", "tape_silence", "tape_recovery"):
                rows.append(row)
    return rows


def stalls_from(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One stall per silence start: the lines Nova read down then, with the words of the first reading (pure).

    Lines whose silences began within a second of each other are one stall (one IBKR event).
    """
    by_start: dict[tuple[str, float], dict[str, Any]] = {}
    for row in rows:
        if row.get("kind") != "tape_silence":
            continue
        reading = row.get("reading") or {}
        if reading.get("state") not in DOWN_STATES or not reading.get("since"):
            continue
        key = (str(row.get("symbol")), float(reading["since"]))
        by_start.setdefault(key, {"symbol": key[0], "since": key[1], "read_at": row.get("ts"),
                                  "state": reading.get("state"), "pipeline": reading.get("pipeline") or [],
                                  "history_unanswered_since": reading.get("history_unanswered_since"),
                                  "text": reading.get("text")})
    stalls: list[dict[str, Any]] = []
    for line in sorted(by_start.values(), key=lambda r: r["since"]):
        last = stalls[-1] if stalls else None
        if last is not None and line["since"] - last["since"] <= 1.0:
            last["lines"].append(line)
            continue
        stalls.append({"since": line["since"], "lines": [line]})
    return stalls


def measure(conn: sqlite3.Connection, symbol: str, since: float) -> dict[str, Any]:
    """When the line printed again, and what Level 1 delivered for the stock in between."""
    row = conn.execute("SELECT MIN(ts) FROM tape_ibkr WHERE symbol = ? AND ts > ? AND ts < ?",
                       (symbol, since, since + _NEXT_PRINT_SCAN_SEC)).fetchone()
    back = float(row[0]) if row and row[0] is not None else None
    if back is None:
        # No later print: the line may have been closed, so the silence has no end to count to.
        return {"back_at": None, "seconds": None, "l1_updates": None, "l1_low": None, "l1_high": None}
    until = back
    l1 = conn.execute("SELECT COUNT(*), MIN(price), MAX(price) FROM l1_ticks WHERE symbol = ? AND ts > ? AND ts < ?",
                      (symbol, since, until)).fetchone()
    return {"back_at": back, "seconds": (back - since) if back is not None else None,
            "l1_updates": int(l1[0] or 0), "l1_low": l1[1], "l1_high": l1[2]}


def build(day: str, cache: Path, log: Path | None = None) -> dict[str, Any]:
    rows = load_perf(cache / "perf" / f"{day}.jsonl")
    notices = [r for r in rows if r.get("kind") == "ib_notice"]
    connectivity = [r for r in notices if r.get("code") in CONNECTIVITY_CODES]
    if not connectivity and log is not None:
        connectivity = connectivity_from_log(log, day)
    farms = [r for r in notices if r.get("farm")]
    recovery = [r for r in rows if r.get("kind") == "tape_recovery"]
    stalls = stalls_from(rows)
    db = cache / "archive.db"
    if db.is_file() and stalls:
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            for stall in stalls:
                read = {line["symbol"] for line in stall["lines"]}
                peers = sorted({p for line in stall["lines"] for p in line.get("pipeline") or []} - read)
                # A line in the same silence that Nova did not read dead itself: measured from the same start.
                stall["lines"] += [{"symbol": p, "since": stall["since"], "peer": True} for p in peers]
                for line in stall["lines"]:
                    line.update(measure(conn, line["symbol"], line["since"]))
        finally:
            conn.close()
    return {"schema_version": SCHEMA_VERSION, "date": day, "connectivity": connectivity, "farms": farms,
            "stalls": stalls, "recovery": recovery, "archive": db.is_file()}


def _near(rows: list[dict[str, Any]], ts: float, before: float, after: float) -> list[dict[str, Any]]:
    return [r for r in rows if ts - before <= float(r.get("ts") or 0) <= ts + after]


def render(report: dict[str, Any]) -> str:
    day, stalls = report["date"], report["stalls"]
    out = [f"# IBKR market data incidents -- {day} (times ET)", ""]
    lost = [r for r in report["connectivity"] if r.get("code") == 1100]
    longest = max((line.get("seconds") or 0 for s in stalls for line in s["lines"]), default=0)
    out += [
        f"IB Gateway lost its connection to IBKR {len(lost)} time(s). Nova's tick-by-tick (AllLast) "
        f"Time & Sales stopped {len(stalls)} time(s) while IBKR kept sending the same stocks' Level 1 "
        f"quotes and last prices; the longest stall lasted {longest:.0f} s.",
        "",
        "Account: (add yours); IB Gateway version: (add yours); connection: the IB Gateway API on this PC.",
        "",
        "## IB Gateway connectivity (API messages 1100 / 1101 / 1102)",
        "",
    ]
    if report["connectivity"]:
        out += ["| Time | Code | Message |", "|---|---|---|"]
        out += [f"| {clock(r['ts'])} | {r['code']} | {r.get('message') or ''} |" for r in report["connectivity"]]
    else:
        out.append("None recorded.")
    out += ["", "## Time & Sales stalls (reqTickByTickData AllLast)", ""]
    if not stalls:
        out.append("None recorded.")
    for i, stall in enumerate(stalls, 1):
        names = ", ".join(sorted({line["symbol"] for line in stall["lines"]} |
                                 {p for line in stall["lines"] for p in line.get("pipeline") or []}))
        out += [f"### Stall {i}: from {clock(stall['since'])} -- {names}", ""]
        out += ["| Symbol | Last print | Next print | Silent | Level 1 updates in the silence | Level 1 range |",
                "|---|---|---|---|---|---|"]
        for line in stall["lines"]:
            secs = line.get("seconds")
            rng = (f"{line['l1_low']:g}-{line['l1_high']:g}" if line.get("l1_low") is not None else "--")
            name = f"{line['symbol']} (same stall)" if line.get("peer") else line["symbol"]
            out.append(f"| {name} | {clock(line['since'])} | {clock(line.get('back_at'))} | "
                       f"{f'{secs:.0f} s' if secs is not None else 'no later print recorded (line closed?)'} | "
                       f"{line['l1_updates'] if line.get('l1_updates') is not None else '--'} | {rng} |")
        hist = next((line.get("history_unanswered_since") for line in stall["lines"]
                     if line.get("history_unanswered_since")), None)
        if hist:
            out.append(f"\nIBKR's historical data (HMDS) stopped answering from {clock(hist)}.")
        around = sorted(_near(report["farms"] + report["connectivity"], stall["since"], 120, 600),
                        key=lambda r: float(r.get("ts") or 0))
        if around:
            out.append("\nIBKR messages from 2 min before to 10 min after:")
            out += [f"- {clock(r['ts'])} {r['code']} {r.get('notice') or ''} {r.get('farm') or ''}".rstrip()
                    for r in around]
        out.append("")
    out += ["## Nova's Reconnect Data attempts (IBC RECONNECTDATA)", ""]
    verified = [r for r in report["recovery"] if r.get("phase") == "verified"]
    sent = [r for r in report["recovery"] if r.get("phase") == "sent"]
    if not sent:
        out.append("None.")
    for r in sent:
        done = next((v for v in verified if v.get("asked_ts") == r.get("asked_ts")), None)
        what = (f"prints back on {', '.join(done.get('back') or []) or 'none'} 30 s later" if done
                else "no follow-up recorded")
        out.append(f"- {clock(r.get('asked_ts'))}: lines {', '.join(r.get('lines') or [])} -- "
                   f"{'sent' if r.get('sent') else 'not sent: ' + str(r.get('error'))}; {what}")
    out += ["", "## Data farm notices (2103-2108, 2157/2158)", ""]
    if report["farms"]:
        out += ["| Time | Code | State | Farm |", "|---|---|---|---|"]
        out += [f"| {clock(r['ts'])} | {r['code']} | {r.get('notice') or ''} | {r.get('farm') or ''} |"
                for r in report["farms"]]
    else:
        out.append("None recorded.")
    out += [
        "", "## Question for IBKR", "",
        "During each stall above, reqTickByTickData (AllLast) delivered no trades for every subscribed stock, "
        "with no error message, while reqMktData kept delivering Level 1 last prices and market depth for the "
        "same stocks. Why did tick-by-tick data stop, why was no error or farm notice sent when it did, and what "
        "should an API client do to restore it without disconnecting?",
    ]
    if not report["archive"]:
        out += ["", "_archive.db was not found: next prints and Level 1 counts are missing._"]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", default=datetime.now(ET).strftime("%Y-%m-%d"), help="YYYY-MM-DD (ET)")
    parser.add_argument("--cache", default=None, help="Nova's cache folder (default: this checkout's)")
    parser.add_argument("--log", default=None, help="the backend's api-console.log (default: this checkout's)")
    parser.add_argument("--out", default=None, help="write the Markdown here instead of printing it")
    parser.add_argument("--json", action="store_true", help="print the measured facts as JSON")
    args = parser.parse_args(argv)
    cache = Path(args.cache) if args.cache else default_cache()
    report = build(args.date, cache, Path(args.log) if args.log else default_log())
    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0
    text = render(report)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
