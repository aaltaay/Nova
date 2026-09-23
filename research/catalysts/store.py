"""The catalyst store: one SQLite file on F: (``PRAGMA user_version = 1``; unknown versions refuse).

  targets       the symbol-days to explain: the prior close -> session end window and the
                cutoff a catalyst must precede (09:30 for the pillar universe, the first top-10
                minute for a leaderboard mover)
  items         every article / filing fetched, once, keyed ``<source>:<native id>``
  item_tickers  which tickers an item names
  checks        per (ticker, day, source): ``ok`` (looked, n items), ``error`` (retry),
                ``unavailable`` (no id / no key), ``out_of_range`` (the source cannot reach
                that date) -- so "nothing found" is provable and never confused with "not asked"
  verdicts      the classifier's answer per symbol-day and rules version
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from cat_config import DB_PATH

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS targets (
    ticker TEXT NOT NULL, session_date TEXT NOT NULL,
    window_start REAL NOT NULL, cutoff REAL NOT NULL, window_end REAL NOT NULL,
    origin TEXT NOT NULL, PRIMARY KEY (ticker, session_date));
CREATE TABLE IF NOT EXISTS items (
    item_id TEXT PRIMARY KEY, source TEXT NOT NULL, published_ts REAL NOT NULL,
    title TEXT, summary TEXT, url TEXT, publisher TEXT, n_tickers INTEGER,
    form TEXT, sec_items TEXT, fetched_ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS item_tickers (
    item_id TEXT NOT NULL, ticker TEXT NOT NULL, published_ts REAL NOT NULL,
    PRIMARY KEY (item_id, ticker));
CREATE INDEX IF NOT EXISTS item_tickers_by_ticker ON item_tickers (ticker, published_ts);
CREATE TABLE IF NOT EXISTS checks (
    ticker TEXT NOT NULL, session_date TEXT NOT NULL, source TEXT NOT NULL,
    status TEXT NOT NULL, n_items INTEGER, detail TEXT, checked_ts REAL NOT NULL,
    PRIMARY KEY (ticker, session_date, source));
CREATE TABLE IF NOT EXISTS verdicts (
    ticker TEXT NOT NULL, session_date TEXT NOT NULL, cutoff_kind TEXT NOT NULL,
    rules_version TEXT NOT NULL, verdict TEXT NOT NULL, category TEXT, strength TEXT,
    item_id TEXT, source TEXT, published_ts REAL, title TEXT, sources_checked TEXT,
    n_items INTEGER, PRIMARY KEY (ticker, session_date, cutoff_kind, rules_version));
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=60)
    version = con.execute("PRAGMA user_version").fetchone()[0]
    has_tables = con.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    if version not in (0, SCHEMA_VERSION) or (version == 0 and has_tables):
        con.close()
        raise RuntimeError(f"{path}: schema version {version} is not {SCHEMA_VERSION}; refusing to open")
    con.executescript(SCHEMA)
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def put_items(con: sqlite3.Connection, rows: list[dict]) -> int:
    """Insert items (first fetch wins) and their tickers. Returns rows offered."""
    now = time.time()
    con.executemany(
        "INSERT OR IGNORE INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(r["item_id"], r["source"], r["published_ts"], r.get("title"), r.get("summary"), r.get("url"),
          r.get("publisher"), (r["n_tickers"] if "n_tickers" in r else len(r.get("tickers") or ())), r.get("form"), r.get("sec_items"), now) for r in rows])
    con.executemany(
        "INSERT OR IGNORE INTO item_tickers VALUES (?,?,?)",
        [(r["item_id"], t.upper(), r["published_ts"]) for r in rows for t in set(r.get("tickers") or ()) if t])
    return len(rows)


def put_check(con: sqlite3.Connection, ticker: str, day: str, source: str, status: str,
              n_items: int | None = None, detail: str | None = None) -> None:
    con.execute("INSERT OR REPLACE INTO checks VALUES (?,?,?,?,?,?,?)",
                (ticker, day, source, status, n_items, detail, time.time()))


def pending(con: sqlite3.Connection, source: str, retry_errors: bool = True) -> list[tuple]:
    """Targets this source has not answered (``error`` rows are retried)."""
    done = "c.status != 'error'" if retry_errors else "1=1"
    return con.execute(
        f"SELECT t.ticker, t.session_date, t.window_start, t.cutoff, t.window_end FROM targets t "
        f"WHERE NOT EXISTS (SELECT 1 FROM checks c WHERE c.ticker = t.ticker AND c.session_date = t.session_date "
        f"AND c.source = ? AND {done}) ORDER BY t.session_date DESC, t.ticker", [source]).fetchall()
