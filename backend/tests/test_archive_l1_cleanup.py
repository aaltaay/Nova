"""Epoch-0 L1 rows and the 1969-12-31 cold folder are deleted."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive.capture as capture
import archive.db as archive_db
import archive.l1_cleanup as cleanup


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    yield tmp_path


def test_purge_epoch_zero_l1(tmp_path, isolated_archive):
    conn = archive_db.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO l1_ticks (symbol, ts, price, volume, day_high, session_date)
            VALUES ('BAD', 0, 1.0, NULL, NULL, '1969-12-31')
            """
        )
        conn.execute(
            """
            INSERT INTO l1_ticks (symbol, ts, price, volume, day_high, session_date)
            VALUES ('OK', 1700000000, 2.0, NULL, NULL, '2026-08-17')
            """
        )
        conn.commit()
    finally:
        conn.close()
    cold = isolated_archive / "archive_cold" / "1969-12-31"
    cold.mkdir(parents=True)
    (cold / "l1_ticks.jsonl").write_text("{}\n", encoding="utf-8")
    deleted = cleanup.purge_epoch_zero_l1()
    assert deleted == 1
    conn = archive_db.get_connection()
    try:
        n = conn.execute("SELECT COUNT(*) FROM l1_ticks").fetchone()[0]
        left = conn.execute("SELECT symbol FROM l1_ticks").fetchone()[0]
    finally:
        conn.close()
    assert n == 1
    assert left == "OK"
    assert not cold.exists()


def test_purge_reads_the_date_index_not_the_whole_table(isolated_archive):
    """It runs on every start: a full scan of l1_ticks cost ~28 s of each restart (2026-09-30)."""
    captured: list[str] = []
    real = archive_db.get_connection

    def spy():
        conn = real()
        conn.set_trace_callback(captured.append)
        return conn

    import unittest.mock as mock

    with mock.patch.object(archive_db, "get_connection", spy):
        cleanup.purge_epoch_zero_l1()
    delete = next(s for s in captured if s.lstrip().upper().startswith("DELETE FROM L1_TICKS"))
    conn = archive_db.get_connection()
    try:
        plan = " ".join(str(r[3]) for r in conn.execute(f"EXPLAIN QUERY PLAN {delete}"))
    finally:
        conn.close()
    assert "idx_l1_ticks_date" in plan, plan
    assert "SCAN l1_ticks" not in plan, plan
