"""Versioned leaderboard schema (ADR 023). Unknown versions refuse loudly.

Version 2 (#498) adds the per-day catalyst tables Sim playback reads. A version-1 file is migrated
in place by creating those two tables only -- the rows / coverage history (tens of GB on the desk)
is never rewritten.
"""
from __future__ import annotations

import sqlite3

from constants_leaderboard import LEADERBOARD_SCHEMA_VERSION

ROW_COLUMNS = (
    "session_date", "minute_ts", "source", "board", "symbol", "rank",
    "price", "prev_close", "change_pct", "volume", "rvol", "rvol_basis",
    "float_shares", "has_news", "news_first_seen_ts", "gap_pct", "exchange",
    "market_cap",
)
COVERAGE_COLUMNS = ("session_date", "minute_ts", "source", "board", "state", "row_count", "run_id")
MINUTE_COLUMNS = ("session_date", "minute_ts", "run_id", "feed_live", "halt_feed_ok")
HALT_COLUMNS = ("symbol", "ts", "event", "kind", "code", "source", "session_date", "recorded_ts")
CATALYST_CHECK_COLUMNS = (
    "session_date", "symbol", "window_start", "window_end", "sources_answered", "rules_version", "exported_ts",
)
CATALYST_ITEM_COLUMNS = (
    "session_date", "symbol", "item_id", "published_ts", "source", "publisher", "title", "url",
    "kind", "category", "strength", "dilution", "rules_version",
)

# Schema 2 (#498): what research/catalysts/export_leaderboard.py copies from the research store, so
# playback judges a mover's news as known at the playhead without the backend reading that store.
# ``catalyst_checks``: one row per symbol-day exported, ``sources_answered`` (comma-joined, '' when
# none) the sources that looked across (window_start, window_end]. ``catalyst_items``: every item
# naming the symbol in that window, labelled by ``catalysts.classify`` at ``rules_version``.
_CATALYST_DDL = (
    """CREATE TABLE IF NOT EXISTS catalyst_checks (
    session_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    window_start REAL NOT NULL,
    window_end REAL NOT NULL,
    sources_answered TEXT NOT NULL,
    rules_version TEXT NOT NULL,
    exported_ts REAL NOT NULL,
    PRIMARY KEY (session_date, symbol)
)""",
    """CREATE TABLE IF NOT EXISTS catalyst_items (
    session_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    item_id TEXT NOT NULL,
    published_ts REAL NOT NULL,
    source TEXT NOT NULL,
    publisher TEXT,
    title TEXT,
    url TEXT,
    kind TEXT NOT NULL,
    category TEXT NOT NULL,
    strength TEXT,
    dilution INTEGER NOT NULL,
    rules_version TEXT NOT NULL,
    PRIMARY KEY (session_date, symbol, item_id)
)""",
)

_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_ts REAL NOT NULL,
    last_beat_ts REAL NOT NULL,
    stopped_ts REAL,
    stop_reason TEXT
);
CREATE TABLE IF NOT EXISTS minutes (
    session_date TEXT NOT NULL,
    minute_ts INTEGER NOT NULL,
    run_id TEXT NOT NULL,
    feed_live INTEGER NOT NULL,
    halt_feed_ok INTEGER NOT NULL,
    PRIMARY KEY (session_date, minute_ts)
);
CREATE TABLE IF NOT EXISTS coverage (
    session_date TEXT NOT NULL,
    minute_ts INTEGER NOT NULL,
    source TEXT NOT NULL,
    board TEXT NOT NULL,
    state TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    run_id TEXT,
    PRIMARY KEY (session_date, source, board, minute_ts)
);
CREATE TABLE IF NOT EXISTS rows (
    session_date TEXT NOT NULL,
    minute_ts INTEGER NOT NULL,
    source TEXT NOT NULL,
    board TEXT NOT NULL,
    symbol TEXT NOT NULL,
    rank INTEGER NOT NULL,
    price REAL,
    prev_close REAL,
    change_pct REAL,
    volume REAL,
    rvol REAL,
    rvol_basis TEXT,
    float_shares REAL,
    has_news INTEGER,
    news_first_seen_ts REAL,
    gap_pct REAL,
    exchange TEXT,
    market_cap REAL,
    PRIMARY KEY (session_date, source, board, minute_ts, symbol)
);
CREATE TABLE IF NOT EXISTS halt_events (
    symbol TEXT NOT NULL,
    ts REAL NOT NULL,
    event TEXT NOT NULL,
    kind TEXT,
    code TEXT,
    source TEXT NOT NULL,
    session_date TEXT NOT NULL,
    recorded_ts REAL NOT NULL,
    PRIMARY KEY (symbol, source, event, ts)
);
CREATE INDEX IF NOT EXISTS halt_events_day ON halt_events(session_date, symbol, ts);
"""


class UnknownLeaderboardSchema(sqlite3.DatabaseError):
    """The store was written by a newer Nova; reading it would be a guess."""


_MIGRATABLE = (1,)
# Versions a read-only reader may open as found (it never migrates): every one holds ``rows``.
READABLE_VERSIONS = (*_MIGRATABLE, LEADERBOARD_SCHEMA_VERSION)


def _version(db: sqlite3.Connection) -> int:
    return int(db.execute("PRAGMA user_version").fetchone()[0])


def _refuse_unknown(version: int) -> None:
    if version not in (0, LEADERBOARD_SCHEMA_VERSION, *_MIGRATABLE):
        raise UnknownLeaderboardSchema(
            f"leaderboard store schema version {version} is not {LEADERBOARD_SCHEMA_VERSION}"
        )


def initialize(db: sqlite3.Connection) -> None:
    version = _version(db)
    _refuse_unknown(version)
    if version == LEADERBOARD_SCHEMA_VERSION:
        return
    if version == 0:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(_DDL)
        for ddl in _CATALYST_DDL:
            db.execute(ddl)
        db.execute(f"PRAGMA user_version={LEADERBOARD_SCHEMA_VERSION}")
        db.commit()
        return
    _migrate_1_to_2(db)


def _migrate_1_to_2(db: sqlite3.Connection) -> None:
    """Add the catalyst tables; nothing existing is touched. Safe when another process migrates first."""
    db.execute("BEGIN IMMEDIATE")
    try:
        version = _version(db)  # re-read under the write lock
        _refuse_unknown(version)
        if version != LEADERBOARD_SCHEMA_VERSION:
            for ddl in _CATALYST_DDL:
                db.execute(ddl)
            db.execute(f"PRAGMA user_version={LEADERBOARD_SCHEMA_VERSION}")
        db.commit()
    except BaseException:
        db.rollback()
        raise
