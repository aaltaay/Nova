"""Tests for the Nova OS archive maintenance scheduler (P7/P8 hardening, #720)."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive.capture as capture
import archive.compact as compact
import archive.db as archive_db
import archive.scheduler as scheduler
import l2.db as l2_db
from constants import ARCHIVE_SCHEMA_VERSION, ARCHIVE_SOURCE_IBKR

_ET = ZoneInfo("America/New_York")
# Friday 2026-07-10: 21:00 ET is after Nova's session, 10:00 ET inside it.
AFTER_CLOSE = datetime(2026, 7, 10, 21, 0, tzinfo=_ET).timestamp()
IN_SESSION = datetime(2026, 7, 10, 10, 0, tzinfo=_ET).timestamp()
NEXT_NIGHT = datetime(2026, 7, 11, 21, 0, tzinfo=_ET).timestamp()
DAY = "2026-07-08"


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(compact, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(l2_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("archive.backup.cache_dir", lambda: tmp_path)
    monkeypatch.setattr(scheduler, "r2_enabled", lambda: False)
    archive_db.init_db()
    l2_db.init_db()
    capture.clear_l2_stub_for_tests()
    yield


def _bar(ts: float, *, close: float = 190.0, session_date: str = DAY, symbol: str = "AAPL") -> None:
    capture.record_bar(
        symbol=symbol,
        ts=ts,
        open_=189.0,
        high=191.0,
        low=188.5,
        close=close,
        volume=1000,
        source=ARCHIVE_SOURCE_IBKR,
        timeframe="1m",
        session_date=session_date,
    )


def _manifest(tmp_path: Path, table: str, day: str = DAY) -> dict:
    path = tmp_path / "archive_cold" / day / ARCHIVE_SCHEMA_VERSION / f"{table}.manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _count_compactions(monkeypatch) -> list[tuple[str, tuple[str, ...]]]:
    calls: list[tuple[str, tuple[str, ...]]] = []
    real = scheduler.compact_day

    def _spy(d, *, tables=None, **kwargs):
        calls.append((d, tuple(tables or ())))
        return real(d, tables=tables, **kwargs)

    monkeypatch.setattr(scheduler, "compact_day", _spy)
    return calls


def test_run_maintenance_once_also_compacts_l2_bridge(monkeypatch):
    """The scheduler must not just compact bars/tape_ibkr — it must also
    run the l2_bridge export for the same finished day, otherwise "persist
    all feeds" only covers the tables that were already durable."""
    _bar(1_720_000_000.0)

    calls: list[str] = []
    monkeypatch.setattr(
        scheduler,
        "compact_l2_day",
        lambda d, **kwargs: calls.append(d),
    )

    done = scheduler.run_maintenance_once(today="2026-07-10", now_ts=AFTER_CLOSE)
    assert DAY in done
    assert calls == [DAY]


def test_run_maintenance_once_l2_failure_does_not_block_primary_compaction(monkeypatch):
    """A crash in the l2_bridge step for one day must not prevent that day's
    primary bars/tape compaction from being recorded as done."""
    _bar(1_720_000_000.0)

    def _boom(d, **kwargs):
        raise RuntimeError("l2.db unavailable")

    monkeypatch.setattr(scheduler, "compact_l2_day", _boom)

    done = scheduler.run_maintenance_once(today="2026-07-10", now_ts=AFTER_CLOSE)
    assert DAY in done


def test_nothing_runs_inside_the_trading_session(monkeypatch, tmp_path):
    """#720: the run shares the trading process's GIL, so it waits for 20:00 ET."""
    _bar(1_720_000_000.0)
    calls = _count_compactions(monkeypatch)

    assert scheduler.run_maintenance_once(today="2026-07-10", now_ts=IN_SESSION) == []
    assert calls == []
    assert not (tmp_path / "backups").exists()
    assert not (tmp_path / "archive_cold" / DAY).exists()


def test_a_finished_day_is_compacted_once(monkeypatch):
    """#720: every hourly run re-exported every finished day (64 days, 8 GB)."""
    _bar(1_720_000_000.0)
    calls = _count_compactions(monkeypatch)
    l2_calls: list[str] = []
    real_l2 = scheduler.compact_l2_day

    def _l2_spy(d, **kwargs):
        l2_calls.append(d)
        return real_l2(d, **kwargs)

    monkeypatch.setattr(scheduler, "compact_l2_day", _l2_spy)

    assert scheduler.run_maintenance_once(today="2026-07-10", now_ts=AFTER_CLOSE) == [DAY]
    assert scheduler.run_maintenance_once(today="2026-07-10", now_ts=AFTER_CLOSE + 3600) == []

    assert [d for d, _ in calls] == [DAY]
    assert l2_calls == [DAY]


