"""Each thread keeps one execution-ledger connection (2026-10-05, Paper order latency).

A Paper order opened and closed the ledger about 20 times; on the desk PC that was
~100 ms of a ~150 ms reply. These pin what the kept connection must never change:
a ``close()`` still ends the caller's transaction, a use inside a use never shares
the outer one's transaction, threads never share a connection, and a replaced or
moved ledger file is opened again.
"""
from __future__ import annotations

import sqlite3
import threading

import pytest

from execution import ledger_conn, store


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "cache_dir", lambda: tmp_path)
    store.init_db()
    yield tmp_path
    ledger_conn.close_all()


def _count(path) -> int:
    with sqlite3.connect(path) as conn:
        return conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]


def _insert(conn: sqlite3.Connection, key: str) -> None:
    conn.execute(
        "INSERT INTO executions (id, idempotency_key, operation, source, status, boot_id,"
        " received_ns, created_ts, updated_ts) VALUES (?, ?, 'place', 'manual', 'reserved', 'b', 1, 0, 0)",
        (key, key),
    )


def test_a_thread_reuses_its_connection(ledger) -> None:
    first = store.get_connection()
    first.close()
    second = store.get_connection()
    second.close()
    assert first is second
    assert second.execute("SELECT 1").fetchone()[0] == 1  # still open after close()


def test_close_rolls_back_what_was_not_committed(ledger) -> None:
    conn = store.get_connection()
    _insert(conn, "never-committed")
    conn.close()
    assert _count(store._db_path()) == 0
    conn = store.get_connection()
    try:
        _insert(conn, "committed")
        conn.commit()
    finally:
        conn.close()
    assert _count(store._db_path()) == 1


def test_a_use_inside_a_use_has_its_own_connection(ledger) -> None:
    outer = store.get_connection()
    try:
        _insert(outer, "outer")  # open transaction on the outer connection
        inner = store.get_connection()
        assert inner is not outer
        inner.close()  # must not roll back (or commit) the outer write
        assert outer.in_transaction
        outer.commit()
    finally:
        outer.close()
    assert _count(store._db_path()) == 1
    again = store.get_connection()
    again.close()
    assert again is outer  # the kept one is handed out again once free


def test_threads_never_share_a_connection(ledger) -> None:
    mine = store.get_connection()
    mine.close()
    theirs: list[sqlite3.Connection] = []

    def other() -> None:
        conn = store.get_connection()
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        theirs.append(conn)

    worker = threading.Thread(target=other)
    worker.start()
    worker.join()
    assert theirs and theirs[0] is not mine


def test_another_ledger_file_gets_another_connection(ledger, tmp_path, monkeypatch) -> None:
    first = store.get_connection()
    first.close()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr(store, "cache_dir", lambda: elsewhere)
    store.init_db()
    second = store.get_connection()
    second.close()
    assert second is not first
    with pytest.raises(sqlite3.ProgrammingError):
        first.execute("SELECT 1")  # the old one was closed for real


def test_a_replaced_file_is_opened_again(ledger, monkeypatch) -> None:
    first = store.get_connection()
    first.close()
    real = ledger_conn._identity
    monkeypatch.setattr(ledger_conn, "_identity", lambda path: (real(path) or (0, 0))[:1] + (-1,))
    second = store.get_connection()
    second.close()
    assert second is not first


def test_close_all_from_another_thread_leaves_no_dead_connection(ledger) -> None:
    mine = store.get_connection()
    mine.close()
    worker = threading.Thread(target=ledger_conn.close_all)
    worker.start()
    worker.join()
    again = store.get_connection()
    try:
        assert again is not mine
        assert again.execute("SELECT 1").fetchone()[0] == 1
    finally:
        again.close()


def test_a_connection_that_cannot_roll_back_is_dropped(ledger, monkeypatch) -> None:
    conn = store.get_connection()
    _insert(conn, "pending")

    def broken(self) -> None:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(ledger_conn.KeptConnection, "rollback", broken)
    conn.close()
    monkeypatch.undo()
    monkeypatch.setattr(store, "cache_dir", lambda: ledger)
    fresh = store.get_connection()
    try:
        assert fresh is not conn
        assert fresh.execute("SELECT COUNT(*) FROM executions").fetchone()[0] == 0
    finally:
        fresh.close()
