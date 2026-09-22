"""Pass 1: per symbol-day opening-range and RTH facts from the minute flat files.

For every trading day file that is not yet built, one DuckDB pass produces one row per
ticker in ``open5``: pre-market volume, the 09:30-09:35 candle (open / high / low / close /
volume / bar count) and the regular-session OHLCV. Nothing reads ahead of its own day.

``--reference`` pulls the ticker list (type, active, delisting) and the splits table from
the Massive REST API (``MASSIVE_API_KEY`` in the desk ``.env``) so selection can exclude
funds, warrants, units and any symbol with a split inside its lookback.

``--select`` builds the ``selection`` table: the published stocks-in-play filter and the
opening relative-volume rank, top ``--top`` per day (kept wide so the robustness pass can
try 10 / 20 / 30 without re-reading files).

Usage (from the repo root so .env is found):
    py -3 research/orb/build_store.py            # build missing days
    py -3 research/orb/build_store.py --reference
    py -3 research/orb/build_store.py --select --top 30
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime

import requests

from common import MINUTE_SOURCE_SQL, STORE_DIR, connect, load_env, minute_files

SCHEMA = """
CREATE TABLE IF NOT EXISTS open5 (
    ticker VARCHAR, d DATE,
    pm_volume BIGINT,
    o5_open DOUBLE, o5_high DOUBLE, o5_low DOUBLE, o5_close DOUBLE, o5_volume BIGINT, o5_bars INTEGER,
    rth_open DOUBLE, rth_high DOUBLE, rth_low DOUBLE, rth_close DOUBLE, rth_volume BIGINT, rth_bars INTEGER,
    PRIMARY KEY (ticker, d));
