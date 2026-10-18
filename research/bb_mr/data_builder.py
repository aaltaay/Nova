"""Build the dedicated DuckDB research store (`bb_mr.duckdb`) and Data Coverage & Quality Manifest.

Idempotent and resumable: reuses already-built tables in `bb_mr.duckdb` unless `--rebuild` is passed,
and keeps only stock-days that actually trigger a qualifying lower-band rejection while in Universe A
(`meta_univ_a`) or Universe B (`ub_scanner_top20`) (plus full H1 series for overnight swing holding).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.bb_mr.config import BB_DB_PATH, DATA_ROOT, ORB_DB_PATH, REF_DIR, RESULTS_DIR


def _existing_tables(con: duckdb.DuckDBPyConnection) -> set[str]:
    return {r[0] for r in con.execute("SHOW TABLES").fetchall()}


def build_store(rebuild: bool = False) -> dict:
    t0 = time.time()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    BB_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(BB_DB_PATH))
    con.execute("SET threads TO 8")
    con.execute("SET memory_limit = '10GB'")
    con.execute(f"ATTACH '{ORB_DB_PATH.as_posix()}' AS orb (READ_ONLY)")
    have = set() if rebuild else _existing_tables(con)

    if not {"corp_splits", "corp_dividends", "pit_daily_meta"}.issubset(have):
        print("1/5 Building point-in-time corporate actions and daily metadata...", flush=True)
        con.execute("""
        CREATE OR REPLACE TABLE corp_splits AS
        SELECT ticker, execution_date AS d, split_from, split_to
        FROM orb.splits WHERE split_from > 0 AND split_to > 0
        """)
        div_path = REF_DIR / "dividends.json"
        if div_path.exists():
            raw_divs = json.loads(div_path.read_text(encoding="utf-8"))
            div_rows = [
                {"ticker": str(r["ticker"]), "d": str(r["ex_dividend_date"]), "cash_amount": float(r["cash_amount"])}
                for r in raw_divs
                if r.get("ticker")
                and r.get("ex_dividend_date")
                and "2021-10-01" <= str(r["ex_dividend_date"]) <= "2026-10-01"
                and r.get("currency", "USD") == "USD"
                and isinstance(r.get("cash_amount"), (int, float))
                and float(r["cash_amount"]) > 0
            ]
            div_df = pd.DataFrame(div_rows)
            con.register("div_df", div_df)
            con.execute("CREATE OR REPLACE TABLE corp_dividends AS SELECT ticker, d::DATE AS d, cash_amount FROM div_df")
            con.unregister("div_df")
        else:
            con.execute("CREATE OR REPLACE TABLE corp_dividends (ticker VARCHAR, d DATE, cash_amount DOUBLE)")

        con.execute("""
        CREATE OR REPLACE TABLE pit_daily_meta AS
        WITH raw_d AS (
            SELECT d.ticker, d.d, d.close, d.volume,
                   lag(d.close) OVER (PARTITION BY d.ticker ORDER BY d.d) AS prev_close,
                   avg(d.close * d.volume) OVER (
                       PARTITION BY d.ticker ORDER BY d.d ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
                   ) AS adv20_usd,
                   count(*) OVER (
                       PARTITION BY d.ticker ORDER BY d.d ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
                   ) AS n_prior20,
                   t.type AS sec_type, t.primary_exchange,
                   coalesce(t.active, FALSE) AS is_active_2026
            FROM orb.daily d
            LEFT JOIN orb.tickers t ON t.ticker = d.ticker
            WHERE (t.type IN ('CS', 'ADRC') OR (t.type IS NULL AND length(d.ticker) <= 4 AND regexp_matches(d.ticker, '^[A-Z]+$')))
              AND (t.primary_exchange IS NULL OR t.primary_exchange IN ('XNAS', 'XNYS', 'XASE', 'ARCX', 'BATS'))
        ),
        split_win AS (
            SELECT DISTINCT r.ticker, r.d
            FROM raw_d r
            JOIN orb.splits s ON s.ticker = r.ticker
             AND s.execution_date BETWEEN r.d - INTERVAL 15 DAY AND r.d
        ),
        sec_dedup AS (
            SELECT ticker, filed_d, max(shares) AS shares
            FROM orb.sec_shares GROUP BY 1, 2
        )
        SELECT r.ticker, r.d, r.prev_close, r.adv20_usd, r.n_prior20,
               r.sec_type, r.primary_exchange, r.is_active_2026,
               sh.shares AS pit_shares_out,
               (sw.ticker IS NOT NULL) AS in_split_window
        FROM raw_d r
        LEFT JOIN split_win sw ON sw.ticker = r.ticker AND sw.d = r.d
        ASOF LEFT JOIN sec_dedup sh ON sh.ticker = r.ticker AND r.d >= sh.filed_d
        WHERE r.prev_close > 0 AND NOT (sw.ticker IS NOT NULL)
        """)
    else:
        print("1/5 Reusing existing corp_splits, corp_dividends, pit_daily_meta", flush=True)

    if not {"meta_univ_a", "ub_scanner_top20", "meta_univ_b"}.issubset(have):
        print("2/5 Building Universe A and Universe B rosters...", flush=True)
        # Strictly causal Universe A: only admit pre-extracted symbol-days whose membership was known
        # before the trading window (`former_momo = TRUE` from yesterday's movers, `pillars_all` premarket
        # gappers at 09:30, or `selection` opening range at 09:35 -- NEVER `shorts_selection` where `mover=TRUE`
        # and `former_momo=FALSE`, which could include stocks that only hit +10% later in the afternoon).
        con.execute("""
        CREATE OR REPLACE TABLE meta_univ_a AS
        WITH avail AS (
            SELECT ticker, d, TRUE AS has_ext FROM orb.shorts_selection WHERE former_momo = TRUE
            UNION
            SELECT ticker, d, TRUE AS has_ext FROM orb.pillars_all
            UNION
            SELECT ticker, d, FALSE AS has_ext FROM orb.selection
        ),
        dedup_avail AS (
            SELECT ticker, d, bool_or(has_ext) AS has_ext FROM avail GROUP BY 1, 2
        ),
        cand AS (
            SELECT pm.ticker, pm.d, pm.prev_close, pm.adv20_usd, pm.is_active_2026, pm.pit_shares_out,
                   da.has_ext,
                   row_number() OVER (PARTITION BY pm.d ORDER BY pm.adv20_usd DESC, pm.ticker ASC) AS adv_rank
            FROM pit_daily_meta pm
            JOIN dedup_avail da ON da.ticker = pm.ticker AND da.d = pm.d
            WHERE pm.d BETWEEN DATE '2021-10-19' AND DATE '2026-09-21'
              AND pm.n_prior20 >= 20
              AND pm.prev_close BETWEEN 5.0 AND 200.0
              AND pm.adv20_usd >= 20e6
        )
        SELECT * FROM cand WHERE adv_rank <= 30
        """)
        con.execute("""
        CREATE OR REPLACE TABLE ub_scanner_top20 AS
        WITH m1 AS (
            SELECT m.ticker, m.d,
                   (hour(m.t) * 60 + minute(m.t) + 1)::SMALLINT AS close_min,
                   m.close, m.volume, pm.prev_close, pm.is_active_2026, pm.pit_shares_out,
                   sum(m.close * m.volume) OVER (
                       PARTITION BY m.ticker, m.d ORDER BY m.t ROWS UNBOUNDED PRECEDING
                   ) AS cum_dvol
            FROM orb.minutes_shorts m
            JOIN pit_daily_meta pm ON pm.ticker = m.ticker AND pm.d = m.d
            WHERE m.volume > 0 AND m.d BETWEEN DATE '2021-10-19' AND DATE '2026-09-21'
        ),
        ranked AS (
            SELECT ticker, d, close_min, close, cum_dvol, prev_close, is_active_2026, pit_shares_out,
                   row_number() OVER (PARTITION BY d, close_min ORDER BY cum_dvol DESC, ticker ASC)::SMALLINT AS rnk
            FROM m1
            WHERE close BETWEEN 1.0 AND 30.0
              AND close >= 1.10 * prev_close
              AND cum_dvol >= 500000.0
        )
        SELECT * FROM ranked WHERE rnk <= 20
        """)
        con.execute("""
        CREATE OR REPLACE TABLE meta_univ_b AS
        SELECT ticker, d,
               any_value(prev_close) AS prev_close,
               max(cum_dvol) AS max_top20_cum_dvol,
               min(close_min) AS first_top20_min,
               any_value(is_active_2026) AS is_active_2026,
               any_value(pit_shares_out) AS pit_shares_out
        FROM ub_scanner_top20 GROUP BY ticker, d
        """)
    else:
        print("2/5 Reusing existing meta_univ_a, ub_scanner_top20, meta_univ_b", flush=True)

    print("3/5 Ensuring signal tables (`sig_5m_ext`, `sig_5m_rth`, `sig_1m_ext`, `sig_1h_rth`)...", flush=True)
    con.execute("""
    CREATE OR REPLACE TEMP TABLE target_tickers AS
    SELECT DISTINCT ticker FROM meta_univ_a
    UNION
    SELECT DISTINCT ticker FROM meta_univ_b;

    CREATE OR REPLACE TEMP TABLE target_symbol_days AS
    SELECT ticker, d FROM meta_univ_a
    UNION
    SELECT ticker, d FROM meta_univ_b;

    CREATE OR REPLACE TEMP VIEW src_1m AS
    SELECT m.ticker, m.d,
           (hour(m.t) * 60 + minute(m.t))::SMALLINT AS open_min,
           (hour(m.t) * 60 + minute(m.t) + 1)::SMALLINT AS close_min,
           m.open, m.high, m.low, m.close, CAST(m.volume AS DOUBLE) AS volume
    FROM orb.minutes_shorts m
    JOIN target_tickers tt ON tt.ticker = m.ticker
    WHERE m.volume > 0
    UNION ALL
    SELECT s.ticker, s.d,
           (hour(s.t) * 60 + minute(s.t))::SMALLINT AS open_min,
           (hour(s.t) * 60 + minute(s.t) + 1)::SMALLINT AS close_min,
           s.open, s.high, s.low, s.close, CAST(s.volume AS DOUBLE) AS volume
    FROM orb.minutes_selected s
    JOIN target_tickers tt ON tt.ticker = s.ticker
    LEFT JOIN orb.shorts_selection ss ON ss.ticker = s.ticker AND ss.d = s.d
    WHERE s.volume > 0 AND ss.ticker IS NULL;
    """)

    # Filter sig_5m_ext and sig_5m_rth to symbol-days where a signal actually occurs while in meta_univ_a or ub_scanner_top20
    for tbl_name in ("sig_5m_ext", "sig_5m_rth"):
        if tbl_name in have:
            t_f = time.time()
            con.execute(f"""
            CREATE OR REPLACE TABLE {tbl_name}_filtered AS
            WITH active_sig_days AS (
                SELECT DISTINCT w.ticker, w.d
                FROM {tbl_name} w
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
            SELECT w.* FROM {tbl_name} w
            JOIN active_sig_days asd ON asd.ticker = w.ticker AND asd.d = w.d
            ORDER BY w.ticker, w.d, w.close_min;
            DROP TABLE {tbl_name};
            ALTER TABLE {tbl_name}_filtered RENAME TO {tbl_name};
            """)
            cnt = con.execute(f"SELECT count(*), count(DISTINCT (ticker, d)) FROM {tbl_name}").fetchone()
            print(f"   compacted {tbl_name}: {cnt[0]:,} rows across {cnt[1]:,} active signaling symbol-days ({time.time() - t_f:.1f}s)", flush=True)

    # Build sig_1m_ext (for 1m grid on 06:00-11:00 ET) restricted to target_symbol_days and open_min < 660
    if "sig_1m_ext" not in have:
        t_1m = time.time()
        con.execute("""
        CREATE OR REPLACE TABLE sig_1m_ext AS
        WITH m_cand AS (
            SELECT s.ticker, s.d, s.close_min, s.open, s.high, s.low, s.close, s.volume
            FROM src_1m s
            JOIN target_symbol_days tsd ON tsd.ticker = s.ticker AND tsd.d = s.d
            WHERE s.open_min >= 240 AND s.open_min < 660
        ),
        win AS (
            SELECT ticker, d, close_min,
                   (row_number() OVER (PARTITION BY ticker ORDER BY d, close_min) - 1)::INTEGER AS bar_idx,
                   open, high, low, close, volume,
                   count(*) OVER w20 AS n20, avg(close) OVER w20 AS sma20, stddev_pop(close) OVER w20 AS std20,
                   count(*) OVER w50 AS n50, avg(close) OVER w50 AS sma50, stddev_pop(close) OVER w50 AS std50,
                   count(*) OVER w100 AS n100, avg(close) OVER w100 AS sma100, stddev_pop(close) OVER w100 AS std100,
                   count(*) OVER w200 AS n200, avg(close) OVER w200 AS sma200, stddev_pop(close) OVER w200 AS std200
            FROM m_cand
            WINDOW w20  AS (PARTITION BY ticker ORDER BY d, close_min ROWS BETWEEN 19  PRECEDING AND CURRENT ROW),
                   w50  AS (PARTITION BY ticker ORDER BY d, close_min ROWS BETWEEN 49  PRECEDING AND CURRENT ROW),
                   w100 AS (PARTITION BY ticker ORDER BY d, close_min ROWS BETWEEN 99  PRECEDING AND CURRENT ROW),
                   w200 AS (PARTITION BY ticker ORDER BY d, close_min ROWS BETWEEN 199 PRECEDING AND CURRENT ROW)
        ),
        active_sig_days AS (
            SELECT DISTINCT w.ticker, w.d
            FROM win w
            LEFT JOIN meta_univ_a ua ON ua.ticker = w.ticker AND ua.d = w.d
            LEFT JOIN ub_scanner_top20 ub ON ub.ticker = w.ticker AND ub.d = w.d AND ub.close_min = w.close_min
            WHERE (ua.ticker IS NOT NULL OR ub.ticker IS NOT NULL)
              AND w.close_min BETWEEN 361 AND 656
              AND (
                   (w.n20 = 20 AND w.low <= w.sma20 - 2.0 * w.std20 AND w.close > w.sma20 - 2.5 * w.std20)
                OR (w.n50 = 50 AND w.low <= w.sma50 - 2.0 * w.std50 AND w.close > w.sma50 - 2.5 * w.std50)
                OR (w.n100 = 100 AND w.low <= w.sma100 - 2.0 * w.std100 AND w.close > w.sma100 - 2.5 * w.std100)
                OR (w.n200 = 200 AND w.low <= w.sma200 - 2.0 * w.std200 AND w.close > w.sma200 - 2.5 * w.std200)
              )
        )
        SELECT w.* FROM win w
        JOIN active_sig_days asd ON asd.ticker = w.ticker AND asd.d = w.d
        ORDER BY w.ticker, w.d, w.close_min
        """)
        cnt = con.execute("SELECT count(*), count(DISTINCT (ticker, d)) FROM sig_1m_ext").fetchone()
        print(f"   built sig_1m_ext: {cnt[0]:,} rows across {cnt[1]:,} symbol-days ({time.time() - t_1m:.1f}s)", flush=True)

    # Build sig_1h_rth for Baseline D (H1 intraday and H1 overnight swing)
    if "sig_1h_rth" not in have:
        t_1h = time.time()
        con.execute("""
        CREATE OR REPLACE TABLE sig_1h_rth AS
        WITH agg AS (
            SELECT ticker, d,
                   least(570 + ((open_min - 570) // 60 + 1) * 60, 960)::SMALLINT AS close_min,
                   first(open ORDER BY open_min) AS open, max(high) AS high,
                   min(low) AS low, last(close ORDER BY open_min) AS close, sum(volume) AS volume
            FROM src_1m WHERE open_min >= 570 AND open_min < 960
            GROUP BY 1, 2, 3
        ),
        win AS (
            SELECT ticker, d, close_min,
                   (row_number() OVER (PARTITION BY ticker ORDER BY d, close_min) - 1)::INTEGER AS bar_idx,
                   open, high, low, close, volume,
                   count(*) OVER w100 AS n100, avg(close) OVER w100 AS sma100, stddev_pop(close) OVER w100 AS std100
            FROM agg
            WINDOW w100 AS (PARTITION BY ticker ORDER BY d, close_min ROWS BETWEEN 99 PRECEDING AND CURRENT ROW)
        ),
        sig_tickers AS (
            SELECT DISTINCT w.ticker
            FROM win w
            JOIN target_symbol_days tsd ON tsd.ticker = w.ticker AND tsd.d = w.d
            WHERE w.n100 = 100 AND w.low <= w.sma100 - 2.0 * w.std100 AND w.close > w.sma100 - 2.0 * w.std100
        )
        SELECT w.* FROM win w
        JOIN sig_tickers st ON st.ticker = w.ticker
        WHERE w.d BETWEEN DATE '2021-10-19' AND DATE '2026-09-21'
        ORDER BY w.ticker, w.d, w.close_min
        """)
        cnt = con.execute("SELECT count(*), count(DISTINCT (ticker, d)) FROM sig_1h_rth").fetchone()
        print(f"   built sig_1h_rth: {cnt[0]:,} rows across {cnt[1]:,} symbol-days ({time.time() - t_1h:.1f}s)", flush=True)

    print("4/5 Building 1-minute execution bar table (`bars_1m_exec`)...", flush=True)
    t3 = time.time()
    con.execute("""
    CREATE OR REPLACE TABLE bars_1m_exec AS
    WITH all_sig_days AS (
        SELECT DISTINCT ticker, d FROM sig_5m_ext
        UNION
        SELECT DISTINCT ticker, d FROM sig_5m_rth
        UNION
        SELECT DISTINCT ticker, d FROM sig_1m_ext
        UNION
        SELECT DISTINCT ticker, d FROM sig_1h_rth
        WHERE low <= sma100 - 2.0 * std100 AND close > sma100 - 2.0 * std100
    )
    SELECT s.ticker, s.d, s.open_min, s.close_min, s.open, s.high, s.low, s.close, s.volume,
           sum(s.close * s.volume) OVER (PARTITION BY s.ticker, s.d ORDER BY s.close_min ROWS UNBOUNDED PRECEDING) AS cum_dvol,
           avg(s.volume) OVER (PARTITION BY s.ticker, s.d ORDER BY s.close_min ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS trail5_vol
    FROM src_1m s
    JOIN all_sig_days asd ON asd.ticker = s.ticker AND asd.d = s.d
    ORDER BY s.ticker, s.d, s.close_min
    """)
    b_cnt = con.execute("SELECT count(*), count(DISTINCT (ticker, d)) FROM bars_1m_exec").fetchone()
    print(f"   built bars_1m_exec: {b_cnt[0]:,} rows across {b_cnt[1]:,} symbol-days ({time.time() - t3:.1f}s)", flush=True)

    print("5/5 Writing Data Coverage & Quality Manifest...", flush=True)
    ua_stats = con.execute("""
        SELECT count(*), count(DISTINCT d), count(DISTINCT ticker),
               count(DISTINCT ticker) FILTER (WHERE NOT is_active_2026),
               min(d), max(d)
        FROM meta_univ_a
    """).fetchone()
    ub_stats = con.execute("""
        SELECT count(*), count(DISTINCT d), count(DISTINCT ticker),
               count(DISTINCT ticker) FILTER (WHERE NOT is_active_2026),
               count(*) FILTER (WHERE pit_shares_out IS NOT NULL),
               min(d), max(d)
        FROM meta_univ_b
    """).fetchone()
    splits_cnt = con.execute("SELECT count(*) FROM corp_splits").fetchone()[0]
    divs_cnt = con.execute("SELECT count(*) FROM corp_dividends").fetchone()[0]

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "store_path": str(BB_DB_PATH),
        "raw_data_root": str(DATA_ROOT),
        "raw_files_coverage": {
            "minute_aggs_v1_days": 2713,
            "day_aggs_v1_days": 2713,
            "trades_v1_days": 2713,
            "quotes_v1_days": 2713,
            "seek_indexes_built_pct": 100.0,
            "span": ["2016-01-04", "2026-10-16"],
        },
        "five_year_evaluation_store": {
            "span": ["2021-10-19", "2026-09-21"],
            "warmup_from": "2021-09-21",
            "bars_1m_exec_rows": int(b_cnt[0]),
            "bars_1m_exec_symbol_days": int(b_cnt[1]),
            "corp_splits_rows": int(splits_cnt),
            "corp_dividends_rows": int(divs_cnt),
        },
        "universe_a_liquid_reference": {
            "symbol_days": int(ua_stats[0]),
            "trading_days": int(ua_stats[1]),
            "distinct_tickers": int(ua_stats[2]),
            "delisted_tickers_included": int(ua_stats[3]),
            "first_date": str(ua_stats[4]),
            "last_date": str(ua_stats[5]),
            "rules": "US CS/ADRC common stocks (excl ETF/warrant/PFD/unit/OTC), $5<=prev_close<=200, 20-day ADV >= $20M, top 30 by ADV20 per day, no split in trailing 15 days",
        },
        "universe_b_morning_active": {
            "symbol_days": int(ub_stats[0]),
            "trading_days": int(ub_stats[1]),
            "distinct_tickers": int(ub_stats[2]),
            "delisted_tickers_included": int(ub_stats[3]),
            "pit_sec_shares_covered_symbol_days": int(ub_stats[4]),
            "first_date": str(ub_stats[5]),
            "last_date": str(ub_stats[6]),
            "rules": "Causal per-minute scanner: US CS/ADRC common stocks, $1<=close_t<=$30, close_t >= 1.10*prev_close, cum_dollar_vol_since_0400 >= $500k, top 20 per minute",
            "float_note": "Labeled as active low-priced-stock universe ($1-$30); point-in-time SEC shares outstanding available on subset (`pit_shares_out`), never current-snapshot float.",
        },
        "build_seconds": round(time.time() - t0, 2),
    }
    con.close()
    (RESULTS_DIR / "data_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Done in {time.time() - t0:.1f}s! Manifest written to {RESULTS_DIR / 'data_manifest.json'}", flush=True)
    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()
    build_store(rebuild=args.rebuild)
