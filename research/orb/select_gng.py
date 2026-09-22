"""Gap and Go selection -- the Five Pillars at 09:30, mechanically (pre-registered 2026-09-22).

A symbol-day is a candidate when, using only what is known by 09:30 ET that day:
  price     the 09:30 open is between --min-price and --max-price ($2..$20)
  gap       09:30 open vs the prior regular-session close is at least --min-gap (10%)
  rvol      pre-market volume is at least --min-rvol (5x) its average over the prior 14
            sessions and at least --min-pm-volume shares (a floor so 5 x nothing is nothing)
  catalyst  at least one news article tagged with the ticker, published after the prior
            session's close and before 09:30 (``news_tickers.session_d = d``)
  float     shares outstanding at or under --max-float (20M) from ticker details -- current
            values, not point-in-time; ``--no-float`` runs the variant without this pillar
Funds / derivatives and split-window days are excluded as in the ORB selection. Candidates
are ranked per day by pre-market relative volume; ``--top`` kept wide for robustness.

Usage:
    py -3 research/orb/select_gng.py --top 20
    py -3 research/orb/select_gng.py --top 20 --no-float --table gng_selection_nofloat
"""
from __future__ import annotations

import argparse
import time

from common import connect, load_env

SELECT_SQL = """
CREATE OR REPLACE TABLE {table} AS
WITH base AS (
    SELECT o.ticker, o.d, o.o5_open, o.o5_high, o.o5_low, o.o5_close, o.o5_volume, o.o5_bars,
           o.rth_high, o.rth_low, o.rth_close, o.rth_volume,
           p.pm_high, p.pm_low, p.pm_last, p.pm_volume, p.pm_bars, p.pm_high_t, p.h30, p.l30, p.v30,
           lag(o.rth_close) OVER w AS prev_close,
           lag(o.d) OVER w AS prev_d,
           avg(o.rth_volume) OVER w14 AS adv14,
           avg(p.pm_volume) OVER w14 AS avg_pm14,
           count(*) OVER w14 AS n14
    FROM open5 o
    JOIN premarket p USING (ticker, d)
    WINDOW w AS (PARTITION BY o.ticker ORDER BY o.d),
           w14 AS (PARTITION BY o.ticker ORDER BY o.d ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING)
), cand AS (
    SELECT b.*,
           b.o5_open / b.prev_close - 1 AS gap,
           b.pm_volume / greatest(b.avg_pm14, 1000) AS rvol_pm,
           (SELECT count(*) FROM news_tickers n WHERE n.ticker = b.ticker AND n.session_d = b.d) AS news_n,
           td.shares_outstanding AS float_shares, td.market_cap
    FROM base b
    LEFT JOIN ticker_details td ON td.ticker = b.ticker
    WHERE b.n14 >= 14 AND b.o5_bars >= 1 AND b.prev_close > 0 AND b.pm_high IS NOT NULL
      AND b.o5_open BETWEEN ? AND ?
      AND b.o5_open / b.prev_close - 1 >= ?
      AND b.pm_volume >= ?
      AND b.pm_volume / greatest(b.avg_pm14, 1000) >= ?
      AND b.ticker NOT IN (SELECT ticker FROM tickers WHERE type IS NOT NULL AND type NOT IN ('CS', 'ADRC'))
      AND NOT EXISTS (SELECT 1 FROM splits s WHERE s.ticker = b.ticker
                      AND s.execution_date BETWEEN b.d - INTERVAL 30 DAY AND b.d)
), pillars AS (
    SELECT *, CASE WHEN o5_close > o5_open THEN 'long' WHEN o5_close < o5_open THEN 'short' ELSE 'doji' END AS o5_dir
    FROM cand
    WHERE news_n >= 1
      AND ({no_float} OR (float_shares IS NOT NULL AND float_shares <= ?))
), ranked AS (
    SELECT *, row_number() OVER (PARTITION BY d ORDER BY rvol_pm DESC, ticker) AS rank FROM pillars
)
SELECT * FROM ranked WHERE rank <= ?
"""


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", default="gng_selection")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--min-price", type=float, default=2.0)
    ap.add_argument("--max-price", type=float, default=20.0)
    ap.add_argument("--min-gap", type=float, default=0.10)
    ap.add_argument("--min-rvol", type=float, default=5.0)
    ap.add_argument("--min-pm-volume", type=float, default=100_000)
    ap.add_argument("--max-float", type=float, default=20e6)
    ap.add_argument("--no-float", action="store_true")
    a = ap.parse_args()
    con = connect()
    t0 = time.time()
    sql = SELECT_SQL.format(table=a.table, no_float="TRUE" if a.no_float else "FALSE")
    con.execute(sql, [a.min_price, a.max_price, a.min_gap, a.min_pm_volume, a.min_rvol, a.max_float, a.top])
    row = con.execute(
        f"SELECT count(*), count(DISTINCT d), min(d), max(d), median(gap), median(rvol_pm), "
        f"count(*) FILTER (WHERE o5_open < pm_high) FROM {a.table}"
    ).fetchone()
    print(f"{a.table}: {row[0]} symbol-days over {row[1]} days {row[2]}..{row[3]}; median gap {row[4]:.1%}, "
          f"median pm rvol {row[5]:.1f}x; {row[6]} open below the pre-market high (entry possible) "
          f"in {time.time() - t0:.1f}s", flush=True)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
