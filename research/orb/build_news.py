"""Load the reference dump into the research store: news mentions and ticker details.

``news_tickers``: one row per (article, ticker) with the publish time in UTC and the
Eastern trading date it belongs to for a *next-open* catalyst test -- an article published
after 16:00 ET is a catalyst for the next session, so ``session_d`` is shifted accordingly
(weekends roll to Monday; holidays are handled by joining to trading days later).
``ticker_details``: shares outstanding, market cap, SIC, list date (current values from the
API -- not point-in-time; the plan note states this caveat).

Usage:
    py -3 research/orb/build_news.py
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from common import STORE_DIR, connect, load_env

REF_DIR = STORE_DIR / "reference"
ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

SCHEMA = """
CREATE TABLE IF NOT EXISTS news_tickers (
    ticker VARCHAR, published_utc TIMESTAMP, session_d DATE, article_id VARCHAR,
    publisher VARCHAR, title VARCHAR);
CREATE TABLE IF NOT EXISTS news_months (month VARCHAR PRIMARY KEY, articles INTEGER, rows INTEGER, loaded_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS ticker_details (
    ticker VARCHAR PRIMARY KEY, name VARCHAR, type VARCHAR, active BOOLEAN, market_cap DOUBLE,
    shares_outstanding DOUBLE, weighted_shares DOUBLE, sic_code VARCHAR, sic_description VARCHAR,
    list_date DATE, primary_exchange VARCHAR);
"""


def session_date(published_utc: str):
    """Eastern session an article is a catalyst for: same day if before 16:00 ET, else next weekday."""
    ts = datetime.fromisoformat(published_utc.replace("Z", "+00:00")).astimezone(ET)
    d = ts.date()
    if ts.time() >= datetime.strptime("16:00", "%H:%M").time():
        d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return ts.astimezone(UTC).replace(tzinfo=None), d


def load_news(con) -> None:
    news_dir = REF_DIR / "news"
    done = {r[0] for r in con.execute("SELECT month FROM news_months").fetchall()}
    files = sorted(news_dir.glob("*.jsonl")) if news_dir.exists() else []
    # the newest month may still be growing: always reload it
    todo = [p for p in files if p.stem not in done or p == files[-1]]
    print(f"news: {len(done)} months loaded, {len(todo)} to load", flush=True)
    for p in todo:
        t0 = time.time()
        rows, articles = [], 0
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                a = json.loads(line)
            except ValueError:
                continue
            pub = a.get("published_utc")
            if not pub:
                continue
            articles += 1
            ts, d = session_date(pub)
            for t in a.get("tickers") or []:
                rows.append((t, ts, d, a.get("id"), (a.get("publisher") or {}).get("name"), (a.get("title") or "")[:200]))
        con.execute("BEGIN")
        con.execute("DELETE FROM news_tickers WHERE article_id IN (SELECT article_id FROM news_tickers "
                    "WHERE strftime(published_utc, '%Y-%m') = ?)", [p.stem])
        con.executemany("INSERT INTO news_tickers VALUES (?, ?, ?, ?, ?, ?)", rows)
        con.execute("INSERT OR REPLACE INTO news_months VALUES (?, ?, ?, ?)", [p.stem, articles, len(rows), datetime.now()])
        con.execute("COMMIT")
        print(f"  {p.stem}: {articles} articles, {len(rows)} ticker rows, {time.time() - t0:.1f}s", flush=True)


def load_details(con) -> None:
    path = REF_DIR / "ticker_details.jsonl"
    if not path.exists():
        print("ticker_details: not fetched yet", flush=True)
        return
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if not r.get("ticker") or r.get("_missing") or r.get("_error"):
            continue
        rows.append((r["ticker"], r.get("name"), r.get("type"), r.get("active"), r.get("market_cap"),
                     r.get("share_class_shares_outstanding"), r.get("weighted_shares_outstanding"),
                     r.get("sic_code"), r.get("sic_description"), r.get("list_date"), r.get("primary_exchange")))
    con.execute("DELETE FROM ticker_details")
    con.executemany("INSERT OR REPLACE INTO ticker_details VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    n = con.execute("SELECT count(*), count(shares_outstanding), count(*) FILTER (WHERE shares_outstanding <= 20e6) "
                    "FROM ticker_details").fetchone()
    print(f"ticker_details: {n[0]} rows, {n[1]} with shares outstanding, {n[2]} at or under 20M", flush=True)


def main() -> int:
    load_env()
    con = connect()
    con.execute(SCHEMA)
    load_news(con)
    load_details(con)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
