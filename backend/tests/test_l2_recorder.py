"""Tests for efficient local L2 + tape recorders: batching, range recall,
session metadata, and graceful skip when IBKR is disconnected."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import l2.batch as batch
import l2.continuous as continuous
import l2.db as l2_db
import l2.recorder as recorder
import l2.sessions as sessions
import l2.tape as tape
from ibkr import client as ibkr_client_mod
from ibkr import depth as depth_mod
from l2.recall import recall_at, recall_range
from l2.store import get_nearest_snapshot, get_snapshots_in_range, record_snapshot


@pytest.fixture(autouse=True)
def isolated_dbs(tmp_path, monkeypatch):
    monkeypatch.setattr(l2_db, "cache_dir", lambda: tmp_path)
    l2_db.init_db()
    batch.clear_queues_for_tests()
    tape.clear_watched_for_tests()
    continuous.clear_for_tests()
    recorder._active_recordings.clear()
    yield
    batch.clear_queues_for_tests()
    tape.clear_watched_for_tests()
    continuous.clear_for_tests()
    recorder._active_recordings.clear()


def _book(bid_size=500, ask_size=100, bid_price=5.0, ask_price=5.05):
    return {
        "bids": [{"price": bid_price, "size": bid_size, "side": "bid"}],
        "asks": [{"price": ask_price, "size": ask_size, "side": "ask"}],
        "l1_fallback": False,
    }


class TestBatchWriter:
    def test_enqueue_does_not_write_until_flush(self, monkeypatch):
        monkeypatch.setattr(batch, "L2_BATCH_SIZE", 10_000)
        record_snapshot("AAPL:1", "AAPL", "depth", 1.0, 1.5, _book(), flush=False)
        assert batch.pending_counts()["snapshots"] == 1
        # Direct SQL (no store flush) should still be empty.
        conn = l2_db.get_connection()
        try:
            n = conn.execute("SELECT COUNT(*) FROM l2_snapshots").fetchone()[0]
        finally:
            conn.close()
        assert n == 0
        batch.flush()
        assert batch.pending_counts()["snapshots"] == 0
        assert len(get_snapshots_in_range("AAPL", 0, 10)) == 1

    def test_auto_flush_at_batch_size(self, monkeypatch):
        monkeypatch.setattr(batch, "L2_BATCH_SIZE", 3)
        for i in range(3):
            record_snapshot("AAPL:1", "AAPL", "depth", 1.0, float(i), _book(), flush=False)
        assert batch.pending_counts()["snapshots"] == 0
        assert len(get_snapshots_in_range("AAPL", 0, 10)) == 3


class TestRangeAndRecall:
    def test_snapshots_in_range_and_nearest(self):
        record_snapshot("AAPL:1", "AAPL", "depth", 100.0, 100.0, _book(100, 50))
        record_snapshot("AAPL:1", "AAPL", "depth", 100.0, 102.0, _book(200, 50))
        record_snapshot("AAPL:1", "AAPL", "depth", 100.0, 110.0, _book(300, 50))

        mid = get_snapshots_in_range("AAPL", 101.0, 103.0)
        assert len(mid) == 1
        assert mid[0]["bids"][0]["size"] == 200

        nearest = get_nearest_snapshot("AAPL", 102.4, window_sec=2.0)
        assert nearest is not None
        assert nearest["ts"] == 102.0

    def test_tape_range_and_recall_at(self):
        tape.watch_symbol("AAPL", session_id="sess-1")
        tape.on_alpaca_trade("AAPL", 5.01, 100, ts=1000.0)
        tape.on_alpaca_trade("AAPL", 5.02, 200, ts=1000.5)
        tape.on_alpaca_trade("MSFT", 10.0, 50, ts=1000.2)  # not watched
        batch.flush()

        trades = tape.get_trades_in_range("AAPL", 999.0, 1001.0)
        assert len(trades) == 2
        assert trades[0]["price"] == 5.01

        record_snapshot("AAPL:1", "AAPL", "depth", 1000.0, 1000.4, _book(), session_id="sess-1")
        sessions.start_session("AAPL", "depth", started_ts=999.0)

        result = recall_at("AAPL", 1000.4, window_sec=1.0)
        assert result["l2"] is not None
        assert result["tape_count"] == 2
        assert result["symbol"] == "AAPL"

        ranged = recall_range("AAPL", 1000.0, 1001.0)
        assert ranged["l2_count"] == 1
        assert ranged["tape_count"] == 2


class TestSessionsAndRetention:
    def test_session_covering(self):
        sid = sessions.start_session("AAPL", "depth", started_ts=100.0)
        assert sessions.session_covering("AAPL", 150.0)["session_id"] == sid
        sessions.end_session(sid, ended_ts=200.0)
        assert sessions.session_covering("AAPL", 150.0)["session_id"] == sid
        assert sessions.session_covering("AAPL", 250.0) is None

    def test_purge_older_than(self, monkeypatch):
        # P6 default refuses timer purge until cloud verify; tests opt out.
        monkeypatch.setattr(
            "constants.ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM",
            False,
        )
        old_ts = time.time() - (20 * 86400)
        record_snapshot("AAPL:old", "AAPL", "depth", old_ts, old_ts, _book())
        record_snapshot("AAPL:new", "AAPL", "depth", time.time(), time.time(), _book())
        result = l2_db.purge_older_than(retention_days=14)
        assert result["snapshots"] >= 1
        assert get_nearest_snapshot("AAPL", old_ts, window_sec=1.0) is None

    def test_purge_skipped_when_archive_trim_required(self, monkeypatch):
        monkeypatch.setattr(
            "constants.ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM",
            True,
        )
        old_ts = time.time() - (20 * 86400)
        record_snapshot("AAPL:guard", "AAPL", "depth", old_ts, old_ts, _book())
        result = l2_db.purge_older_than(retention_days=14)
        assert result.get("skipped") is True
        assert result["snapshots"] == 0
        assert get_nearest_snapshot("AAPL", old_ts, window_sec=1.0) is not None


class TestRecorderGracefulSkip:
    def test_on_signal_skips_when_ibkr_disconnected(self, monkeypatch):
        monkeypatch.setattr(ibkr_client_mod, "is_connected", lambda: False)
        called = []
        monkeypatch.setattr(depth_mod, "subscribe", lambda s: called.append(s) or {"ok": True})
        asyncio.run(recorder.on_signal("AAPL", "gap_and_go", time.time()))
        assert called == []
        assert tape.watched_symbols() == []

    def test_unwatched_trades_are_dropped(self):
        tape.on_alpaca_trade("ZZZZ", 1.0, 10, ts=1.0)
        batch.flush()
        assert tape.get_trades_in_range("ZZZZ", 0, 10) == []


class TestContinuousRecorder:
    def test_start_stop_writes_snapshots(self, monkeypatch):
        monkeypatch.setattr(continuous, "L2_CONTINUOUS_SNAPSHOT_INTERVAL_SEC", 0.01)
        monkeypatch.setattr(depth_mod, "current_book", lambda s: _book(400, 100))

        async def _run():
            continuous.start("AAPL")
            assert "AAPL" in continuous.active_symbols()
            assert "AAPL" in tape.watched_symbols()
            await asyncio.sleep(0.05)
            await continuous.stop("AAPL")

        asyncio.run(_run())
        rows = get_snapshots_in_range("AAPL", 0, time.time() + 10)
        assert len(rows) >= 1
        assert rows[0]["setup"] == "depth"
        assert "AAPL" not in continuous.active_symbols()
