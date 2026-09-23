"""Fold the live catalyst feed's recordings into the research store (ADR 024).

The desk records SEC filings and the press-release wires as they publish into
``catalyst_feed.sqlite3`` (``backend/catalysts/feed.py``); this copies those items -- same shape --
into ``catalysts.sqlite3`` so the history gains the wires directly from the day the feed started,
and records a ``checks`` row per target and feed source only where the feed's unbroken coverage
spanned the target's whole window (anything less is not a "looked"). Read-only on the feed store.

Usage:  py -3 research/catalysts/import_feed.py
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

from cat_config import ROOT
from store import connect, put_check

from constants_catalysts import CATALYST_FEED_COVERAGE_SOURCES, CATALYST_FEED_DB_FILENAME

COLS = ("item_id", "source", "published_ts", "title", "summary", "url", "publisher", "n_tickers", "form", "sec_items",
        "fetched_ts")


def main() -> int:
    feed_path = ROOT / CATALYST_FEED_DB_FILENAME
    if not feed_path.exists():
        print(f"{feed_path} does not exist yet -- the desk has not recorded a feed")
        return 0
    feed = sqlite3.connect(f"file:{feed_path.as_posix()}?mode=ro", uri=True)
    items = feed.execute(f"SELECT {', '.join(COLS)} FROM items").fetchall()
    tickers = feed.execute("SELECT item_id, ticker, published_ts FROM item_tickers").fetchall()
    spans = defaultdict(list)
    for source, s, e in feed.execute("SELECT source, start_ts, end_ts FROM coverage"):
        spans[source].append((s, e))
    feed.close()
    con = connect()
    with con:
        con.executemany(f"INSERT OR IGNORE INTO items VALUES ({', '.join('?' for _ in COLS)})", items)
        con.executemany("INSERT OR IGNORE INTO item_tickers VALUES (?,?,?)", tickers)
        n_checks = 0
        for ticker, day, w0, _cut, w1 in con.execute(
                "SELECT ticker, session_date, window_start, cutoff, window_end FROM targets").fetchall():
            for source in CATALYST_FEED_COVERAGE_SOURCES:
                if any(s <= w0 and e >= w1 for s, e in spans.get(source, ())):
                    n = con.execute("SELECT count(*) FROM item_tickers t JOIN items i USING (item_id) WHERE t.ticker = ? "
                                    "AND i.source = ? AND t.published_ts > ? AND t.published_ts <= ?",
                                    [ticker, source, w0, w1]).fetchone()[0]
                    put_check(con, ticker, day, f"feed_{source}", "ok", n_items=n)
                    n_checks += 1
    print(f"feed: {len(items)} items, {len(tickers)} ticker links folded in; {n_checks} target windows fully covered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
