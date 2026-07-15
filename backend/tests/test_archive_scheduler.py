"""Tests for the Nova OS archive maintenance scheduler (P7/P8 hardening)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive.capture as capture
import archive.compact as compact
import archive.db as archive_db
import archive.scheduler as scheduler
import l2.db as l2_db
from constants import ARCHIVE_SOURCE_IBKR


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(compact, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(l2_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    l2_db.init_db()
    capture.clear_l2_stub_for_tests()
    yield


def test_run_maintenance_once_also_compacts_l2_bridge(monkeypatch):
    """The scheduler must not just compact bars/tape_ibkr — it must also
    run the l2_bridge export for the same finished day, otherwise "persist
    all feeds" only covers the tables that were already durable."""
    capture.record_bar(
        symbol="AAPL",
        ts=1_720_000_000.0,
        open_=189.0,
        high=191.0,
        low=188.5,
        close=190.0,
        volume=1000,
        source=ARCHIVE_SOURCE_IBKR,
        timeframe="1m",
        session_date="2026-07-08",
    )

    calls: list[str] = []
    monkeypatch.setattr(
        scheduler,
        "compact_l2_day",
        lambda d, **kwargs: calls.append(d),
    )

    done = scheduler.run_maintenance_once(today="2026-07-10")
    assert "2026-07-08" in done
    assert calls == ["2026-07-08"]


def test_run_maintenance_once_l2_failure_does_not_block_primary_compaction(monkeypatch):
    """A crash in the l2_bridge step for one day must not prevent that day's
    primary bars/tape compaction from being recorded as done."""
    capture.record_bar(
        symbol="AAPL",
        ts=1_720_000_000.0,
        open_=189.0,
        high=191.0,
        low=188.5,
        close=190.0,
        volume=1000,
        source=ARCHIVE_SOURCE_IBKR,
        timeframe="1m",
        session_date="2026-07-08",
    )

    def _boom(d, **kwargs):
        raise RuntimeError("l2.db unavailable")

    monkeypatch.setattr(scheduler, "compact_l2_day", _boom)

    done = scheduler.run_maintenance_once(today="2026-07-10")
    assert "2026-07-08" in done
