"""Pre-market and first-half-hour facts per symbol-day, for the Gap and Go candidate.

One row per ticker per day in ``premarket``: pre-market high / low / last / volume / bar
count (04:00-09:30 ET), the 09:30-10:00 high / low / volume, and the 09:30-10:00 close.
Same honesty as ``open5``: each row is built from its own day's file only.

Usage:
    py -3 research/orb/build_premarket.py
"""
from __future__ import annotations

import time
from datetime import datetime

from common import MINUTE_SOURCE_SQL, connect, load_env, minute_files

SCHEMA = """
CREATE TABLE IF NOT EXISTS premarket (
    ticker VARCHAR, d DATE,
    pm_high DOUBLE, pm_low DOUBLE, pm_last DOUBLE, pm_volume BIGINT, pm_bars INTEGER,
    pm_high_t TIME,
    h30 DOUBLE, l30 DOUBLE, v30 BIGINT, c30 DOUBLE,
    PRIMARY KEY (ticker, d));
CREATE TABLE IF NOT EXISTS premarket_days (d DATE PRIMARY KEY, tickers INTEGER, seconds DOUBLE, built_at TIMESTAMP);
"""

DAY_SQL = (
    "INSERT OR REPLACE INTO premarket "
    "WITH m AS (" + MINUTE_SOURCE_SQL + ") "
    "SELECT ticker, ?::DATE AS d, "
    "  max(high) FILTER (WHERE t < TIME '09:30'), "
    "  min(low) FILTER (WHERE t < TIME '09:30'), "
    "  last(close ORDER BY t) FILTER (WHERE t < TIME '09:30'), "
    "  coalesce(sum(volume) FILTER (WHERE t < TIME '09:30'), 0), "
    "  count(*) FILTER (WHERE t < TIME '09:30'), "
    "  arg_max(t, high) FILTER (WHERE t < TIME '09:30'), "
    "  max(high) FILTER (WHERE t >= TIME '09:30' AND t < TIME '10:00'), "
    "  min(low) FILTER (WHERE t >= TIME '09:30' AND t < TIME '10:00'), "
    "  coalesce(sum(volume) FILTER (WHERE t >= TIME '09:30' AND t < TIME '10:00'), 0), "
    "  last(close ORDER BY t) FILTER (WHERE t >= TIME '09:30' AND t < TIME '10:00') "
    "FROM m GROUP BY ticker"
)


def main() -> int:
    load_env()
    con = connect()
    con.execute(SCHEMA)
    files = minute_files()
    done = {r[0] for r in con.execute("SELECT d FROM premarket_days").fetchall()}
    todo = [d for d in files if d not in done]
    print(f"premarket: {len(done)} days built, {len(todo)} to build", flush=True)
    for i, d in enumerate(todo, 1):
        t0 = time.time()
        con.execute("BEGIN")
        con.execute("DELETE FROM premarket WHERE d = ?", [d])
        con.execute(DAY_SQL, [str(files[d]), d])
        n = con.execute("SELECT count(*) FROM premarket WHERE d = ?", [d]).fetchone()[0]
        con.execute("INSERT OR REPLACE INTO premarket_days VALUES (?, ?, ?, ?)", [d, n, time.time() - t0, datetime.now()])
        con.execute("COMMIT")
        if i % 50 == 0 or i == len(todo):
            print(f"  {d} tickers={n} {time.time() - t0:.1f}s  ({i}/{len(todo)})", flush=True)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
