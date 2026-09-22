"""Daily bars for every US stock from the day_aggs_v1 flat files, plus the indicators the
large-cap mean-reversion candidate (A4) reads, each computed from prior rows only.

``daily``: ticker, d, open, high, low, close, volume, transactions.
``daily_ind``: prev_close, prev_high, sma200 (200 prior closes incl. today's close is the
standard definition -- today's close is known at the close when the order goes), adv20_usd
(20-day average dollar volume, prior days), rsi2 (Wilder, 2 periods, through today's close),
n_hist (rows of history available).

Usage:
    py -3 research/orb/build_daily.py
"""
from __future__ import annotations

import re
import time
from datetime import date
from pathlib import Path

from common import DATA_ROOT, connect, load_env

DAY_DIR = DATA_ROOT / "day_aggs_v1"
_DAY_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\.csv\.gz$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily (
    ticker VARCHAR, d DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT, transactions BIGINT,
    PRIMARY KEY (ticker, d));
CREATE TABLE IF NOT EXISTS daily_days (d DATE PRIMARY KEY, tickers INTEGER, built_at TIMESTAMP);
"""

DAY_SQL = """
INSERT OR REPLACE INTO daily
SELECT ticker, ?::DATE, open, high, low, close, volume, transactions
FROM read_csv(?, header = true,
              columns = {'ticker': 'VARCHAR', 'volume': 'BIGINT', 'open': 'DOUBLE', 'close': 'DOUBLE',
                         'high': 'DOUBLE', 'low': 'DOUBLE', 'window_start': 'BIGINT', 'transactions': 'BIGINT'})
"""

# Split adjustment: the flat files are unadjusted. Every bar before a split is scaled by the
# product of (split_from / split_to) over the ticker's later splits, so a 4-for-1 divides
# earlier prices by 4 and multiplies earlier volume by 4. Economically neutral, so indicators
# and P&L computed on adjusted bars are the honest ones; no split exclusion is needed.
ADJ_SQL = """
CREATE OR REPLACE TABLE daily_adj AS
WITH f AS (
    SELECT d2.ticker, d2.d, product(s.split_from / s.split_to) AS factor
    FROM daily d2
    JOIN splits s ON s.ticker = d2.ticker AND s.execution_date > d2.d
    WHERE s.split_from > 0 AND s.split_to > 0
    GROUP BY 1, 2
)
SELECT d.ticker, d.d,
       d.open * coalesce(f.factor, 1.0) AS open, d.high * coalesce(f.factor, 1.0) AS high,
       d.low * coalesce(f.factor, 1.0) AS low, d.close * coalesce(f.factor, 1.0) AS close,
       (d.volume / coalesce(f.factor, 1.0))::BIGINT AS volume, d.transactions,
       coalesce(f.factor, 1.0) AS factor
FROM daily d LEFT JOIN f USING (ticker, d)
"""

# Wilder RSI(2) needs a recursive smoothing; DuckDB has no EWM, so it is computed in pandas
# per ticker below. Everything else is window SQL.
IND_SQL = """
CREATE OR REPLACE TABLE daily_ind AS
SELECT ticker, d, close, high, low, factor,
       lag(close) OVER w AS prev_close,
       lag(high) OVER w AS prev_high,
       avg(close) OVER (PARTITION BY ticker ORDER BY d ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS sma200,
       avg(close) OVER (PARTITION BY ticker ORDER BY d ROWS BETWEEN 99 PRECEDING AND CURRENT ROW) AS sma100,
       avg(close * volume) OVER (PARTITION BY ticker ORDER BY d ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS adv20_usd,
       count(*) OVER (PARTITION BY ticker ORDER BY d ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS n_hist
FROM daily_adj
WINDOW w AS (PARTITION BY ticker ORDER BY d)
"""


def day_files() -> dict[date, Path]:
    out: dict[date, Path] = {}
    for p in DAY_DIR.glob("*/*/*.csv.gz"):
        m = _DAY_RE.search(p.name)
        if m:
            out[date.fromisoformat(m.group(1))] = p
    return dict(sorted(out.items()))


def build_rsi(con) -> None:
    import numpy as np
    import pandas as pd

    df = con.execute("SELECT ticker, d, close FROM daily_adj ORDER BY ticker, d").df()
    delta = df.groupby("ticker", sort=False)["close"].diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    # Wilder smoothing with period 2 is an EWM with alpha = 1/2 (adjust=False), per ticker
    ag = gain.groupby(df["ticker"], sort=False).transform(lambda s: s.ewm(alpha=0.5, adjust=False).mean())
    al = loss.groupby(df["ticker"], sort=False).transform(lambda s: s.ewm(alpha=0.5, adjust=False).mean())
    with np.errstate(divide="ignore", invalid="ignore"):
        rsi = np.where(al == 0, 100.0, 100.0 - 100.0 / (1.0 + ag / al))
    rsi_df = pd.DataFrame({"ticker": df["ticker"], "d": df["d"], "rsi2": rsi})[delta.notna().to_numpy()]
    con.execute("CREATE OR REPLACE TABLE daily_rsi AS SELECT * FROM rsi_df")


def main() -> int:
    load_env()
    con = connect()
    con.execute(SCHEMA)
    files = day_files()
    done = {r[0] for r in con.execute("SELECT d FROM daily_days").fetchall()}
    todo = [d for d in files if d not in done]
    print(f"daily: {len(done)} days built, {len(todo)} to build", flush=True)
    t0 = time.time()
    for i, d in enumerate(todo, 1):
        con.execute("BEGIN")
        con.execute("DELETE FROM daily WHERE d = ?", [d])
        con.execute(DAY_SQL, [d, str(files[d])])
        n = con.execute("SELECT count(*) FROM daily WHERE d = ?", [d]).fetchone()[0]
        con.execute("INSERT OR REPLACE INTO daily_days VALUES (?, ?, now())", [d, n])
        con.execute("COMMIT")
        if i % 200 == 0 or i == len(todo):
            print(f"  {d} tickers={n}  ({i}/{len(todo)}, {time.time() - t0:.0f}s)", flush=True)
    t1 = time.time()
    con.execute(ADJ_SQL)
    n_adj = con.execute("SELECT count(*) FROM daily_adj WHERE factor <> 1.0").fetchone()[0]
    print(f"daily_adj built in {time.time() - t1:.0f}s ({n_adj} rows scaled by a later split)", flush=True)
    t1 = time.time()
    con.execute(IND_SQL)
    print(f"daily_ind built in {time.time() - t1:.0f}s", flush=True)
    t2 = time.time()
    build_rsi(con)
    print(f"daily_rsi built in {time.time() - t2:.0f}s", flush=True)
    n = con.execute("SELECT count(*), count(DISTINCT ticker), min(d), max(d) FROM daily").fetchone()
    print(f"daily: {n[0]} rows, {n[1]} tickers, {n[2]}..{n[3]}", flush=True)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
