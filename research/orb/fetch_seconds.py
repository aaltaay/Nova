"""One-second bars for the selected long symbol-days, 09:30-11:00 ET, via the REST API.

Why: the ORB stop is 5-10% of ATR, often smaller than a single minute bar's range, so
whether the entry bar itself stops the trade cannot be read from minute bars. Second bars
settle it for the entry window. Pulled now while the plan is active so nothing is missing
later; stored in a separate DuckDB file so it never contends with the research store.

Usage:
    py -3 research/orb/fetch_seconds.py            # all selected long symbol-days (rank <= 30)
    py -3 research/orb/fetch_seconds.py --top 20 --end 10:30
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as dtime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd
import requests

from common import STORE_DIR, connect, load_env

ET = ZoneInfo("America/New_York")
SECONDS_DB = STORE_DIR / "seconds.duckdb"
API_BASES = ("https://api.massive.com", "https://api.polygon.io")
WORKERS = 8

SCHEMA = """
CREATE TABLE IF NOT EXISTS seconds_selected (
    ticker VARCHAR, d DATE, t_ms BIGINT, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
    volume BIGINT, n INTEGER);
CREATE TABLE IF NOT EXISTS seconds_done (ticker VARCHAR, d DATE, rows INTEGER, status VARCHAR,
    fetched_at TIMESTAMP, PRIMARY KEY (ticker, d));
"""


def _key() -> str:
    key = (os.environ.get("MASSIVE_API_KEY") or os.environ.get("POLYGON_API_KEY")
           or os.environ.get("MASSIVE_S3_SECRET_ACCESS_KEY") or "").strip()
    if not key:
        sys.exit("no Massive key in .env")
    return key


def _ms(d: date, t: dtime) -> int:
    return int(datetime.combine(d, t, tzinfo=ET).timestamp() * 1000)


def fetch_one(session: requests.Session, key: str, base: str, ticker: str, d: date,
              start: dtime, end: dtime) -> tuple[str, list[dict]]:
    url = (f"{base}/v2/aggs/ticker/{quote(ticker, safe='')}/range/1/second/"
           f"{_ms(d, start)}/{_ms(d, end)}")
    params = {"adjusted": "false", "sort": "asc", "limit": 50000, "apiKey": key}
    rows: list[dict] = []
    for attempt in range(1, 6):
        try:
            r = session.get(url, params=params, timeout=60)
            if r.status_code in (401, 403):
                return f"refused:{r.status_code}", []
            if r.status_code == 404:
                return "missing", []
            if r.status_code == 429:
                time.sleep(3 * attempt)
                continue
            r.raise_for_status()
            body = r.json()
            rows.extend(body.get("results") or [])
            nxt = body.get("next_url")
            while nxt:
                r = session.get(nxt, params={"apiKey": key}, timeout=60)
                r.raise_for_status()
                body = r.json()
                rows.extend(body.get("results") or [])
                nxt = body.get("next_url")
            return "ok", rows
        except requests.RequestException as exc:
            if attempt == 5:
                return f"error:{str(exc)[:60]}", []
            time.sleep(2 * attempt)
    return "error:retries", []


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--start", default="09:30")
    ap.add_argument("--end", default="11:00")
    ap.add_argument("--direction", default="long")
    a = ap.parse_args()
    start = dtime(*(int(x) for x in a.start.split(":")))
    end = dtime(*(int(x) for x in a.end.split(":")))

    src = connect(read_only=True)
    wanted = src.execute(
        "SELECT ticker, d FROM selection WHERE rank <= ? AND direction = ? ORDER BY d, rank", [a.top, a.direction]
    ).fetchall()
    src.close()
    con = duckdb.connect(str(SECONDS_DB))
    con.execute(SCHEMA)
    done = {(r[0], r[1]) for r in con.execute("SELECT ticker, d FROM seconds_done").fetchall()}
    todo = [(t, d) for t, d in wanted if (t, d) not in done]
    print(f"seconds: {len(done)} symbol-days done, {len(todo)} to fetch ({a.start}-{a.end} ET)", flush=True)

    key, base = _key(), API_BASES[0]
    session = requests.Session()
    t0, n_rows, n_ok, refused = time.time(), 0, 0, None
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(fetch_one, session, key, base, t, d, start, end): (t, d) for t, d in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            ticker, d = futures[fut]
            status, rows = fut.result()
            if status.startswith("refused"):
                refused = status
                break
            if rows:
                df = pd.DataFrame(rows)[["t", "o", "h", "l", "c", "v", "n"]]
                df.insert(0, "d", d)
                df.insert(0, "ticker", ticker)
                con.execute("INSERT INTO seconds_selected SELECT * FROM df")
                n_rows += len(df)
                n_ok += 1
            con.execute("INSERT OR REPLACE INTO seconds_done VALUES (?, ?, ?, ?, ?)",
                        [ticker, d, len(rows), status, datetime.now()])
            if i % 500 == 0:
                print(f"  {i}/{len(todo)} symbol-days, {n_rows} rows, {time.time() - t0:.0f}s", flush=True)
    con.close()
    if refused:
        print(f"seconds: {refused} -- the plan does not serve second aggregates; stopped", flush=True)
        return 2
    print(f"seconds: fetched {n_ok} symbol-days, {n_rows} rows in {(time.time() - t0) / 60:.1f} min -> {SECONDS_DB}",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
