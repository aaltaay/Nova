"""Build the symbol-days the backfill explains (``targets``).

  pillars      every Five Pillars gap candidate without the news pillar (``pillars_all`` from
               ``research/orb/select_gng.py --no-float --no-news``): cutoff 09:30 ET
  leaderboard  every name that reached the rebuilt whole-market board's top 10 inside the desk's
               tradeable band: cutoff = the first minute it got there

The window opens at the prior session's 16:00 ET close and the store keeps items to 20:00 ET so a
later cutoff (a trade's entry time) can be asked of the same rows. A symbol-day in both keeps
the earlier cutoff.

Usage:  py -3 research/catalysts/build_targets.py
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime

import duckdb

from cat_config import (ET, LB_MAX_PRICE, LB_MIN_PRICE, LB_MIN_VOLUME, LB_TOP_RANK, LEADERBOARD_DB,
                        RESEARCH_CUTOFF_ET, RESEARCH_DB, WINDOW_END_ET, WINDOW_OPEN_ET, et_ts)
from store import connect


def trading_days(rs: duckdb.DuckDBPyConnection) -> list[date]:
    return [r[0] for r in rs.execute("SELECT DISTINCT d FROM daily_days ORDER BY d").fetchall()]


def prev_day(days: list[date], d: date) -> date | None:
    import bisect
    i = bisect.bisect_left(days, d)
    return days[i - 1] if i > 0 else None


def main() -> int:
    rs = duckdb.connect(str(RESEARCH_DB), read_only=True)
    days = trading_days(rs)
    out: dict[tuple[str, str], list] = {}
    for ticker, d, prev_d in rs.execute("SELECT ticker, d, prev_d FROM pillars_all").fetchall():
        if prev_d is None:
            continue
        out[(ticker, d.isoformat())] = [et_ts(prev_d, WINDOW_OPEN_ET), et_ts(d, RESEARCH_CUTOFF_ET),
                                        et_ts(d, WINDOW_END_ET), "pillars"]
    rs.close()
    lb = sqlite3.connect(f"file:{LEADERBOARD_DB.as_posix()}?mode=ro", uri=True)
    rows = lb.execute(
        "SELECT symbol, min(minute_ts) FROM rows WHERE source = 'reconstructed' AND board = 'market' "
        "AND rank <= ? AND price BETWEEN ? AND ? AND volume >= ? GROUP BY symbol, "
        "CAST((minute_ts - 4 * 3600) / 86400 AS INTEGER)",  # one row per symbol per (approximate) ET day
        [LB_TOP_RANK, LB_MIN_PRICE, LB_MAX_PRICE, LB_MIN_VOLUME]).fetchall()
    lb.close()
    n_lb = 0
    for sym, first_ts in rows:
        d = datetime.fromtimestamp(first_ts, ET).date()
        p = prev_day(days, d)
        if p is None:
            continue
        key = (sym, d.isoformat())
        n_lb += 1
        if key in out:
            out[key][1] = min(out[key][1], float(first_ts))
            out[key][3] = "both"
        else:
            out[key] = [et_ts(p, WINDOW_OPEN_ET), float(first_ts), et_ts(d, WINDOW_END_ET), "leaderboard"]
    con = connect()
    with con:
        con.executemany("INSERT OR REPLACE INTO targets VALUES (?,?,?,?,?,?)",
                        [(k[0], k[1], *v) for k, v in out.items()])
    by = dict(con.execute("SELECT origin, count(*) FROM targets GROUP BY 1").fetchall())
    span = con.execute("SELECT min(session_date), max(session_date), count(DISTINCT session_date) FROM targets").fetchone()
    print(f"targets: {sum(by.values())} symbol-days {by}; leaderboard movers offered {n_lb}; "
          f"{span[2]} days {span[0]}..{span[1]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
