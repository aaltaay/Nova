"""Pass 2: regular-session minute bars for the selected symbol-days only.

Reads each day's flat file once more and keeps the 09:30-16:00 bars of the tickers in
``selection`` for that day (top-30 wide), so the simulator never touches the raw files.

Usage:
    py -3 research/orb/extract_minutes.py                       # ORB: selection -> minutes_selected
    py -3 research/orb/extract_minutes.py --selection gng_selection --table minutes_gng
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime

from common import MINUTE_SOURCE_SQL, connect, load_env, minute_files

SCHEMA = """
CREATE TABLE IF NOT EXISTS {table} (
    ticker VARCHAR, d DATE, t TIME,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT);
CREATE TABLE IF NOT EXISTS {days} (d DATE PRIMARY KEY, symbols INTEGER, rows BIGINT, built_at TIMESTAMP);
"""

EXTRACT_SQL = (
    "INSERT INTO @TABLE@ "
    "WITH m AS (" + MINUTE_SOURCE_SQL + ") "
    "SELECT ticker, ?::DATE, t, open, high, low, close, volume FROM m "
    "WHERE t >= TIME '@START@' AND t < TIME '16:00' "
    "  AND ticker IN (SELECT ticker FROM @SELECTION@ WHERE d = ?::DATE)"
)  # @tokens@, not str.format: the minute source SQL carries a DuckDB struct literal in braces


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selection", default="selection")
    ap.add_argument("--table", default="minutes_selected")
    ap.add_argument("--start", default="09:30", help="first bar time kept (04:00 to keep pre-market)")
    a = ap.parse_args()
    days_table = "extracted_days" if a.table == "minutes_selected" else f"{a.table}_days"
    con = connect()
    con.execute(SCHEMA.format(table=a.table, days=days_table))
    sql = EXTRACT_SQL.replace("@TABLE@", a.table).replace("@SELECTION@", a.selection).replace("@START@", a.start)
    files = minute_files()
    wanted = [r[0] for r in con.execute(f"SELECT DISTINCT d FROM {a.selection} ORDER BY d").fetchall()]
    done = {r[0] for r in con.execute(f"SELECT d FROM {days_table}").fetchall()}
    todo = [d for d in wanted if d not in done and d in files]
    print(f"{a.table}: {len(done)} days extracted, {len(todo)} to extract", flush=True)
    for i, d in enumerate(todo, 1):
        t0 = time.time()
        con.execute("BEGIN")
        con.execute(f"DELETE FROM {a.table} WHERE d = ?", [d])
        con.execute(sql, [str(files[d]), d, d])
        n_sym, n_rows = con.execute(
            f"SELECT count(DISTINCT ticker), count(*) FROM {a.table} WHERE d = ?", [d]
        ).fetchone()
        con.execute(f"INSERT OR REPLACE INTO {days_table} VALUES (?, ?, ?, ?)", [d, n_sym, n_rows, datetime.now()])
        con.execute("COMMIT")
        if i % 25 == 0 or i == len(todo):
            print(f"  {d} symbols={n_sym} rows={n_rows} {time.time() - t0:.1f}s  ({i}/{len(todo)})", flush=True)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
