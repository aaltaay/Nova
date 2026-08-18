"""Archive writes must not touch SQLite on the IB event loop (ADR 010).

Regression for the 2026-08-18 IB-loop wedge: ``record_tape_print`` /
``record_l1_tick`` ran a full connect + PRAGMA + INSERT + commit (twice each,
counting the integrity counter) inside the ``ib_async`` socket callback, so a
single high-print runner starved ``reqMktData`` for the whole desk
(``ib_loop_lag_ms`` 45,094ms while the HTTP loop stayed at 11ms).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive.capture as capture
import archive.db as archive_db
import archive.write_queue as wq
from constants import (
    ARCHIVE_COUNTER_BARS_1M,
    ARCHIVE_COUNTER_L1_TICKS,
    ARCHIVE_COUNTER_TAPE_DROPPED,
    ARCHIVE_COUNTER_TAPE_RECEIVED,
    ARCHIVE_SOURCE_IBKR,
)


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    wq.reset_for_tests()
    yield
    wq.reset_for_tests()


def _forbid_connections(monkeypatch) -> list[str]:
    """Trip on any SQLite connection opened while producers are enqueueing."""
    opened: list[str] = []
    real = archive_db.get_connection

    def _spy():
        opened.append("get_connection")
        return real()

    monkeypatch.setattr(archive_db, "get_connection", _spy)
    return opened


def _tape_count() -> int:
    conn = archive_db.get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM tape_ibkr").fetchone()[0]
    finally:
        conn.close()


class TestProducerNeverTouchesSqlite:
    def test_enqueue_tape_print_opens_no_connection(self, monkeypatch):
        opened = _forbid_connections(monkeypatch)
        for i in range(500):
            wq.enqueue_tape_print(
                symbol="pfsa",
                ts=1_700_000_000.0 + i,
                price=16.5,
                size=100,
                exchange="ISLAND",
                side="ask",
                source=ARCHIVE_SOURCE_IBKR,
            )
        assert opened == [], "producer hit SQLite on the IB loop"
        assert wq.pending() == 500

    def test_enqueue_l1_tick_opens_no_connection(self, monkeypatch):
        opened = _forbid_connections(monkeypatch)
        for i in range(250):
            wq.enqueue_l1_tick(
                symbol="aixc", ts=1_700_000_000.0 + i, price=1.34, volume=10.0,
            )
        assert opened == []
        assert wq.pending() == 250

    def test_l1_tick_rejects_epoch_zero(self):
        wq.enqueue_l1_tick(symbol="BAD", ts=0.0, price=1.0)
        assert wq.pending() == 0


class TestDrainWritesOneBatch:
    def test_drain_persists_rows_and_bumps_counters_once(self, monkeypatch):
        for i in range(50):
            wq.enqueue_tape_print(
                symbol="pfsa", ts=1_700_000_000.0 + i, price=16.5, size=100,
            )
        for i in range(20):
            wq.enqueue_l1_tick(symbol="pfsa", ts=1_700_000_000.0 + i, price=16.5)

        opened = _forbid_connections(monkeypatch)
        result = wq.drain_once()

        assert result["tape"] == 50
        assert result["l1"] == 20
        # 50 prints + 20 ticks used to cost 140 connections; a batch costs one.
        assert len(opened) == 1
        assert wq.pending() == 0
        assert _tape_count() == 50
        assert capture.get_counter(ARCHIVE_COUNTER_TAPE_RECEIVED) == 50
        assert capture.get_counter(ARCHIVE_COUNTER_L1_TICKS) == 20

    def test_rows_survive_round_trip_with_expected_shape(self):
        wq.enqueue_tape_print(
            symbol="pfsa", ts=1_700_000_000.0, price=16.72, size=250,
            exchange="ISLAND", side="ask", bid=16.71, ask=16.73,
            source=ARCHIVE_SOURCE_IBKR, session_date="2026-08-18",
        )
        wq.drain_once()
        conn = archive_db.get_connection()
        try:
            row = conn.execute(
                "SELECT symbol, price, size, side, source, session_date FROM tape_ibkr",
            ).fetchone()
        finally:
            conn.close()
        assert row["symbol"] == "PFSA"
        assert row["price"] == 16.72
        assert row["size"] == 250
        assert row["side"] == "ask"
        assert row["source"] == ARCHIVE_SOURCE_IBKR
        assert row["session_date"] == "2026-08-18"

    def test_bars_drain_with_upsert(self):
        for close in (10.0, 11.0):
            wq.enqueue_bar(
                symbol="pfsa", ts=1_700_000_000.0, open_=9.0, high=12.0,
                low=8.0, close=close, volume=100.0, timeframe="1m",
            )
        wq.drain_once()
        conn = archive_db.get_connection()
        try:
            rows = conn.execute("SELECT close FROM bars_1m").fetchall()
        finally:
            conn.close()
        assert len(rows) == 1, "same minute must upsert, not duplicate"
        assert rows[0]["close"] == 11.0
        assert capture.get_counter(ARCHIVE_COUNTER_BARS_1M) == 2

    def test_empty_drain_opens_no_connection(self, monkeypatch):
        opened = _forbid_connections(monkeypatch)
        assert wq.drain_once()["tape"] == 0
        assert opened == []

    def test_flush_blocking_drains_more_than_one_batch(self, monkeypatch):
        monkeypatch.setattr(wq, "ARCHIVE_WRITE_BATCH_MAX", 10)
        for i in range(35):
            wq.enqueue_tape_print(
                symbol="pfsa", ts=1_700_000_000.0 + i, price=16.5, size=1,
            )
        total = wq.flush_blocking()
        assert total["tape"] == 35
        assert wq.pending() == 0
        assert _tape_count() == 35


class TestBoundedQueue:
    def test_overflow_drops_oldest_and_counts_it(self, monkeypatch):
        monkeypatch.setattr(wq, "ARCHIVE_WRITE_QUEUE_MAX", 10)
        for i in range(14):
            wq.enqueue_tape_print(
                symbol="pfsa", ts=1_700_000_000.0 + i, price=float(i), size=1,
            )
        assert wq.pending() == 10
        assert wq.stats()["dropped_pending"] == 4

        wq.drain_once()
        # Loss is visible, not silent, and the newest prints are the survivors.
        assert capture.get_counter(ARCHIVE_COUNTER_TAPE_DROPPED) == 4
        conn = archive_db.get_connection()
        try:
            prices = [r["price"] for r in conn.execute(
                "SELECT price FROM tape_ibkr ORDER BY price",
            ).fetchall()]
        finally:
            conn.close()
        assert prices == [float(i) for i in range(4, 14)]


class TestIbLoopCallersUseTheQueue:
    """The wedge came from the *call sites*, so pin them, not just the module."""

    def test_tape_stream_enqueues_instead_of_writing(self, monkeypatch):
        import asyncio
        from types import SimpleNamespace

        import ibkr.tape_stream as tape

        opened = _forbid_connections(monkeypatch)
        monkeypatch.setattr(
            capture, "record_tape_print",
            lambda **_kw: pytest.fail("blocking SQLite write on the IB loop"),
        )

        q: asyncio.Queue = asyncio.Queue()
        monkeypatch.setitem(tape._queues, "CNEY", q)
        monkeypatch.setattr(
            tape._depth, "current_book",
            lambda _sym: {
                "bids": [{"price": 0.73, "size": 100}],
                "asks": [{"price": 0.75, "size": 100}],
            },
        )

        class _FakeTicker:
            def __init__(self) -> None:
                self.tickByTicks = [SimpleNamespace(
                    time=None, price=0.74, size=100,
                    exchange="ISLAND", specialConditions="",
                )]
                self.updateEvent = SimpleNamespace()

        tape._on_tape_update(_FakeTicker(), "CNEY")

        assert q.qsize() == 1, "live tape WS must still get the print"
        assert opened == [], "IB loop opened a SQLite connection"
        assert wq.pending() >= 1, "tape print was not queued for the writer"

    def test_l1_archive_hook_enqueues_instead_of_writing(self, monkeypatch):
        import ibkr_bridge

        opened = _forbid_connections(monkeypatch)
        monkeypatch.setattr(
            capture, "record_l1_tick",
            lambda **_kw: pytest.fail("blocking SQLite write on the IB loop"),
        )
        ibkr_bridge._archive_l1_tick("PFSA", 16.72, 1_700_000_000.0, volume=10.0)
        assert opened == []
        assert wq.pending() == 1
