"""The 5-minute Bollinger signal tables in `bb_mr.duckdb`: `sig_5m_ext` and `sig_5m_rth`.

Bars are built from every 1-minute bar of each target ticker, so a band's warmup crosses days,
then only symbol-days with a lower-band rejection inside Universe A or B are kept. Rebuilt from the
stored tables when the builders moved into the repo (#1068): this SQL reproduces the lab-built rows
exactly (bar index, OHLCV and every band).

Needs, on the connection: the `src_1m` view, `meta_univ_a` and `ub_scanner_top20`.
"""
from __future__ import annotations

import time

import duckdb

SESSION_END_MIN = 960  # 16:00 ET, minutes after midnight
SESSION_FIRST_OPEN = {"sig_5m_ext": 240, "sig_5m_rth": 570}  # 04:00 ET extended warmup, 09:30 ET regular

_WINDOW_SQL = """
SELECT ticker, d, close_min,
       (row_number() OVER (PARTITION BY ticker ORDER BY d, close_min) - 1)::INTEGER AS bar_idx,
       open, high, low, close, volume,
       count(*) OVER w20 AS n20, avg(close) OVER w20 AS sma20, stddev_pop(close) OVER w20 AS std20,
       count(*) OVER w50 AS n50, avg(close) OVER w50 AS sma50, stddev_pop(close) OVER w50 AS std50,
       count(*) OVER w100 AS n100, avg(close) OVER w100 AS sma100, stddev_pop(close) OVER w100 AS std100,
       count(*) OVER w200 AS n200, avg(close) OVER w200 AS sma200, stddev_pop(close) OVER w200 AS std200
FROM (
    SELECT ticker, d, ((open_min // 5 + 1) * 5)::SMALLINT AS close_min,
           first(open ORDER BY open_min) AS open, max(high) AS high, min(low) AS low,
           last(close ORDER BY open_min) AS close, sum(volume) AS volume
    FROM src_1m WHERE open_min >= {first_open} AND open_min < {end}
    GROUP BY 1, 2, 3
)
WINDOW w20  AS (PARTITION BY ticker ORDER BY d, close_min ROWS BETWEEN 19  PRECEDING AND CURRENT ROW),
       w50  AS (PARTITION BY ticker ORDER BY d, close_min ROWS BETWEEN 49  PRECEDING AND CURRENT ROW),
       w100 AS (PARTITION BY ticker ORDER BY d, close_min ROWS BETWEEN 99  PRECEDING AND CURRENT ROW),
       w200 AS (PARTITION BY ticker ORDER BY d, close_min ROWS BETWEEN 199 PRECEDING AND CURRENT ROW)
"""

_SIGNAL_DAYS_SQL = """
WITH active_sig_days AS (
    SELECT DISTINCT w.ticker, w.d
    FROM {source} w
    LEFT JOIN meta_univ_a ua ON ua.ticker = w.ticker AND ua.d = w.d
    LEFT JOIN ub_scanner_top20 ub ON ub.ticker = w.ticker AND ub.d = w.d AND ub.close_min = w.close_min
    WHERE (ua.ticker IS NOT NULL OR ub.ticker IS NOT NULL)
      AND (
           (w.n20 = 20 AND w.low <= w.sma20 - 2.0 * w.std20 AND w.close > w.sma20 - 2.5 * w.std20)
        OR (w.n50 = 50 AND w.low <= w.sma50 - 2.0 * w.std50 AND w.close > w.sma50 - 2.5 * w.std50)
        OR (w.n100 = 100 AND w.low <= w.sma100 - 2.0 * w.std100 AND w.close > w.sma100 - 2.5 * w.std100)
        OR (w.n200 = 200 AND w.low <= w.sma200 - 2.0 * w.std200 AND w.close > w.sma200 - 2.5 * w.std200)
      )
)
SELECT w.* FROM {source} w
JOIN active_sig_days asd ON asd.ticker = w.ticker AND asd.d = w.d
ORDER BY w.ticker, w.d, w.close_min
"""


def ensure_sig_5m(con: duckdb.DuckDBPyConnection, have: set[str]) -> None:
    """Build each missing table; compact an existing one to its signalling symbol-days."""
    for table, first_open in SESSION_FIRST_OPEN.items():
        t0 = time.time()
        if table in have:
            con.execute(f"CREATE OR REPLACE TABLE {table}_filtered AS {_SIGNAL_DAYS_SQL.format(source=table)}")
            con.execute(f"DROP TABLE {table}; ALTER TABLE {table}_filtered RENAME TO {table};")
            verb = "compacted"
        else:
            window = f"{table}_win"
            con.execute(f"CREATE OR REPLACE TEMP VIEW {window} AS "
                        f"{_WINDOW_SQL.format(first_open=first_open, end=SESSION_END_MIN)}")
            con.execute(f"CREATE OR REPLACE TABLE {table} AS {_SIGNAL_DAYS_SQL.format(source=window)}")
            con.execute(f"DROP VIEW {window}")
            verb = "built"
        cnt = con.execute(f"SELECT count(*), count(DISTINCT (ticker, d)) FROM {table}").fetchone()
        print(f"   {verb} {table}: {cnt[0]:,} rows across {cnt[1]:,} active signaling symbol-days "
              f"({time.time() - t0:.1f}s)", flush=True)
