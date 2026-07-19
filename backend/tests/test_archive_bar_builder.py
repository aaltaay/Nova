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
