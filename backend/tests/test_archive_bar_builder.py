"""1m bars from tape — archive integrity for walk/replay."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive.bar_builder as bar_builder
import archive.capture as capture
import archive.db as archive_db


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    bar_builder.reset_for_tests()
    yield
    bar_builder.reset_for_tests()


def test_flush_elapsed_drops_quiet_open_bucket():
    m0 = int(1_700_000_000.0 // 60) * 60
    bar_builder.on_tape_print(symbol="QQQ", ts=m0 + 1, price=10.0, size=1)
    assert len(bar_builder._open) == 1
    assert bar_builder.flush_elapsed(m0 + 30, queued=False) == 0
    assert len(bar_builder._open) == 1
    assert bar_builder.flush_elapsed(m0 + 61, queued=False) == 1
    assert bar_builder._open == {}


def test_two_minutes_flush_two_bars():
    base = 1_700_000_000.0  # aligned-ish epoch
    m0 = int(base // 60) * 60
    bar_builder.on_tape_print(symbol="AAA", ts=m0 + 1, price=10.0, size=100)
    bar_builder.on_tape_print(symbol="AAA", ts=m0 + 30, price=11.0, size=50)
    bar_builder.on_tape_print(symbol="AAA", ts=m0 + 61, price=12.0, size=10)
    # First minute flushed on roll; second still open until flush_all
    n = bar_builder.flush_all()
    assert n == 1
    conn = archive_db.get_connection()
    try:
        rows = conn.execute(
            "SELECT ts, open, high, low, close, volume FROM bars_1m ORDER BY ts"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 2
    assert float(rows[0]["open"]) == 10.0
    assert float(rows[0]["high"]) == 11.0
    assert float(rows[0]["close"]) == 11.0
    assert float(rows[0]["volume"]) == 150.0
    assert float(rows[1]["open"]) == 12.0


def test_backfill_from_rows():
    rows = [
        {"symbol": "XYZ", "ts": 100.0, "price": 1.0, "size": 1, "source": "ibkr"},
        {"symbol": "XYZ", "ts": 120.0, "price": 2.0, "size": 2, "source": "ibkr"},
        {"symbol": "XYZ", "ts": 200.0, "price": 3.0, "size": 1, "source": "ibkr"},
    ]
    n = bar_builder.backfill_from_tape_rows(rows)
    assert n >= 1
    conn = archive_db.get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM bars_1m").fetchone()["c"]
    finally:
        conn.close()
    assert count >= 2


def test_rollup_daily_writes_bars_1d():
    capture.record_bar(
        symbol="AAA",
        ts=1_700_000_000.0,
        open_=10.0,
        high=11.0,
        low=9.5,
        close=10.5,
        volume=100,
        timeframe="1m",
        session_date="2026-08-17",
    )
    capture.record_bar(
        symbol="AAA",
        ts=1_700_000_060.0,
        open_=10.5,
        high=12.0,
        low=10.0,
        close=11.5,
        volume=50,
        timeframe="1m",
        session_date="2026-08-17",
    )
    n = bar_builder.rollup_daily("2026-08-17")
    assert n == 1
    conn = archive_db.get_connection()
    try:
        row = conn.execute(
            "SELECT open, high, low, close, volume FROM bars_1d WHERE symbol = 'AAA'"
        ).fetchone()
    finally:
        conn.close()
    assert float(row["open"]) == 10.0
    assert float(row["high"]) == 12.0
    assert float(row["low"]) == 9.5
    assert float(row["close"]) == 11.5
    assert float(row["volume"]) == 150.0


def test_rollup_daily_groups_by_symbol_and_source_in_any_insert_order():
    """#720: SQLite aggregates; open is the first minute's, close the last minute's."""
    day = "2026-08-18"
    minutes = [
        # (symbol, ts, open, high, low, close, volume, source), written out of order
        ("BBB", 1_700_000_120.0, 5.2, 5.3, 5.1, 5.25, 30, "ibkr"),
        ("BBB", 1_700_000_000.0, 5.0, 5.1, 4.9, 5.05, 10, "ibkr"),
        ("BBB", 1_700_000_060.0, 5.05, 5.6, 5.0, 5.2, 20, "ibkr"),
        ("BBB", 1_700_000_000.0, 7.0, 7.5, 6.5, 7.2, 5, "massive"),
        ("AAA", 1_700_000_060.0, 10.5, 12.0, 10.0, 11.5, 50, "ibkr"),
        ("AAA", 1_700_000_000.0, 10.0, 11.0, 9.5, 10.5, 100, "ibkr"),
    ]
    for symbol, ts, o, h, lo, c, v, source in minutes:
        capture.record_bar(
            symbol=symbol, ts=ts, open_=o, high=h, low=lo, close=c, volume=v,
            timeframe="1m", source=source, session_date=day,
        )

    assert bar_builder.rollup_daily(day) == 3
    assert bar_builder.rollup_daily(day) == 3  # an upsert: a second rollup adds nothing
    conn = archive_db.get_connection()
    try:
        rows = {
            (r["symbol"], r["source"]): (r["ts"], r["open"], r["high"], r["low"], r["close"], r["volume"])
            for r in conn.execute("SELECT * FROM bars_1d WHERE session_date = ?", (day,))
        }
    finally:
        conn.close()
    assert rows == {
        ("AAA", "ibkr"): (1_700_000_000.0, 10.0, 12.0, 9.5, 11.5, 150.0),
        ("BBB", "ibkr"): (1_700_000_000.0, 5.0, 5.6, 4.9, 5.25, 60.0),
        ("BBB", "massive"): (1_700_000_000.0, 7.0, 7.5, 6.5, 7.2, 5.0),
    }
    assert capture.get_counter("bars_1d") == 6


def test_rollup_daily_with_no_minutes_writes_nothing():
    assert bar_builder.rollup_daily("2026-08-19") == 0
