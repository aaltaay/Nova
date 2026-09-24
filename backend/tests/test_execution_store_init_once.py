"""The ledger schema is ensured once per ledger file, not on every read (2026-09-23).

Every ledger read calls ``store.init_db``; re-running the schema script, the
column check and the evidence migrations each time was the performance
recorder's top HTTP-loop stall frame (account / positions polls, bot breakers).
"""
from __future__ import annotations

import sqlite3

from execution import evidence_store, store, store_facts


def _count_column_checks(monkeypatch) -> dict:
    calls = {"n": 0}
    real = store.ensure_executions_columns

    def counting(conn):
        calls["n"] += 1
        return real(conn)

    monkeypatch.setattr(store, "ensure_executions_columns", counting)
    return calls


def test_reads_ensure_the_schema_once(monkeypatch):
    calls = _count_column_checks(monkeypatch)

    store.init_db()
    store.init_db()
    evidence_store.init_db()
    store_facts.list_session_placed(since_ts=0.0)
    store_facts.session_commission_by_symbol(since_ts=0.0)

    assert calls["n"] == 1


def test_a_replaced_ledger_file_is_initialised_again(monkeypatch):
    calls = _count_column_checks(monkeypatch)
    store.init_db()
    path = store._db_path()
    path.unlink()

    store.init_db()

    with sqlite3.connect(path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"executions", "execution_fill_evidence"} <= tables
    assert calls["n"] == 2
