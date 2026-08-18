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
