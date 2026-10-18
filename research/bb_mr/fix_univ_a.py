"""Update `meta_univ_a` in `bb_mr.duckdb` to strictly causal pre-session membership."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.bb_mr.config import BB_DB_PATH, ORB_DB_PATH, RESULTS_DIR


def update_univ_a() -> None:
    con = duckdb.connect(str(BB_DB_PATH))
    con.execute("SET threads TO 8")
    con.execute(f"ATTACH '{ORB_DB_PATH.as_posix()}' AS orb (READ_ONLY)")
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
    ua_stats = con.execute("""
        SELECT count(*), count(DISTINCT d), count(DISTINCT ticker),
               count(DISTINCT ticker) FILTER (WHERE NOT is_active_2026),
               min(d), max(d)
        FROM meta_univ_a
    """).fetchone()
    con.close()

    manifest_path = RESULTS_DIR / "data_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["universe_a_liquid_reference"].update({
            "symbol_days": int(ua_stats[0]),
            "trading_days": int(ua_stats[1]),
            "distinct_tickers": int(ua_stats[2]),
            "delisted_tickers_included": int(ua_stats[3]),
            "first_date": str(ua_stats[4]),
            "last_date": str(ua_stats[5]),
            "rules": "Strictly causal US CS/ADRC common stocks ($5<=prev_close<=200, 20-day ADV >= $20M, top 30 by ADV20 per day, pre-session membership only; excludes ex-post intraday mover rows)",
        })
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Updated meta_univ_a:", ua_stats)


if __name__ == "__main__":
    update_univ_a()
