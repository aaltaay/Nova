"""Versioned leaderboard schema (ADR 022). Unknown versions refuse loudly."""
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


def initialize(db: sqlite3.Connection) -> None:
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, LEADERBOARD_SCHEMA_VERSION):
        raise UnknownLeaderboardSchema(
            f"leaderboard store schema version {version} is not {LEADERBOARD_SCHEMA_VERSION}"
        )
    if version == LEADERBOARD_SCHEMA_VERSION:
        return
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(_DDL)
    db.execute(f"PRAGMA user_version={LEADERBOARD_SCHEMA_VERSION}")
    db.commit()
