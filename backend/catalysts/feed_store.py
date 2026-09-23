"""The recorded catalyst feed on disk (ADR 024).

Owner: ``catalysts/feed.py``. Store ``catalyst_feed.sqlite3`` under ``NOVA_CATALYST_DIR``, else
``F:\\Nova\\catalysts`` when F: is mounted, else ``<cache>/catalysts`` -- beside the research store,
never inside it. ``PRAGMA user_version = 1``; an unknown version, or an unversioned file that already
holds tables, refuses to open. Invalidation: none -- items are history, kept like the leaderboard;
``coverage`` spans say when each source was being read, so a quiet stretch is told apart from a gap.

  items / item_tickers   the research store's shape (``research/catalysts/store.py``)
  coverage               (source, start_ts, end_ts): unbroken reading of one source
"""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from constants_catalysts import (
    CATALYST_DEFAULT_ROOT_WIN,
    CATALYST_DIR_ENV,
    CATALYST_FEED_DB_FILENAME,
    CATALYST_FEED_SCHEMA_VERSION,
    CATALYST_FEED_SQLITE_TIMEOUT_SEC,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    item_id TEXT PRIMARY KEY, source TEXT NOT NULL, published_ts REAL NOT NULL,
    title TEXT, summary TEXT, url TEXT, publisher TEXT, n_tickers INTEGER,
    form TEXT, sec_items TEXT, fetched_ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS item_tickers (
    item_id TEXT NOT NULL, ticker TEXT NOT NULL, published_ts REAL NOT NULL,
    PRIMARY KEY (item_id, ticker));
CREATE INDEX IF NOT EXISTS feed_tickers_by_ticker ON item_tickers (ticker, published_ts);
CREATE TABLE IF NOT EXISTS coverage (
    source TEXT NOT NULL, start_ts REAL NOT NULL, end_ts REAL NOT NULL,
    PRIMARY KEY (source, start_ts));
"""
ITEM_COLUMNS = ("item_id", "source", "published_ts", "title", "summary", "url", "publisher", "n_tickers",
                "form", "sec_items", "fetched_ts")


class FeedStoreVersionError(RuntimeError):
    pass


def root() -> Path:
    configured = (os.environ.get(CATALYST_DIR_ENV) or "").strip()
    if configured:
        return Path(configured)
    if Path("F:/").exists():
        return Path(CATALYST_DEFAULT_ROOT_WIN)
    from paths import cache_dir

    return Path(cache_dir()) / "catalysts"


def path() -> Path:
    return root() / CATALYST_FEED_DB_FILENAME


def connect(database: Path | None = None) -> sqlite3.Connection:
    target = database or path()
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(target), timeout=CATALYST_FEED_SQLITE_TIMEOUT_SEC, check_same_thread=False)
    version = db.execute("PRAGMA user_version").fetchone()[0]
    tables = db.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
    if version not in (0, CATALYST_FEED_SCHEMA_VERSION) or (version == 0 and tables):
        db.close()
        raise FeedStoreVersionError(
            f"{target}: schema version {version} is not {CATALYST_FEED_SCHEMA_VERSION}; refusing to open")
    db.executescript(SCHEMA)
    db.execute(f"PRAGMA user_version = {CATALYST_FEED_SCHEMA_VERSION}")
    db.execute("PRAGMA journal_mode = WAL")
    return db


def put_items(db: sqlite3.Connection, items: Iterable[dict[str, Any]]) -> int:
    """Insert new items (first write wins) and their tickers. Returns the rows offered."""
    now = time.time()
    rows = list(items)
    with db:
        db.executemany(
            f"INSERT OR IGNORE INTO items ({', '.join(ITEM_COLUMNS)}) VALUES ({', '.join('?' for _ in ITEM_COLUMNS)})",
            [(r["item_id"], r["source"], r["published_ts"], r.get("title"), r.get("summary"), r.get("url"),
              r.get("publisher"), len(r.get("tickers") or ()), r.get("form"), r.get("sec_items"), now) for r in rows])
        db.executemany("INSERT OR IGNORE INTO item_tickers VALUES (?,?,?)",
                       [(r["item_id"], t, r["published_ts"]) for r in rows for t in r.get("tickers") or ()])
    return len(rows)


def put_span(db: sqlite3.Connection, source: str, start_ts: float, end_ts: float) -> None:
    with db:
        db.execute("INSERT OR REPLACE INTO coverage VALUES (?,?,?)", (source, float(start_ts), float(end_ts)))


def items_since(db: sqlite3.Connection, since_ts: float) -> list[dict[str, Any]]:
    """Every item published after ``since_ts`` with its tickers (the live window's warm start)."""
    rows = db.execute(
        f"SELECT {', '.join('i.' + c for c in ITEM_COLUMNS)}, group_concat(t.ticker) FROM items i "
        "LEFT JOIN item_tickers t USING (item_id) WHERE i.published_ts > ? GROUP BY i.item_id", [since_ts]).fetchall()
    out = []
    for r in rows:
        item = dict(zip(ITEM_COLUMNS, r[:-1], strict=True))
        item["tickers"] = [t for t in (r[-1] or "").split(",") if t]
        out.append(item)
    return out


def spans_since(db: sqlite3.Connection, since_ts: float) -> list[tuple[str, float, float]]:
    return [tuple(r) for r in db.execute(
        "SELECT source, start_ts, end_ts FROM coverage WHERE end_ts > ? ORDER BY source, start_ts", [since_ts])]
