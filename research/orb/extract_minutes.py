"""Pass 2: regular-session minute bars for the selected symbol-days only.

Reads each day's flat file once more and keeps the 09:30-16:00 bars of the tickers in
``selection`` for that day (top-30 wide), so the simulator never touches the raw files.

Usage:
    py -3 research/orb/extract_minutes.py
"""
from __future__ import annotations

import time
from datetime import datetime

from common import MINUTE_SOURCE_SQL, connect, load_env, minute_files

SCHEMA = """
CREATE TABLE IF NOT EXISTS minutes_selected (
    ticker VARCHAR, d DATE, t TIME,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT);
CREATE TABLE IF NOT EXISTS extracted_days (d DATE PRIMARY KEY, symbols INTEGER, rows BIGINT, built_at TIMESTAMP);
"""

EXTRACT_SQL = (
    "INSERT INTO minutes_selected "
    "WITH m AS (" + MINUTE_SOURCE_SQL + ") "
    "SELECT ticker, ?::DATE, t, open, high, low, close, volume FROM m "
    "WHERE t >= TIME '09:30' AND t < TIME '16:00' "
    "  AND ticker IN (SELECT ticker FROM selection WHERE d = ?::DATE)"
)


def main() -> int:
    load_env()
    con = connect()
    con.execute(SCHEMA)
    files = minute_files()
    wanted = [r[0] for r in con.execute("SELECT DISTINCT d FROM selection ORDER BY d").fetchall()]
    done = {r[0] for r in con.execute("SELECT d FROM extracted_days").fetchall()}
    todo = [d for d in wanted if d not in done and d in files]
    print(f"minutes_selected: {len(done)} days extracted, {len(todo)} to extract", flush=True)
    for i, d in enumerate(todo, 1):
        t0 = time.time()
        con.execute("BEGIN")
        con.execute("DELETE FROM minutes_selected WHERE d = ?", [d])
        con.execute(EXTRACT_SQL, [str(files[d]), d, d])
        n_sym, n_rows = con.execute(
            "SELECT count(DISTINCT ticker), count(*) FROM minutes_selected WHERE d = ?", [d]
        ).fetchone()
        con.execute("INSERT OR REPLACE INTO extracted_days VALUES (?, ?, ?, ?)", [d, n_sym, n_rows, datetime.now()])
        con.execute("COMMIT")
        if i % 25 == 0 or i == len(todo):
            print(f"  {d} symbols={n_sym} rows={n_rows} {time.time() - t0:.1f}s  ({i}/{len(todo)})", flush=True)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
