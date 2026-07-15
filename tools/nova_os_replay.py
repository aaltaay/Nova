"""Replay / ask / evening-review CLI for Nova OS archive (P9).

Usage (from repo root; PYTHONPATH includes backend/):
  py tools/nova_os_replay.py days
  py tools/nova_os_replay.py replay 2026-07-10 [--symbol AAPL]      # hindsight=True, whole day
  py tools/nova_os_replay.py at 2026-07-10 --ts 1720000000 [--symbol AAPL]  # no-hindsight, one moment
  py tools/nova_os_replay.py walk 2026-07-10 [--symbol AAPL] [--step 5]     # no-hindsight rewind timeline
  py tools/nova_os_replay.py ask --symbol AAPL --date 2026-07-10
  py tools/nova_os_replay.py review 2026-07-10
  py tools/nova_os_replay.py health

Does not place orders. Replay/at/walk all use decide(record=False). Prefer
`at`/`walk` over plain `replay` when the goal is testing decision quality —
`replay` feeds decide() the whole day at once and says so (hindsight=True).
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
        description="Nova OS archive replay / ask / evening review (no orders).",
    )
    parser.add_argument("--json", action="store_true", help="Raw JSON output")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("days", help="List local cold archive days")
    sub.add_parser("health", help="Archive + R2 health snapshot")

    p_replay = sub.add_parser("replay", help="Replay a day through decide(record=False) (hindsight=True)")
    p_replay.add_argument("date", help="YYYY-MM-DD")
    p_replay.add_argument("--symbol", action="append", dest="symbols", help="Limit symbols")
    p_replay.add_argument("--limit", type=int, default=20)

    p_at = sub.add_parser("at", help="No-hindsight decision as of one moment in the day")
    p_at.add_argument("date", help="YYYY-MM-DD")
    p_at.add_argument("--ts", type=float, required=True, help="Unix timestamp (decide() sees bars <= this only)")
    p_at.add_argument("--symbol", action="append", dest="symbols", help="Limit symbols")
    p_at.add_argument("--limit", type=int, default=20)

    p_walk = sub.add_parser("walk", help="No-hindsight decision timeline for a day (rewind)")
    p_walk.add_argument("date", help="YYYY-MM-DD")
    p_walk.add_argument("--symbol", action="append", dest="symbols", help="Limit symbols")
    p_walk.add_argument("--limit", type=int, default=10)
    p_walk.add_argument("--step", type=float, default=None, help="Minutes between as-of snapshots")

    p_ask = sub.add_parser("ask", help="Find journal trades + archive index")
    p_ask.add_argument("--symbol", default=None)
    p_ask.add_argument("--date", dest="session_date", default=None)

    p_review = sub.add_parser("review", help="Evening review heuristic for a day")
    p_review.add_argument("date", help="YYYY-MM-DD")
    p_review.add_argument("--horizon", type=int, default=None, help="Minutes ahead")

    args = parser.parse_args()

    if args.cmd == "days":
        from archive.health import list_local_cold_days
        data = {"days": list_local_cold_days()}
    elif args.cmd == "health":
        from archive.health import archive_health
        data = archive_health()
    elif args.cmd == "replay":
        from archive.replay import replay_day
        data = replay_day(
            args.date,
            symbols=args.symbols,
            max_symbols=args.limit,
        )
    elif args.cmd == "at":
        from archive.replay import replay_at
        data = replay_at(
            args.date,
            args.ts,
            symbols=args.symbols,
            max_symbols=args.limit,
        )
    elif args.cmd == "walk":
        from archive.replay import walk_day
        from constants import ARCHIVE_REPLAY_WALK_STEP_MIN
        data = walk_day(
            args.date,
            symbols=args.symbols,
            max_symbols=args.limit,
            step_min=args.step if args.step is not None else ARCHIVE_REPLAY_WALK_STEP_MIN,
        )
    elif args.cmd == "ask":
        from archive.ask import ask
        data = ask(symbol=args.symbol, session_date=args.session_date)
    elif args.cmd == "review":
        from archive.evening_review import evening_review
        from constants import ARCHIVE_EVENING_REVIEW_HORIZON_MIN
        data = evening_review(
            args.date,
            horizon_min=args.horizon or ARCHIVE_EVENING_REVIEW_HORIZON_MIN,
        )
    else:
        parser.error(f"unknown command {args.cmd}")
        return

    if args.json or args.cmd in ("health", "ask", "review"):
        print(json.dumps(data, indent=2, default=str))
        return

    if args.cmd == "days":
        for d in data.get("days") or []:
            print(d)
        return

    if args.cmd in ("replay", "at"):
        hindsight = data.get("hindsight")
        print(
            f"session={data.get('session_date')} as_of={data.get('as_of_ts')} "
            f"hindsight={hindsight} decisions={data.get('decision_count')}"
        )
        for row in data.get("decisions") or []:
            print(
                f"  {row.get('symbol')} → {row.get('decision')} "
                f"conf={row.get('confidence')} reasons={', '.join(row.get('reason_codes') or [])}"
            )
        for err in data.get("errors") or []:
            print(f"  ERROR {err.get('symbol')}: {err.get('error')}", file=sys.stderr)
        return

    if args.cmd == "walk":
        print(f"session={data.get('session_date')} step_min={data.get('step_min')} steps={data.get('step_count')}")
        for step in data.get("steps") or []:
            print(f"  [{step.get('as_of_iso')}]")
            for row in step.get("decisions") or []:
                print(f"    {row.get('symbol')} → {row.get('decision')} conf={row.get('confidence')}")
        return

    print(json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    main()
