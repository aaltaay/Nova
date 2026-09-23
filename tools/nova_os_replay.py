"""Cold-archive CLI: days / ask / health (P9).

Usage (from repo root; PYTHONPATH includes backend/):
  py tools/nova_os_replay.py days
  py tools/nova_os_replay.py ask --symbol AAPL --date 2026-07-10
  py tools/nova_os_replay.py health

Does not place orders. The decide() replay commands (replay / at / walk /
review) were retired with the Nova OS verdict (ADR 025).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cold archive days / ask / health (no orders).",
    )
    parser.add_argument("--json", action="store_true", help="Raw JSON output")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("days", help="List local cold archive days")
    sub.add_parser("health", help="Archive + R2 health snapshot")

    p_ask = sub.add_parser("ask", help="Find journal trades + archive index")
    p_ask.add_argument("--symbol", default=None)
    p_ask.add_argument("--date", dest="session_date", default=None)

    args = parser.parse_args()

    if args.cmd == "days":
        from archive.health import list_local_cold_days
        data = {"days": list_local_cold_days()}
    elif args.cmd == "health":
        from archive.health import archive_health
        data = archive_health()
    elif args.cmd == "ask":
        from archive.ask import ask
        data = ask(symbol=args.symbol, session_date=args.session_date)
    else:
        parser.error(f"unknown command {args.cmd}")
        return

    if args.json or args.cmd in ("health", "ask"):
        print(json.dumps(data, indent=2, default=str))
        return

    if args.cmd == "days":
        for d in data.get("days") or []:
            print(d)
        return

    print(json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    main()
