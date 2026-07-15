"""Tests for Nova OS P6 loss-aware local archive capture."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive.capture as capture
import archive.db as archive_db
from constants import (
    ARCHIVE_COUNTER_BARS_1M,
    ARCHIVE_COUNTER_GAPS,
    ARCHIVE_COUNTER_INCOMPLETE_WINDOWS,
    ARCHIVE_COUNTER_L2_SNAPSHOTS,
    ARCHIVE_COUNTER_TAPE_RECEIVED,
    ARCHIVE_SOURCE_IBKR,
    ARCHIVE_STREAM_TAPE,
)


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    capture.clear_l2_stub_for_tests()
    yield
    capture.clear_l2_stub_for_tests()


class TestArchiveCapture:
    def test_record_tape_print_and_counter(self):
        capture.record_tape_print(
            symbol="aapl",
            ts=1_700_000_000.0,
            price=190.5,
            size=100,
            exchange="ISLAND",
            side="ask",
            source=ARCHIVE_SOURCE_IBKR,
            session_date="2026-07-14",
        )
        conn = archive_db.get_connection()
        try:
            n = conn.execute("SELECT COUNT(*) FROM tape_ibkr").fetchone()[0]
            row = conn.execute("SELECT symbol, price, source FROM tape_ibkr").fetchone()
        finally:
            conn.close()
        assert n == 1
        assert row["symbol"] == "AAPL"
        assert row["price"] == 190.5
        assert row["source"] == ARCHIVE_SOURCE_IBKR
        assert capture.get_counter(ARCHIVE_COUNTER_TAPE_RECEIVED) == 1

    def test_record_bar_upsert(self):
        capture.record_bar(
            symbol="MSFT",
            ts=1_700_000_060.0,
            open_=400.0,
            high=401.0,
            low=399.0,
            close=400.5,
            volume=1_000,
            timeframe="1m",
            session_date="2026-07-14",
        )
        capture.record_bar(
            symbol="MSFT",
            ts=1_700_000_060.0,
            open_=400.0,
            high=402.0,
            low=399.0,
            close=401.0,
            volume=1_500,
            timeframe="1m",
            session_date="2026-07-14",
        )
        conn = archive_db.get_connection()
        try:
            rows = conn.execute("SELECT high, close, volume FROM bars_1m").fetchall()
        finally:
            conn.close()
        assert len(rows) == 1
        assert rows[0]["high"] == 402.0
        assert rows[0]["close"] == 401.0
        assert rows[0]["volume"] == 1500
        assert capture.get_counter(ARCHIVE_COUNTER_BARS_1M) == 2

    def test_record_gap_and_incomplete_window(self):
        capture.record_gap(
            stream=ARCHIVE_STREAM_TAPE,
            symbol="NVDA",
            start_ts=100.0,
            end_ts=200.0,
            reason="queue_drop",
            session_date="2026-07-14",
        )
        capture.mark_incomplete_window(
            stream=ARCHIVE_STREAM_TAPE,
            symbol="NVDA",
            start_ts=100.0,
            end_ts=200.0,
            note="session killed mid-stream",
            session_date="2026-07-14",
        )
        assert capture.get_counter(ARCHIVE_COUNTER_GAPS) == 1
        assert capture.get_counter(ARCHIVE_COUNTER_INCOMPLETE_WINDOWS) == 1
        conn = archive_db.get_connection()
        try:
            g = conn.execute("SELECT reason FROM capture_gaps").fetchone()
            w = conn.execute("SELECT note FROM incomplete_windows").fetchone()
        finally:
            conn.close()
        assert g["reason"] == "queue_drop"
        assert "mid-stream" in w["note"]

    def test_record_l2_snapshot_stub(self):
        capture.record_l2_snapshot(
            symbol="TSLA",
            ts=time.time(),
            bids=[{"price": 250.0, "size": 100}],
            asks=[{"price": 250.1, "size": 50}],
            session_date="2026-07-14",
        )
        assert capture.l2_stub_count() == 1
        assert capture.get_counter(ARCHIVE_COUNTER_L2_SNAPSHOTS) == 1

    def test_bump_counter_accumulates(self):
        capture.bump_counter("custom_test", 3)
        capture.bump_counter("custom_test", 2)
        assert capture.get_counter("custom_test") == 5


class TestTapeStreamArchiveHook:
    def test_on_tape_update_calls_record_tape_print(self, monkeypatch):
        import asyncio
        from types import SimpleNamespace

        import ibkr.tape_stream as tape

        calls: list[dict] = []

        def _fake_record(**kwargs):
            calls.append(kwargs)

        monkeypatch.setattr(capture, "record_tape_print", _fake_record)
        # Force the import path inside tape_stream to hit our patched function.
        import archive.capture as cap_mod
        monkeypatch.setattr(cap_mod, "record_tape_print", _fake_record)

        q: asyncio.Queue = asyncio.Queue()
        monkeypatch.setitem(tape._queues, "CNEY", q)
        monkeypatch.setattr(
            tape._depth,
            "current_book",
            lambda _sym: {
                "bids": [{"price": 0.73, "size": 100}],
                "asks": [{"price": 0.75, "size": 100}],
            },
        )
        ticks = [
            SimpleNamespace(
                time=None, price=0.74, size=100, exchange="ISLAND", specialConditions="",
            ),
        ]
        class _FakeTicker:
            def __init__(self, ticks_):
                self.tickByTicks = list(ticks_)
                self.updateEvent = SimpleNamespace()

        tape._on_tape_update(_FakeTicker(ticks), "CNEY")
        assert q.qsize() == 1
        assert len(calls) == 1
        assert calls[0]["symbol"] == "CNEY"
        assert calls[0]["price"] == 0.74
        assert calls[0]["source"] == ARCHIVE_SOURCE_IBKR
