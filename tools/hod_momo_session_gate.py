"""Orchestrate HOD/scanner session gates for local IBKR verification.

Usage (API running)::

    py -3 tools/hod_momo_session_gate.py --profile ah_slo
    py -3 tools/hod_momo_session_gate.py --profile rth_slo --json

Exit codes:
  0 = pass
  1 = warn / incomplete
  2 = fail
  3 = BLOCKED (Gateway down / wrong discovery / API unreachable)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parents[1]


def _fetch(url: str) -> dict:
    # Integrity can take 10–20s when the API event loop is busy (IBKR L1 churn).
    # 8s falsely classified healthy-but-slow API as BLOCKED and killed the observe loop.
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _run_tool(script: str, args: list[str]) -> int:
    cmd = [sys.executable, str(ROOT / "tools" / script), *args]
    return subprocess.call(cmd, cwd=str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Nova HOD session gate")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument(
        "--profile",
        choices=("premarket_slo", "rth_slo", "ah_slo", "integrity_only"),
        default="integrity_only",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--latency-seconds", type=float, default=60.0)
    args = parser.parse_args()
    base = args.url.rstrip("/")

    try:
        health = _fetch(base + "/api/health")
    except Exception as exc:
        print(f"SESSION GATE BLOCKED: API unreachable ({exc})", file=sys.stderr)
        return 3

    try:
        ibkr = _fetch(base + "/api/ibkr/status")
    except Exception as exc:
        print(f"SESSION GATE BLOCKED: /api/ibkr/status failed ({exc})", file=sys.stderr)
        return 3

    connected = bool(ibkr.get("connected"))
    if not connected:
        print(
            "SESSION GATE BLOCKED: IB Gateway not connected "
            "(log in to Gateway / complete 2FA)",
            file=sys.stderr,
        )
        return 3

    integrity_code = _run_tool(
        "hod_momo_integrity_check.py",
        ["--url", base] + (["--json"] if args.json else []),
    )
    if integrity_code == 2:
        print("SESSION GATE FAIL: integrity status=fail", file=sys.stderr)
        return 2

    if args.profile == "integrity_only":
        # warn (exit 1) is armable — only hard fail blocks parity / DoD.
        if integrity_code == 1:
            print("SESSION GATE PASS (warn) profile=integrity_only")
            return 0
        print("SESSION GATE PASS profile=integrity_only")
        return 0

    # Latency probe for live freshness SLO (shorter default; use 900 for RTH claim).
    seconds = args.latency_seconds
    if args.profile == "rth_slo" and seconds < 900:
        seconds = 900.0
    lat_code = _run_tool(
        "hod_momo_latency_probe.py",
        [
            "--url", base,
            "--seconds", str(seconds),
            "--interval", "5",
        ] + (["--json"] if args.json else []),
    )
    if lat_code == 2:
        print("SESSION GATE FAIL: latency probe failed", file=sys.stderr)
        return 2
    if integrity_code == 1 or lat_code == 1:
        return 1
    print(
        f"SESSION GATE PASS profile={args.profile} "
        f"health={health.get('status')} ibkr=connected"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
