"""Tests for Nova OS P7 cold compact + restore."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive.capture as capture
import archive.compact as compact
import archive.db as archive_db
import archive.manifest as manifest
import archive.restore as restore
from constants import ARCHIVE_SCHEMA_VERSION, ARCHIVE_SOURCE_IBKR


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(compact, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    capture.clear_l2_stub_for_tests()
    yield


def _seed_day(session_date: str = "2026-07-10") -> None:
    capture.record_tape_print(
        symbol="AAPL",
        ts=1_720_000_000.0,
        price=190.0,
        size=50,
        source=ARCHIVE_SOURCE_IBKR,
        session_date=session_date,
    )
    capture.record_tape_print(
        symbol="AAPL",
        ts=1_720_000_001.0,
        price=190.1,
        size=25,
        source=ARCHIVE_SOURCE_IBKR,
        session_date=session_date,
    )
    capture.record_bar(
        symbol="AAPL",
        ts=1_720_000_000.0,
        open_=189.0,
        high=191.0,
        low=188.5,
        close=190.0,
        volume=10_000,
        timeframe="1m",
        session_date=session_date,
    )
    capture.record_bar(
        symbol="AAPL",
        ts=1_720_000_000.0,
        open_=189.0,
        high=191.0,
        low=188.5,
        close=190.0,
        volume=1_000_000,
        timeframe="1d",
        session_date=session_date,
    )
    capture.record_gap(
        stream="tape",
        symbol="AAPL",
        start_ts=1_720_000_010.0,
        end_ts=1_720_000_020.0,
        reason="test",
        session_date=session_date,
    )
    capture.mark_incomplete_window(
        stream="tape",
        start_ts=1_720_000_010.0,
        end_ts=1_720_000_020.0,
        note="test incomplete",
        session_date=session_date,
    )


class TestCompactRestore:
    def test_compact_writes_jsonl_and_manifest(self, tmp_path):
        _seed_day("2026-07-10")
        mans = compact.compact_day("2026-07-10", cold_dir=tmp_path / "archive_cold")
        by_table = {m["table_name"]: m for m in mans}
        assert by_table["tape_ibkr"]["row_count"] == 2
        assert by_table["bars_1m"]["row_count"] == 1
        assert by_table["bars_1d"]["row_count"] == 1
        assert by_table["tape_ibkr"]["schema_version"] == ARCHIVE_SCHEMA_VERSION

        day_dir = tmp_path / "archive_cold" / "2026-07-10" / ARCHIVE_SCHEMA_VERSION
        jsonl = day_dir / "tape_ibkr.jsonl"
        man_path = day_dir / "tape_ibkr.manifest.json"
        assert jsonl.is_file()
        assert man_path.is_file()
        man = manifest.read_manifest(man_path)
        assert manifest.verify_payload(jsonl, man["sha256"])
        assert man["row_count"] == 2

    def test_restore_compares_row_counts(self, tmp_path):
        cold = tmp_path / "archive_cold"
        _seed_day("2026-07-10")
        compact.compact_day("2026-07-10", cold_dir=cold)
        result = restore.restore_day_to_temp("2026-07-10", cold_dir=cold)
        assert result["ok"] is True
        assert result["expected"]["tape_ibkr"] == 2
        assert result["actual"]["tape_ibkr"] == 2
        assert result["expected"]["bars_1m"] == 1
        assert result["mismatches"] == {}
        assert Path(result["db_path"]).is_file()

    def test_restore_detects_checksum_tamper(self, tmp_path):
        cold = tmp_path / "archive_cold"
        _seed_day("2026-07-11")
        compact.compact_day("2026-07-11", cold_dir=cold)
        jsonl = cold / "2026-07-11" / ARCHIVE_SCHEMA_VERSION / "tape_ibkr.jsonl"
        jsonl.write_text(jsonl.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
        result = restore.restore_day_to_temp("2026-07-11", cold_dir=cold)
        assert result["ok"] is False
        assert "tape_ibkr" in result["mismatches"]
        assert result["mismatches"]["tape_ibkr"]["error"] == "sha256_mismatch"

    def test_restore_missing_manifest_is_hard_failure(self, tmp_path):
        """A day where compact_day crashed before writing one table's
        manifest must fail the restore drill, not silently report ok=True
        for the tables that did compact."""
        cold = tmp_path / "archive_cold"
        _seed_day("2026-07-12")
        compact.compact_day("2026-07-12", cold_dir=cold)
        day_dir = cold / "2026-07-12" / ARCHIVE_SCHEMA_VERSION
        (day_dir / "bars_1d.manifest.json").unlink()

        result = restore.restore_day_to_temp("2026-07-12", cold_dir=cold)
        assert result["ok"] is False
        assert result["mismatches"]["bars_1d"]["error"] == "manifest_missing"

    def test_compact_write_is_atomic_no_tmp_left_behind(self, tmp_path):
        """write_jsonl_atomic must never leave a stray temp file behind on
        the happy path, and the final file must be exactly the new content
        (not appended/partial)."""
        cold = tmp_path / "archive_cold"
        _seed_day("2026-07-13")
        compact.compact_day("2026-07-13", cold_dir=cold)
        day_dir = cold / "2026-07-13" / ARCHIVE_SCHEMA_VERSION
        leftover_tmp = list(day_dir.glob("*.tmp*"))
        assert leftover_tmp == []
        jsonl = day_dir / "tape_ibkr.jsonl"
        assert len(jsonl.read_text(encoding="utf-8").strip().splitlines()) == 2

    def test_list_finished_dates(self):
        _seed_day("2026-07-08")
        _seed_day("2026-07-09")
        dates = compact.list_finished_dates("2026-07-10")
        assert "2026-07-08" in dates
        assert "2026-07-09" in dates
        assert "2026-07-10" not in dates

    def test_compare_row_counts_helper(self):
        diff = restore.compare_row_counts({"a": 1, "b": 2}, {"a": 1, "b": 3})
        assert diff == {"b": {"expected": 2, "actual": 3}}
