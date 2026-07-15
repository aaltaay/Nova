"""Tests for the Nova OS archive <-> l2/db.py bridge (P7/P8 hardening)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive.compact as compact
import archive.l2_bridge as l2_bridge
import l2.db as l2_db
from constants import ARCHIVE_SCHEMA_VERSION


@pytest.fixture(autouse=True)
def isolated_dbs(tmp_path, monkeypatch):
    monkeypatch.setattr(l2_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(compact, "cache_dir", lambda: tmp_path)
    l2_db.init_db()
    yield


def _et_ts(session_date: str, hour: int, minute: int = 0) -> float:
    start_ts, _ = l2_bridge.et_day_bounds(session_date)
    return start_ts + hour * 3600 + minute * 60


def _seed_l2_day(session_date: str = "2026-07-10") -> None:
    conn = l2_db.get_connection()
    try:
        conn.execute(
            """
            INSERT INTO l2_snapshots
                (recording_id, symbol, setup, signal_ts, ts, bids_json, asks_json, l1_fallback, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAPL:depth:1", "AAPL", "depth", _et_ts(session_date, 10), _et_ts(session_date, 10),
             "[]", "[]", 0, "sess-1"),
        )
        conn.execute(
            """
            INSERT INTO l2_snapshots
                (recording_id, symbol, setup, signal_ts, ts, bids_json, asks_json, l1_fallback, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAPL:depth:1", "AAPL", "depth", _et_ts(session_date, 10), _et_ts(session_date, 10, 1),
             "[]", "[]", 0, "sess-1"),
        )
        # Outside the target day — must not show up in rows_for_day / compact.
        conn.execute(
            """
            INSERT INTO l2_snapshots
                (recording_id, symbol, setup, signal_ts, ts, bids_json, asks_json, l1_fallback, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAPL:depth:1", "AAPL", "depth", 0.0, _et_ts(session_date, 10) - 86400.0,
             "[]", "[]", 0, "sess-0"),
        )
        conn.execute(
            "INSERT INTO tape_trades (symbol, ts, price, size, exchange, source, session_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("AAPL", _et_ts(session_date, 10), 190.0, 100, "ISLAND", "ibkr", "sess-1"),
        )
        conn.commit()
    finally:
        conn.close()


class TestRowsForDay:
    def test_rows_for_day_filters_by_et_calendar_day(self):
        _seed_l2_day("2026-07-10")
        rows = l2_bridge.rows_for_day("l2_snapshots", "2026-07-10")
        assert len(rows) == 2
        assert all(r["symbol"] == "AAPL" for r in rows)

    def test_rows_for_day_rejects_unknown_table(self):
        with pytest.raises(ValueError):
            l2_bridge.rows_for_day("bars_1m", "2026-07-10")


class TestCompactL2Day:
    def test_compact_writes_jsonl_and_manifest(self, tmp_path):
        _seed_l2_day("2026-07-10")
        cold = tmp_path / "archive_cold"
        mans = l2_bridge.compact_l2_day("2026-07-10", cold_dir=cold)
        by_table = {m["table_name"]: m for m in mans}
        assert by_table["l2_snapshots"]["row_count"] == 2
        assert by_table["tape_trades"]["row_count"] == 1

        day_dir = cold / "2026-07-10" / ARCHIVE_SCHEMA_VERSION
        assert (day_dir / "l2_snapshots.jsonl").is_file()
        assert (day_dir / "l2_snapshots.manifest.json").is_file()
        assert (day_dir / "tape_trades.jsonl").is_file()

    def test_compact_writes_empty_manifest_for_quiet_day(self, tmp_path):
        """A day with zero depth sessions must still produce a (row_count=0)
        manifest — otherwise upload_l2_day cannot tell "quiet day" apart
        from "compaction never ran"."""
        cold = tmp_path / "archive_cold"
        mans = l2_bridge.compact_l2_day("2026-07-15", cold_dir=cold)
        by_table = {m["table_name"]: m for m in mans}
        assert by_table["l2_snapshots"]["row_count"] == 0
        assert by_table["tape_trades"]["row_count"] == 0


