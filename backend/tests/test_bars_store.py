"""Durable chart bar store + coverage metadata."""
from __future__ import annotations

import archive.db as archive_db
import bars_store


def _payload(symbol="AIXC", timeframe="1Min", n=3):
    bars = [
        {
            "t": f"2026-08-18T14:0{i}:00Z",
            "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 100 + i,
        }
        for i in range(n)
    ]
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": bars,
        "source": "ibkr",
        "coverage": bars_store.coverage_from_bars(bars, filling=False),
    }


def test_write_then_read_returns_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    bars_store.write_payload(_payload(n=4))
    hit = bars_store.read("aixc", "1Min", 2)
    assert hit is not None
    assert hit["cache"] == "store"
    assert hit["source"] == "ibkr"
    assert len(hit["bars"]) == 2
    assert hit["coverage"]["as_of"] == "2026-08-18T14:03:00Z"
    assert hit["coverage"]["filling"] is False


def test_empty_filling_payload():
    out = bars_store.empty_filling("aixc", "5Min")
    assert out["bars"] == []
    assert out["coverage"]["filling"] is True
    assert out["source"] == "ibkr"


def test_read_miss_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    assert bars_store.read("NOPE", "1Min", 10) is None


def test_store_series_complete_rejects_intraday_stub():
    assert bars_store.store_series_complete("1Min", 0) is False
    assert bars_store.store_series_complete("1Min", 1) is False
    assert bars_store.store_series_complete("1Hour", 9) is False
    assert bars_store.store_series_complete("5Min", 8) is False
    assert bars_store.store_series_complete("5Min", 200) is True
    assert bars_store.store_series_complete("1Hour", 24) is True
    assert bars_store.store_series_complete("1Day", 1) is True


def test_bars_intraday_unique_is_one_candle(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    conn = archive_db.get_connection()
    try:
        cols = _unique_columns(conn, "bars_intraday")
    finally:
        conn.close()
    assert cols == ["symbol", "timeframe", "ts"]


def test_migrate_legacy_source_unique_keeps_hist(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    conn = archive_db.get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE bars_intraday (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                ts REAL NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL DEFAULT 0,
                source TEXT NOT NULL,
                session_date TEXT NOT NULL,
                UNIQUE(symbol, timeframe, ts, source)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO bars_intraday
                (symbol, timeframe, ts, open, high, low, close, volume, source, session_date)
            VALUES
                ('AIXC','1Min',100,1,2,0.5,1.5,10,'ibkr','2026-08-18'),
                ('AIXC','1Min',100,9,9,9,9,0,'ibkr_l1','2026-08-18')
            """
        )
        conn.commit()
    finally:
        conn.close()

    archive_db.init_db()
    conn = archive_db.get_connection()
    try:
        rows = conn.execute(
            "SELECT source, close, volume FROM bars_intraday",
        ).fetchall()
        cols = _unique_columns(conn, "bars_intraday")
    finally:
        conn.close()
    assert cols == ["symbol", "timeframe", "ts"]
    assert len(rows) == 1
    assert rows[0]["source"] == "ibkr"
    assert rows[0]["close"] == 1.5
    assert rows[0]["volume"] == 10


def _unique_columns(conn, table: str) -> list[str]:
    for idx in conn.execute(f"PRAGMA index_list({table})"):
        if not idx["unique"]:
            continue
        info = conn.execute(f"PRAGMA index_info({idx['name']})").fetchall()
        cols = [r["name"] for r in info]
        if "ts" in cols:
            return cols
    return []


def test_read_does_not_use_tape_bars_1m_stub(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    conn = archive_db.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO bars_1m
                (symbol, ts, open, high, low, close, volume, source, session_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("CDTG", 1787068800.0, 3.9, 3.95, 3.8, 3.93, 100, "ibkr", "2026-08-18"),
        )
        conn.commit()
    finally:
        conn.close()
    assert bars_store.read("CDTG", "1Min", 500) is None
