"""The kept headlines on disk.

Owner: ``market_news/feed.py`` writes, ``search`` reads. Store ``market_news.sqlite3`` beside the catalyst feed
(``catalysts.feed_store.root``). ``PRAGMA user_version = 1``; another version refuses to open. Invalidation: none --
items are history; ``coverage`` spans say when the feed was reading, so a quiet stretch is told apart from a gap.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from catalysts.feed_store import root
from constants_market_news import (
    MARKET_NEWS_DB_FILENAME,
    MARKET_NEWS_SCHEMA_VERSION,
    MARKET_NEWS_SQLITE_TIMEOUT_SEC,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    url TEXT PRIMARY KEY, published_ts REAL NOT NULL, headline TEXT NOT NULL, summary TEXT, source TEXT,
    symbols TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS items_by_time ON items (published_ts);
CREATE TABLE IF NOT EXISTS coverage (start_ts REAL PRIMARY KEY, end_ts REAL NOT NULL);
"""


class StoreVersionError(RuntimeError):
    pass


def path() -> Path:
    return root() / MARKET_NEWS_DB_FILENAME


def connect(database: Path | None = None) -> sqlite3.Connection:
    target = database or path()
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(target, timeout=MARKET_NEWS_SQLITE_TIMEOUT_SEC, check_same_thread=False)
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, MARKET_NEWS_SCHEMA_VERSION):
        db.close()
        raise StoreVersionError(f"{target}: schema version {version} is not {MARKET_NEWS_SCHEMA_VERSION}")
    db.executescript(SCHEMA)
    db.execute(f"PRAGMA user_version = {MARKET_NEWS_SCHEMA_VERSION}")
    return db


def put_items(db: sqlite3.Connection, items: Iterable[Mapping[str, Any]]) -> None:
    with db:
        db.executemany("INSERT OR IGNORE INTO items VALUES (?,?,?,?,?,?)",
                       [(i["url"], i["published_ts"], i["headline"], i.get("summary"), i.get("source"),
                         json.dumps(i.get("symbols") or [])) for i in items])


def put_span(db: sqlite3.Connection, start_ts: float, end_ts: float) -> None:
    with db:
        db.execute("INSERT OR REPLACE INTO coverage VALUES (?,?)", (start_ts, end_ts))


def search(db: sqlite3.Connection, words: list[str], since_ts: float, limit: int) -> list[dict[str, Any]]:
    """Newest first: items since ``since_ts`` with any of ``words`` in the headline or summary (none: every item)."""
    where = " OR ".join("headline LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\'" for _ in words)
    like = [f"%{w.replace(chr(92), chr(92) * 2).replace('%', r'\%').replace('_', r'\_')}%" for w in words]
    rows = db.execute(
        "SELECT published_ts, headline, source, url, symbols FROM items WHERE published_ts >= ?"
        + (f" AND ({where})" if words else "") + " ORDER BY published_ts DESC LIMIT ?",
        [since_ts, *[w for w in like for _ in (0, 1)], limit]).fetchall()
    return [{"published_ts": r[0], "headline": r[1], "source": r[2], "url": r[3], "symbols": json.loads(r[4])}
            for r in rows]


def spans_since(db: sqlite3.Connection, since_ts: float) -> list[tuple[float, float]]:
    return db.execute("SELECT start_ts, end_ts FROM coverage WHERE end_ts >= ? ORDER BY start_ts",
                      [since_ts]).fetchall()
