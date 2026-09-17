"""Broker facts (permId, fill qty) persist on the execution ledger."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import execution.store as store
import execution.store_facts as facts
import execution.telemetry as telemetry


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    store.init_db()
    telemetry.reset_for_tests()
    yield
    telemetry.reset_for_tests()


def test_init_db_adds_broker_fact_columns(tmp_path, monkeypatch):
    import sqlite3
    from constants import EXECUTION_LEDGER_DB_FILENAME

    conn = sqlite3.connect(tmp_path / EXECUTION_LEDGER_DB_FILENAME)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(executions)")}
    conn.close()
    assert "perm_id" in columns
    assert "filled_qty" in columns
    assert "avg_fill_price" in columns
    assert "commission" in columns


def test_record_broker_facts_and_lookup_symbol():
    execution_id, is_new = store.reserve(
        idempotency_key="facts-1",
        operation="place",
        source="manual",
        symbol="IVF",
        received_ns=1,
        payload={"qty": 1},
    )
    assert is_new is True
    store.update_stages(execution_id, order_id=19112, status="sent")
    assert facts.record_broker_facts(
        execution_id,
        perm_id=888001,
        filled_qty=1.0,
        avg_fill_price=4.25,
    )
    row = store.get_by_id(execution_id)
    assert row["perm_id"] == 888001
    assert row["filled_qty"] == 1.0
    assert row["avg_fill_price"] == 4.25
    assert facts.lookup_symbol_for_order_id(19112) == "IVF"


def test_list_session_placed_skips_benchmark():
    store.reserve(
        idempotency_key="bench-skip",
        operation="place",
        source="benchmark",
        symbol="AAPL",
        received_ns=1,
    )
    manual_id, _ = store.reserve(
        idempotency_key="manual-keep",
        operation="place",
        source="manual",
        symbol="IVF",
        received_ns=2,
    )
    store.update_stages(manual_id, status="filled", order_id=19112)
    rows = facts.list_session_placed(since_ts=0, limit=50)
    symbols = [r["symbol"] for r in rows]
    assert "IVF" in symbols
    assert "AAPL" not in symbols


def test_init_db_migrates_pre_facts_schema(tmp_path, monkeypatch):
    """Live ledgers created before perm_id must ALTER, then index."""
    import sqlite3
    from constants import EXECUTION_LEDGER_DB_FILENAME

    db_path = tmp_path / EXECUTION_LEDGER_DB_FILENAME
    db_path.unlink(missing_ok=True)
    pre_facts = store._SCHEMA.replace(
        "    payload_json TEXT NOT NULL DEFAULT '{}',\n"
        "    perm_id INTEGER,\n"
        "    filled_qty REAL,\n"
        "    avg_fill_price REAL,\n"
        "    commission REAL\n",
        "    payload_json TEXT NOT NULL DEFAULT '{}'\n",
    )
    with sqlite3.connect(db_path) as conn:
        conn.executescript(pre_facts)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(executions)")}
    assert "perm_id" not in columns
    assert "commission" not in columns
    monkeypatch.setattr(store, "cache_dir", lambda: tmp_path)
    store.init_db()
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(executions)")}
        indexes = {
            row[1] for row in conn.execute("PRAGMA index_list(executions)")
        }
    assert "perm_id" in columns
    assert "filled_qty" in columns
    assert "avg_fill_price" in columns
    assert "commission" in columns
    assert "idx_exec_perm_id" in indexes


def test_note_filled_writes_perm_id_and_qty():
    execution_id, _ = store.reserve(
        idempotency_key="fill-facts",
        operation="place",
        source="manual",
        symbol="IVF",
        received_ns=1,
        payload={},
    )
    store.update_stages(execution_id, order_id=19085, status="sent")
    watch = telemetry.watch_order(19085, execution_id)
    watch.note_status(
        "Filled",
        filled=1.0,
        remaining=0.0,
        average_fill_price=3.5,
        perm_id=777002,
    )
    # Ledger fill qty/avg come from execDetails, not orderStatus.
    watch.note_execution(
        avg_price=3.5,
        price=3.5,
        shares=1.0,
        cumulative_shares=1.0,
        perm_id=777002,
    )
    watch.note_filled()
    row = store.get_by_id(execution_id)
    assert row["status"] == "filled"
    assert row["perm_id"] == 777002
    assert row["filled_qty"] == 1.0
    assert row["avg_fill_price"] == 3.5