class TestUploadL2Day:
    def test_upload_l2_day_missing_manifest_is_hard_failure(self, tmp_path, monkeypatch):
        _seed_l2_day("2026-07-10")
        cold = tmp_path / "archive_cold"
        l2_bridge.compact_l2_day("2026-07-10", cold_dir=cold)
        day_dir = cold / "2026-07-10" / ARCHIVE_SCHEMA_VERSION
        (day_dir / "tape_trades.manifest.json").unlink()

        store: dict[str, bytes] = {}

        class FakeClient:
            def head_object(self, Bucket, Key):
                if Key not in store:
                    err = Exception("404")
                    err.response = {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}
                    raise err
                return {}

            def put_object(self, Bucket, Key, Body, **kwargs):
                store[Key] = Body if isinstance(Body, bytes) else bytes(Body)

        monkeypatch.setenv("ARCHIVE_R2_ENABLED", "true")
        monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
        import archive.r2 as r2

        monkeypatch.setattr(r2, "boto3_available", lambda: True)
        monkeypatch.setattr(r2, "_client", lambda: (FakeClient(), "nova-archive"))

        result = l2_bridge.upload_l2_day("2026-07-10", cold_dir=cold)
        assert result["ok"] is False
        by_table = {u["table"]: u for u in result["uploads"]}
        assert by_table["tape_trades"]["ok"] is False
        assert not l2_bridge.is_l2_day_verified_remote("2026-07-10", cold)

    def test_upload_l2_day_marks_verified_independently_of_primary_index(self, tmp_path, monkeypatch):
        """The L2 bridge's verified index must be separate from
        archive.r2's — verifying one must not claim the other verified."""
        _seed_l2_day("2026-07-10")
        cold = tmp_path / "archive_cold"
        l2_bridge.compact_l2_day("2026-07-10", cold_dir=cold)

        store: dict[str, bytes] = {}

        class FakeClient:
            def head_object(self, Bucket, Key):
                if Key not in store:
                    err = Exception("404")
                    err.response = {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}
                    raise err
                return {}

            def put_object(self, Bucket, Key, Body, **kwargs):
                store[Key] = Body if isinstance(Body, bytes) else bytes(Body)

        monkeypatch.setenv("ARCHIVE_R2_ENABLED", "true")
        monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
        import archive.r2 as r2

        monkeypatch.setattr(r2, "boto3_available", lambda: True)
        monkeypatch.setattr(r2, "_client", lambda: (FakeClient(), "nova-archive"))

        result = l2_bridge.upload_l2_day("2026-07-10", cold_dir=cold)
        assert result["ok"] is True
        assert l2_bridge.is_l2_day_verified_remote("2026-07-10", cold)
        assert not r2.is_day_verified_remote("2026-07-10", cold)


class TestRestoreL2Day:
    def test_restore_round_trip(self, tmp_path):
        _seed_l2_day("2026-07-10")
        cold = tmp_path / "archive_cold"
        l2_bridge.compact_l2_day("2026-07-10", cold_dir=cold)
        result = l2_bridge.restore_l2_day_to_temp("2026-07-10", cold_dir=cold)
        assert result["ok"] is True
        assert result["expected"]["l2_snapshots"] == 2
        assert result["actual"]["l2_snapshots"] == 2
        assert result["expected"]["tape_trades"] == 1

    def test_restore_detects_tamper(self, tmp_path):
        _seed_l2_day("2026-07-10")
        cold = tmp_path / "archive_cold"
        l2_bridge.compact_l2_day("2026-07-10", cold_dir=cold)
        jsonl = cold / "2026-07-10" / ARCHIVE_SCHEMA_VERSION / "l2_snapshots.jsonl"
        jsonl.write_text(jsonl.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
        result = l2_bridge.restore_l2_day_to_temp("2026-07-10", cold_dir=cold)
        assert result["ok"] is False
        assert result["mismatches"]["l2_snapshots"]["error"] == "sha256_mismatch"
