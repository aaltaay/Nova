"""S5, the rolling universe, read back from the rebuilt leaderboard (ADR 022).

"Top-3 % gainer with at least 5x relative volume at the minute of the trade"
(knowledge/obsidian/03-Nova-Decisions/Bot-Trading-Plan.md section 2f): for each
stored minute of a reconstructed day, ``leader_symbols(rows, S5_RULES)`` over that
minute's ``board="market"`` rows. The builder stores every row S5 would pick, so this
is exact, and the ranking is the same function playback and live auto-record call.
RVOL here is ``time_of_day_20`` -- never the desk's daily-average RVOL.

Usage (from the repo root):
    py -3 research/leaderboard/s5_universe.py --date 2026-09-21 --from 07:00 --to 09:30
    py -3 research/leaderboard/s5_universe.py --date 2026-09-21 --all --json s5.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from constants_leaderboard import LEADERBOARD_BOARD_MARKET, LEADERBOARD_SOURCE_RECONSTRUCTED  # noqa: E402
from leaderboard import store  # noqa: E402
from leaderboard.ranking import S5_RULES, leader_symbols  # noqa: E402
from leaderboard.schema import ROW_COLUMNS  # noqa: E402

ET = ZoneInfo("America/New_York")


def s5_by_minute(db: sqlite3.Connection, session_date: str) -> list[tuple[int, list[str]]]:
    """(minute_ts, S5 symbols in rank order) for every rebuilt minute of the day, in order."""
    minutes = store.coverage_minutes(db, session_date, LEADERBOARD_SOURCE_RECONSTRUCTED)
    grouped: dict[int, list[dict]] = {m: [] for m in minutes}
    cur = db.execute(
        f"SELECT {', '.join(ROW_COLUMNS)} FROM rows WHERE session_date = ? AND source = ? AND board = ?"
        " ORDER BY minute_ts, rank",
        (session_date, LEADERBOARD_SOURCE_RECONSTRUCTED, LEADERBOARD_BOARD_MARKET),
    )
    for row in cur:
        grouped.setdefault(int(row[1]), []).append(dict(zip(ROW_COLUMNS, row)))
    return [(m, leader_symbols(grouped[m], S5_RULES)) for m in sorted(grouped)]


def _et(ts: int) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True)
    ap.add_argument("--from", dest="start", default="04:01", help="first minute, HH:MM ET")
    ap.add_argument("--to", dest="end", default="20:00", help="last minute, HH:MM ET")
    ap.add_argument("--all", action="store_true", help="print every minute, not only changes")
    ap.add_argument("--json", type=Path, help="write [{minute_ts, et, symbols}] here")
    ap.add_argument("--db", type=Path, default=None)
    args = ap.parse_args()
    d = date.fromisoformat(args.date)
    with store.connect(args.db) as db:
        universe = s5_by_minute(db, d.isoformat())
    if not universe:
        print(f"no reconstructed minutes stored for {d} -- run build_leaderboard.py first")
        return 1
    lo, hi = (datetime.combine(d, datetime.strptime(x, "%H:%M").time(), ET).timestamp() for x in (args.start, args.end))
    picked = [(m, syms) for m, syms in universe if lo <= m <= hi]
    last: list[str] | None = None
    for m, syms in picked:
        if args.all or syms != last:
            print(f"{_et(m)}  {' '.join(syms) if syms else '(none)'}")
        last = syms
    names = sorted({s for _, syms in picked for s in syms})
    print(f"{len(picked)} minutes, {sum(1 for _, s in picked if s)} with a pick, {len(names)} names: {' '.join(names)}")
    if args.json:
        args.json.write_text(json.dumps([{"minute_ts": m, "et": _et(m), "symbols": s} for m, s in picked]), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