def test_late_rows_export_their_table_and_the_daily_bars(monkeypatch, tmp_path):
    _bar(1_720_000_000.0)
    scheduler.run_maintenance_once(today="2026-07-10", now_ts=AFTER_CLOSE)
    assert _manifest(tmp_path, "bars_1m")["row_count"] == 1
    assert _manifest(tmp_path, "bars_1d")["row_count"] == 1

    calls = _count_compactions(monkeypatch)
    _bar(1_720_000_060.0, close=195.0)

    assert scheduler.run_maintenance_once(today="2026-07-10", now_ts=AFTER_CLOSE + 3600) == [DAY]
    assert calls == [(DAY, ("bars_1m", "bars_1d"))]
    assert _manifest(tmp_path, "bars_1m")["row_count"] == 2
    daily = (tmp_path / "archive_cold" / DAY / ARCHIVE_SCHEMA_VERSION / "bars_1d.jsonl").read_text("utf-8")
    assert json.loads(daily.splitlines()[0])["close"] == 195.0


def test_a_trimmed_hot_day_keeps_its_cold_copy(monkeypatch, tmp_path):
    """Fewer hot rows than the manifest means trimmed hot data: never overwrite the cold copy."""
    _bar(1_720_000_000.0)
    _bar(1_720_000_060.0)
    scheduler.run_maintenance_once(today="2026-07-10", now_ts=AFTER_CLOSE)
    cold = tmp_path / "archive_cold" / DAY / ARCHIVE_SCHEMA_VERSION / "bars_1m.jsonl"
    before = cold.read_bytes()

    conn = archive_db.get_connection()
    try:
        conn.execute("DELETE FROM bars_1m WHERE ts = ?", (1_720_000_060.0,))
        conn.commit()
    finally:
        conn.close()
    calls = _count_compactions(monkeypatch)

    assert scheduler.run_maintenance_once(today="2026-07-10", now_ts=AFTER_CLOSE + 3600) == []
    assert calls == []
    assert cold.read_bytes() == before
    assert _manifest(tmp_path, "bars_1m")["row_count"] == 2


def test_backup_is_taken_once_a_day(monkeypatch):
    taken: list[str] = []
    import archive.backup as backup

    real = backup.backup_sqlite_once

    def _spy(*, now=None):
        taken.append(now.date().isoformat())
        return real(now=now)

    monkeypatch.setattr(backup, "backup_sqlite_once", _spy)

    scheduler.run_maintenance_once(today="2026-07-10", now_ts=AFTER_CLOSE)
    scheduler.run_maintenance_once(today="2026-07-10", now_ts=AFTER_CLOSE + 3600)
    scheduler.run_maintenance_once(today="2026-07-11", now_ts=NEXT_NIGHT)

    assert taken == ["2026-07-10", "2026-07-11"]


def test_r2_uploads_after_compaction_or_until_verified(monkeypatch):
    """A verified day is not re-read and re-checked with R2 every hour."""
    _bar(1_720_000_000.0)
    uploads: list[str] = []
    verified: set[str] = set()

    def _upload(d, **kwargs):
        uploads.append(d)
        verified.add(d)
        return {"ok": True}

    monkeypatch.setattr(scheduler, "r2_enabled", lambda: True)
    monkeypatch.setattr(scheduler, "upload_day", _upload)
    monkeypatch.setattr(scheduler, "is_day_verified_remote", lambda d: d in verified)
    monkeypatch.setattr(scheduler, "upload_l2_day", lambda d, **kw: {"ok": True})
    monkeypatch.setattr(scheduler, "is_l2_day_verified_remote", lambda d: True)

    scheduler.run_maintenance_once(today="2026-07-10", now_ts=AFTER_CLOSE)
    scheduler.run_maintenance_once(today="2026-07-10", now_ts=AFTER_CLOSE + 3600)
    assert uploads == [DAY]

    verified.clear()
    scheduler.run_maintenance_once(today="2026-07-10", now_ts=AFTER_CLOSE + 7200)
    assert uploads == [DAY, DAY]