CREATE TABLE IF NOT EXISTS built_days (d DATE PRIMARY KEY, tickers INTEGER, seconds DOUBLE, built_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS tickers (ticker VARCHAR PRIMARY KEY, name VARCHAR, type VARCHAR, active BOOLEAN,
    primary_exchange VARCHAR, list_date DATE, delisted_utc VARCHAR);
CREATE TABLE IF NOT EXISTS splits (ticker VARCHAR, execution_date DATE, split_from DOUBLE, split_to DOUBLE);
"""

DAY_SQL = (
    "INSERT OR REPLACE INTO open5 "
    "WITH m AS (" + MINUTE_SOURCE_SQL + ") "
    "SELECT ticker, ?::DATE AS d, "
    "  coalesce(sum(volume) FILTER (WHERE t < TIME '09:30'), 0), "
    "  first(open ORDER BY t) FILTER (WHERE t >= TIME '09:30' AND t < TIME '09:35'), "
    "  max(high) FILTER (WHERE t >= TIME '09:30' AND t < TIME '09:35'), "
    "  min(low) FILTER (WHERE t >= TIME '09:30' AND t < TIME '09:35'), "
    "  last(close ORDER BY t) FILTER (WHERE t >= TIME '09:30' AND t < TIME '09:35'), "
    "  coalesce(sum(volume) FILTER (WHERE t >= TIME '09:30' AND t < TIME '09:35'), 0), "
    "  count(*) FILTER (WHERE t >= TIME '09:30' AND t < TIME '09:35'), "
    "  first(open ORDER BY t) FILTER (WHERE t >= TIME '09:30' AND t < TIME '16:00'), "
    "  max(high) FILTER (WHERE t >= TIME '09:30' AND t < TIME '16:00'), "
    "  min(low) FILTER (WHERE t >= TIME '09:30' AND t < TIME '16:00'), "
    "  last(close ORDER BY t) FILTER (WHERE t >= TIME '09:30' AND t < TIME '16:00'), "
    "  coalesce(sum(volume) FILTER (WHERE t >= TIME '09:30' AND t < TIME '16:00'), 0), "
    "  count(*) FILTER (WHERE t >= TIME '09:30' AND t < TIME '16:00') "
    "FROM m GROUP BY ticker"
)

# The published stocks-in-play filter (Zarattini, Barbon & Aziz 2024) with the opening
# relative-volume rank. Lookbacks are the prior 14 trading rows of that ticker, never today.
SELECT_SQL = """
CREATE OR REPLACE TABLE selection AS
WITH base AS (
    SELECT o.*,
           lag(rth_close) OVER w AS prev_close,
           avg(rth_volume) OVER w14 AS adv14,
           avg(o5_volume) OVER w14 AS avg_o5_14,
           count(*) OVER w14 AS n14
    FROM open5 o
    WINDOW w AS (PARTITION BY ticker ORDER BY d),
           w14 AS (PARTITION BY ticker ORDER BY d ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING)
), tr AS (
    SELECT *, greatest(rth_high - rth_low, abs(rth_high - prev_close), abs(rth_low - prev_close)) AS tr
    FROM base
), atr AS (
    SELECT *, avg(tr) OVER (PARTITION BY ticker ORDER BY d ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING) AS atr14
    FROM tr
), cand AS (
    SELECT ticker, d, prev_close, pm_volume,
           o5_open, o5_high, o5_low, o5_close, o5_volume, o5_bars,
           rth_open, rth_high, rth_low, rth_close, rth_volume,
           adv14, atr14, avg_o5_14, n14,
           o5_volume / nullif(avg_o5_14, 0) AS rvol,
           CASE WHEN o5_close > o5_open THEN 'long' WHEN o5_close < o5_open THEN 'short' ELSE 'doji' END AS direction
    FROM atr a
    WHERE n14 >= 14 AND o5_bars >= 1 AND o5_volume > 0
      AND o5_open > ? AND adv14 >= ? AND atr14 > ?
      -- keep common stock, ADRs and unknown-type names (many delisted rows carry no type;
      -- dropping them would reintroduce survivorship bias); drop every known fund / derivative
      AND ticker NOT IN (SELECT ticker FROM tickers WHERE type IS NOT NULL AND type NOT IN ('CS', 'ADRC'))
      AND NOT EXISTS (SELECT 1 FROM splits s
                      WHERE s.ticker = a.ticker AND s.execution_date BETWEEN a.d - INTERVAL 30 DAY AND a.d)
), ranked AS (
    SELECT *, row_number() OVER (PARTITION BY d ORDER BY rvol DESC, ticker) AS rank
    FROM cand WHERE rvol >= ?
)
SELECT * FROM ranked WHERE rank <= ?
"""

API_BASES = ("https://api.massive.com", "https://api.polygon.io")


def build_days(con, limit: int | None = None) -> int:
    files = minute_files()
    done = {r[0] for r in con.execute("SELECT d FROM built_days").fetchall()}
    todo = [d for d in files if d not in done]
    if limit:
        todo = todo[:limit]
    print(f"open5: {len(done)} days built, {len(todo)} to build", flush=True)
    for i, d in enumerate(todo, 1):
        t0 = time.time()
        con.execute("BEGIN")
        con.execute("DELETE FROM open5 WHERE d = ?", [d])
        con.execute(DAY_SQL, [str(files[d]), d])
        n = con.execute("SELECT count(*) FROM open5 WHERE d = ?", [d]).fetchone()[0]
        con.execute("INSERT OR REPLACE INTO built_days VALUES (?, ?, ?, ?)", [d, n, time.time() - t0, datetime.now()])
        con.execute("COMMIT")
        if i % 25 == 0 or i == len(todo):
            print(f"  {d} tickers={n} {time.time() - t0:.1f}s  ({i}/{len(todo)})", flush=True)
    return len(todo)


def _api_key() -> str:
    # Massive issues one value per key: the REST API key is also the flat-file S3 secret.
    key = (os.environ.get("MASSIVE_API_KEY") or os.environ.get("POLYGON_API_KEY")
           or os.environ.get("MASSIVE_S3_SECRET_ACCESS_KEY") or "").strip()
    if not key:
        sys.exit("Missing MASSIVE_API_KEY (or MASSIVE_S3_SECRET_ACCESS_KEY) in .env -- Dashboard > Keys.")
    return key


def _paged(path: str, params: dict) -> list[dict]:
    key = _api_key()
    rows: list[dict] = []
    for base in API_BASES:
        url = f"{base}{path}"
        try:
            while url:
                r = requests.get(url, params={**params, "apiKey": key} if "apiKey" not in url else {"apiKey": key},
                                 timeout=60)
                r.raise_for_status()
                body = r.json()
                rows.extend(body.get("results") or [])
                url = body.get("next_url")
                params = {}
            return rows
        except requests.RequestException as exc:
            print(f"{base}: {exc}; trying next host", file=sys.stderr)
            rows.clear()
    sys.exit("reference download failed on every host")


REF_DIR = STORE_DIR / "reference"


def fetch_reference() -> None:
    """Pull tickers (active + delisted) and splits via REST into JSON files; no store lock needed."""
    REF_DIR.mkdir(parents=True, exist_ok=True)
    tickers: list[dict] = []
    for active in ("true", "false"):
        tickers += _paged("/v3/reference/tickers", {"market": "stocks", "active": active, "limit": 1000})
    splits = _paged("/v3/reference/splits", {"execution_date.gte": "2021-06-01", "limit": 1000})
    (REF_DIR / "tickers.json").write_text(json.dumps(tickers), encoding="utf-8")
    (REF_DIR / "splits.json").write_text(json.dumps(splits), encoding="utf-8")
    kinds = {}
    for t in tickers:
        kinds[t.get("type")] = kinds.get(t.get("type"), 0) + 1
    print(f"reference fetched: {len(tickers)} tickers, {len(splits)} splits since 2021-06; "
          f"types {dict(sorted(kinds.items(), key=lambda kv: -kv[1])[:8])}", flush=True)


def load_reference(con) -> bool:
    """Load the fetched JSON into the store; returns False when nothing has been fetched yet."""
    tp, sp = REF_DIR / "tickers.json", REF_DIR / "splits.json"
    if not (tp.exists() and sp.exists()):
        return False
    tickers = json.loads(tp.read_text(encoding="utf-8"))
    splits = json.loads(sp.read_text(encoding="utf-8"))
    con.execute("DELETE FROM tickers")
    con.executemany(
        "INSERT OR REPLACE INTO tickers VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(t.get("ticker"), t.get("name"), t.get("type"), t.get("active"), t.get("primary_exchange"),
          t.get("list_date"), t.get("delisted_utc")) for t in tickers if t.get("ticker")],
    )
    con.execute("DELETE FROM splits")
    con.executemany(
        "INSERT INTO splits VALUES (?, ?, ?, ?)",
        [(s.get("ticker"), s.get("execution_date"), s.get("split_from"), s.get("split_to"))
         for s in splits if s.get("ticker") and s.get("execution_date")],
    )
    n_t = con.execute("SELECT count(*), count(*) FILTER (WHERE type IN ('CS','ADRC')) FROM tickers").fetchone()
    n_s = con.execute("SELECT count(*) FROM splits").fetchone()[0]
    print(f"reference loaded: {n_t[0]} tickers ({n_t[1]} common/ADR), {n_s} splits", flush=True)
    return True


def build_selection(con, top: int, min_price: float, min_adv: float, min_atr: float, min_rvol: float) -> None:
    t0 = time.time()
    con.execute(SELECT_SQL, [min_price, min_adv, min_atr, min_rvol, top])
    row = con.execute(
        "SELECT count(*), count(DISTINCT d), min(d), max(d), "
        "count(*) FILTER (WHERE direction='long'), count(*) FILTER (WHERE direction='short') FROM selection"
    ).fetchone()
    print(f"selection: {row[0]} symbol-days over {row[1]} days {row[2]}..{row[3]} "
          f"(long {row[4]}, short {row[5]}) in {time.time() - t0:.1f}s", flush=True)


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="build at most N new days (smoke test)")
    ap.add_argument("--fetch-reference", action="store_true", help="pull tickers + splits via REST to JSON (no store lock)")
    ap.add_argument("--reference", action="store_true", help="load the fetched reference JSON into the store")
    ap.add_argument("--select", action="store_true", help="(re)build the selection table")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--min-price", type=float, default=5.0)
    ap.add_argument("--min-adv", type=float, default=1_000_000)
    ap.add_argument("--min-atr", type=float, default=0.5)
    ap.add_argument("--min-rvol", type=float, default=1.0)
    ap.add_argument("--no-build", action="store_true", help="skip the day pass")
    args = ap.parse_args()

    if args.fetch_reference:
        fetch_reference()
        if not (args.reference or args.select or not args.no_build):
            return 0
    con = connect()
    con.execute(SCHEMA)
    if not args.no_build:
        build_days(con, args.limit)
    if args.reference or args.select:
        if not load_reference(con):
            print("reference: none fetched yet -- selection will not exclude funds or split days", flush=True)
    if args.select:
        build_selection(con, args.top, args.min_price, args.min_adv, args.min_atr, args.min_rvol)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
