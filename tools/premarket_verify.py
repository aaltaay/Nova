#!/usr/bin/env python3
"""Premarket evidence for #14, and why the Gateway last needed a phone login.

#14 closes on two facts nobody should have to dig out of four logs by hand:

1. an unattended NovaMorningCheck run (03:55 ET, started by the scheduler)
   that ended ``RESULT PASS``;
2. a week with no IB Gateway phone login other than IBKR's weekly one.

This tool reads the evidence and says whether each criterion is met, and for
every phone login and every missed morning it says why -- a Windows restart
(who asked, when, and how long Windows sat at the sign-in screen), or a fresh
Gateway start. Read-only: it reads ``backend/logs/morning-check.log``,
``backend/logs/daily-start.log``, the IBC logs and the Windows System event
log, and writes nothing.

Usage (repo root):
  py -3 tools/premarket_verify.py                 # the #14 evidence, text
  py -3 tools/premarket_verify.py --json          # same, JSON (schema in AGENTS.md §3)
  py -3 tools/premarket_verify.py relogin         # one line: why the latest Gateway start needed / did not need a phone
  py -3 tools/premarket_verify.py relogin --json

Exit code: ``evidence`` 0 when both criteria are met, 1 otherwise;
``relogin`` always 0 (the scripts print its line).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from constants_nova_os import NOVA_OS_NYSE_HOLIDAYS  # noqa: E402
from constants_relogin import (  # noqa: E402
    PREMARKET_CHECK_WINDOW_END,
    PREMARKET_CHECK_WINDOW_START,
    PREMARKET_EVIDENCE_DAYS_DEFAULT,
)
from ibkr import relogin_reason, windows_restarts  # noqa: E402

SCHEMA_VERSION = 1
LOG_DIR = ROOT / "backend" / "logs"
_LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) \[(\w+)\] (.*)$")
_RUN_GAP_SEC = 10 * 60
_SAME_START_SEC = 5 * 60


def parse_morning_runs(text: str) -> list[dict[str, Any]]:
    """Group morning-check.log lines into runs (a new date, or a gap of more
    than ten minutes, starts one). ``unattended`` means the first line fell
    in the scheduler's 03:55 window -- a hand-started run lands elsewhere."""
    runs: list[dict[str, Any]] = []
    last_ts: float | None = None
    for raw in (text or "").splitlines():
        m = _LINE_RE.match(raw.strip())
        if not m:
            continue
        day, clock, level, message = m.groups()
        ts = _local(f"{day} {clock}")
        if ts is None:
            continue
        if not runs or runs[-1]["date"] != day or last_ts is None or ts - last_ts > _RUN_GAP_SEC:
            runs.append({
                "date": day,
                "started": clock,
                "unattended": PREMARKET_CHECK_WINDOW_START <= clock[:5] <= PREMARKET_CHECK_WINDOW_END,
                "result": None,
                "failed_leg": None,
            })
        last_ts = ts
        if message.startswith("RESULT PASS"):
            runs[-1]["result"] = "PASS"
        elif message.startswith("RESULT FAIL"):
            runs[-1]["result"] = "FAIL"
            leg = re.search(r"leg=(\S+)", message)
            runs[-1]["failed_leg"] = leg.group(1) if leg else None
    return runs


def parse_gateway_launches(text: str) -> list[float]:
    """Times Start-NovaDaily cold-started the Gateway through IBC. Every cold
    start is a phone login: the saved login survives only Gateway's own
    restart, never a new process."""
    out: list[float] = []
    for raw in (text or "").splitlines():
        m = _LINE_RE.match(raw.strip())
        if m and m.group(4).startswith("Starting IB Gateway via IBC"):
            ts = _local(f"{m.group(1)} {m.group(2)}")
            if ts is not None:
                out.append(ts)
    return out


