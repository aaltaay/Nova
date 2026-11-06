"""What was known about each stock-day beyond its prices -- news, halts, relative volume -- into the day movers store
(ADR 050, ADR 059).

The desk's agent search (``/api/agent/movers``) filters by news, halts and relative volume, but the backend never
reads the research stores they live in (the catalyst backfill, the relative-volume table). This export writes them,
per movers row, into the store's ``day_facts`` table (``backend/day_movers/facts.py`` reads and filters it) through
the one join the research front door uses (``market_reads.day_facts.for_pairs``: catalyst, halts, rvol), so a
stock-day passes the same filter in both searches. A row with nothing known is not written (no row reads unknown).

Replaces the table whole in one transaction (a reader sees the old table until the new one is complete); run it
again after the movers index, the catalyst backfill, the halt log or the relative-volume table changes. It reads
every relative-volume day file: a heavy run, outside 04:00-20:00 ET.

Usage (from the repo root):
    py -3 research/movers/export_day_facts.py [--db PATH] [--days-per-read N]
"""
from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "research"))
sys.path.insert(0, str(REPO / "backend"))

from day_movers import facts, store  # noqa: E402
from day_movers.schema import DAY_FACT_COLUMNS  # noqa: E402

PARTS = ("catalyst", "halts", "rvol")
DAYS_PER_READ = 20


def _days(db_path: Path) -> list[str]:
    db = store.read_only(db_path)
    if db is None:
        raise SystemExit(f"{db_path}: the movers index is not built (py -3 research/movers/build_movers.py)")
    with closing(db):
        return [r[0] for r in db.execute("SELECT session_date FROM sessions ORDER BY session_date")]


def _pairs(db_path: Path, days: list[str]) -> list[tuple[str, str]]:
    with closing(store.read_only(db_path)) as db:
        sql = f"SELECT session_date, symbol FROM movers WHERE session_date IN ({', '.join('?' * len(days))})"
        return [(r[0], r[1]) for r in db.execute(sql + " ORDER BY session_date, symbol", days)]


def rows(db_path: Path, days_per_read: int = DAYS_PER_READ,
         say: Callable[[str], None] = print) -> Iterator[dict[str, Any]]:
    """Every movers row's known facts (``DAY_FACT_COLUMNS``), oldest session first, read ``days_per_read`` sessions
    at a time. A pair with nothing known yields nothing."""
    from market_reads import day_facts
    days = _days(db_path)
    started, written = time.time(), 0
    for i in range(0, len(days), days_per_read):
        part = days[i:i + days_per_read]
        found = day_facts.for_pairs(_pairs(db_path, part), parts=PARTS)
        for (day, symbol), known in found.items():
            values = {key: known.get(key) for key in facts.FACT_KEYS}
            if any(v is not None for v in values.values()):
                written += 1
                yield {"session_date": day, "symbol": symbol, **values}
        say(f"day facts: {part[-1]} ({i + len(part):,} of {len(days):,} sessions, {written:,} rows, "
            f"{time.time() - started:.0f} s)")


def export(db_path: Path, days_per_read: int = DAYS_PER_READ, say: Callable[[str], None] = print) -> int:
    """The whole ``day_facts`` table, from the stores the research front door reads; the rows written."""
    stream = rows(db_path, days_per_read, say)
    with store.connect(db_path) as db:
        return store.replace_day_facts(db, stream)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", type=Path, default=store.path())
    ap.add_argument("--days-per-read", dest="days_per_read", type=int, default=DAYS_PER_READ)
    args = ap.parse_args(argv)
    started = time.time()
    written = export(args.db, args.days_per_read, lambda line: print(line, flush=True))
    print(f"day_facts: {written:,} rows ({', '.join(DAY_FACT_COLUMNS[2:])}); {time.time() - started:.0f} s "
          f"-> {args.db}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