def build_evidence(
    *,
    runs: list[dict[str, Any]],
    ibc_logins: list[relogin_reason.IbcLogin],
    launches: list[float],
    restarts: list[windows_restarts.Restart] | None,
    days: int,
    now: float,
) -> dict[str, Any]:
    """Pure: the #14 verdict from already-read facts."""
    since = now - days * 86400
    full_logins: list[dict[str, Any]] = []
    for login in ibc_logins:
        if login.full_auth and login.ts is not None and since <= login.ts <= now:
            full_logins.append(_login_row(login.ts, "ibc_log", restarts, now, login))
    # IBC keeps a patchy history (see docs/live-desk-sync.md, "IBC log
    # history"), so Nova's own launch log fills the gaps; a launch the IBC log
    # already shows (its login within a few minutes after) is not counted twice.
    ibc_times = [l.ts for l in ibc_logins if l.ts is not None]
    for ts in launches:
        if not since <= ts <= now or any(ts <= t <= ts + _SAME_START_SEC for t in ibc_times):
            continue
        full_logins.append(_login_row(ts, "daily_start", restarts, now, None))
    full_logins.sort(key=lambda r: r["ts"])

    recent = [r for r in runs if (_local(f"{r['date']} {r['started']}") or 0) >= since]
    passes = [r for r in recent if r["unattended"] and r["result"] == "PASS"]
    unexpected = [r for r in full_logins if not r["expected"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now,
        "days": days,
        "morning_runs": recent,
        "missed_mornings": _missed_mornings(recent, restarts, days, now),
        "full_logins": full_logins,
        "restarts": [r.to_dict() for r in restarts or [] if r.boot_ts >= since],
        "restarts_readable": restarts is not None,
        "criteria": {
            "unattended_pass": {"met": bool(passes), "date": passes[-1]["date"] if passes else None},
            "no_unexpected_logins": {"met": not unexpected, "count": len(unexpected)},
        },
        "met": bool(passes) and not unexpected,
    }


def _login_row(
    ts: float,
    source: str,
    restarts: list[windows_restarts.Restart] | None,
    now: float,
    login: relogin_reason.IbcLogin | None,
) -> dict[str, Any]:
    weekday = time.localtime(ts).tm_wday
    why = relogin_reason.explain(login or relogin_reason.IbcLogin(ts=ts, full_auth=True), restarts, now=now)
    return {
        "ts": ts,
        "source": source,
        "weekday": time.strftime("%a", time.localtime(ts)),
        # IBKR's own weekly re-login falls at the weekend; a phone login then
        # is expected, any other one is what #14 counts.
        "expected": weekday >= 5,
        "relogin": why,
    }


def _missed_mornings(
    runs: list[dict[str, Any]],
    restarts: list[windows_restarts.Restart] | None,
    days: int,
    now: float,
) -> list[dict[str, Any]]:
    ran = {r["date"] for r in runs if r["unattended"]}
    today = datetime.fromtimestamp(now).date()
    missed: list[dict[str, Any]] = []
    since = now - days * 86400
    for back in range(days, -1, -1):
        day = today - timedelta(days=back)
        check_start = _local(f"{day.isoformat()} {PREMARKET_CHECK_WINDOW_START}:00") or 0
        check_end = _local(f"{day.isoformat()} {PREMARKET_CHECK_WINDOW_END}:00") or 0
        if check_start < since or day.weekday() >= 5 or day.isoformat() in NOVA_OS_NYSE_HOLIDAYS or now < check_end:
            continue
        if day.isoformat() in ran:
            continue
        missed.append({"date": day.isoformat(), "reason": _missed_reason(day, restarts, now)})
    return missed


def _missed_reason(day: date, restarts: list[windows_restarts.Restart] | None, now: float) -> str:
    check_at = _local(f"{day.isoformat()} {PREMARKET_CHECK_WINDOW_START}:00") or 0
    for r in restarts or []:
        signed_in_late = r.first_signin_ts is None or r.first_signin_ts > check_at
        if check_at - 86400 < r.boot_ts <= check_at and signed_in_late:
            signin = "nobody signed in" if r.first_signin_ts is None else (
                f"nobody signed in until {time.strftime('%H:%M', time.localtime(r.first_signin_ts))}"
            )
            return (
                f"{relogin_reason.restart_phrase(r, now)} and {signin}; "
                "the scheduled tasks only run while you are signed in"
            )
    if restarts is None:
        return "no 03:55 run in morning-check.log (the Windows event log could not be read)"
    return "no 03:55 run in morning-check.log (the PC was asleep, off, or the task did not fire)"


def read_ibc_logins(log_dir: Path) -> list[relogin_reason.IbcLogin]:
    """Every Gateway start in every IBC log, oldest first."""
    logins: list[relogin_reason.IbcLogin] = []
    try:
        files = sorted(log_dir.glob("IBC-*.txt"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return []
    for path in files:
        try:
            logins += relogin_reason.parse_ibc_logins(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return sorted(logins, key=lambda l: l.ts or 0)


def render_text(ev: dict[str, Any]) -> str:
    crit = ev["criteria"]
    lines = [f"Premarket evidence for #14, last {ev['days']} days"]
    up = crit["unattended_pass"]
    lines.append(
        f"  [{'MET' if up['met'] else 'OPEN'}] unattended 03:55 RESULT PASS"
        + (f" -- latest {up['date']}" if up["date"] else " -- none in the window")
    )
    nu = crit["no_unexpected_logins"]
    lines.append(f"  [{'MET' if nu['met'] else 'OPEN'}] no weekday phone login -- {nu['count']} found")
    for row in ev["full_logins"]:
        tag = "weekend, expected" if row["expected"] else "UNEXPECTED"
        stamp = time.strftime("%a %Y-%m-%d %H:%M", time.localtime(row["ts"]))
        lines.append(f"      {stamp} ({tag}, {row['source']}): {row['relogin']['text']}")
    if ev["missed_mornings"]:
        lines.append("  Mornings with no unattended check:")
        for m in ev["missed_mornings"]:
            lines.append(f"      {m['date']}: {m['reason']}")
    if not ev["restarts_readable"]:
        lines.append("  Note: the Windows event log could not be read -- restarts are unknown, not absent.")
    lines.append(f"RESULT {'MET' if ev['met'] else 'OPEN'}")
    return "\n".join(lines)


def _local(text: str) -> float | None:
    try:
        return time.mktime(datetime.strptime(text, "%Y-%m-%d %H:%M:%S").timetuple())
    except ValueError:
        return None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("command", nargs="?", default="evidence", choices=("evidence", "relogin"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--days", type=int, default=PREMARKET_EVIDENCE_DAYS_DEFAULT)
    parser.add_argument("--log-dir", type=Path, default=LOG_DIR, help="Nova's backend/logs (default: this checkout's)")
    parser.add_argument("--ibc-log-dir", type=Path, default=relogin_reason.IBC_LOG_DIR)
    args = parser.parse_args(argv)

    if args.command == "relogin":
        why = relogin_reason.current(log_dir=args.ibc_log_dir)
        print(json.dumps(why, indent=1) if args.json else why["text"])
        return 0

    now = time.time()
    ev = build_evidence(
        runs=parse_morning_runs(_read(args.log_dir / "morning-check.log")),
        ibc_logins=read_ibc_logins(args.ibc_log_dir),
        launches=parse_gateway_launches(_read(args.log_dir / "daily-start.log")),
        restarts=windows_restarts.recent_restarts(args.days + 1),
        days=args.days,
        now=now,
    )
    print(json.dumps(ev, indent=1) if args.json else render_text(ev))
    return 0 if ev["met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
