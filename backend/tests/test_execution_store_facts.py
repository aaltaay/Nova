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


_NOVA_PLACED = "2026-09-16T18:04:12.123456Z"


def _acked_presubmitted_place(*, order_id: int = 116071, perm_id: int = 888777) -> str:
    from execution.nova_placed import persist_nova_placed_at

    execution_id, is_new = store.reserve(
        idempotency_key=f"place-{order_id}",
        operation="place",
        source="manual",
        symbol="ZTG",
        received_ns=1,
        payload={
            "qty": 1,
            "sent_qty": 1.0,
            "side": "BUY",
            "order_type": "LMT",
            "requested_price": 1.76,
        },
    )
    assert is_new is True
    store.update_stages(
        execution_id,
        order_id=order_id,
        status="acked",
        broker_status="PreSubmitted",
        broker_ack_ns=11,
    )
    persist_nova_placed_at(execution_id, _NOVA_PLACED)
    facts.record_broker_facts(execution_id, perm_id=perm_id)
    return execution_id


def test_mark_place_cancelled_closes_presubmitted_place_not_cancel_row():
    place_id = _acked_presubmitted_place()
    cancel_id, _ = store.reserve(
        idempotency_key="cancel-116071",
        operation="cancel",
        source="manual",
        symbol="ZTG",
        received_ns=2,
        payload={},
    )
    store.update_stages(
        cancel_id,
        order_id=116071,
        status="acked",
        broker_status="Cancelled",
        broker_ack_ns=22,
    )
    assert facts.list_session_placed(since_ts=0, limit=50) == []
    overlay_ids = [r["id"] for r in facts.list_session_place_overlay(since_ts=0)]
    assert place_id in overlay_ids

    marked = facts.mark_place_cancelled(order_id=116071, perm_id=888777)
    assert marked == place_id
    place = store.get_by_id(place_id)
    cancel = store.get_by_id(cancel_id)
    assert place["broker_status"] == "Cancelled"
    assert place["status"] == "acked"
    assert place["payload"]["nova_placed_at"] == _NOVA_PLACED
    assert cancel["operation"] == "cancel"
    assert cancel["broker_status"] == "Cancelled"
    rows = facts.list_session_placed(since_ts=0, limit=50)
    assert [r["id"] for r in rows] == [place_id]


def test_mark_place_cancelled_does_not_overwrite_fill():
    execution_id, _ = store.reserve(
        idempotency_key="filled-keep",
        operation="place",
        source="manual",
        symbol="SPCX",
        received_ns=1,
        payload={"qty": 1, "sent_qty": 1.0, "side": "BUY"},
    )
    store.update_stages(
        execution_id,
        order_id=115728,
        status="filled",
        broker_status="Filled",
    )
    facts.record_broker_facts(execution_id, perm_id=777001, filled_qty=1.0)
    assert facts.mark_place_cancelled(order_id=115728, perm_id=777001) is None
    row = store.get_by_id(execution_id)
    assert row["broker_status"] == "Filled"
    assert row["status"] == "filled"


def test_mark_place_cancelled_leaves_a_row_whose_fill_qty_is_unreadable():
    """An unreadable filled_qty cannot prove "no fill", so the cancel mark must
    not overwrite the row (it used to fall through as if the qty were 0)."""
    execution_id, _ = store.reserve(
        idempotency_key="garbled-qty",
        operation="place",
        source="manual",
        symbol="SPCX",
        received_ns=1,
        payload={"qty": 1, "sent_qty": 1.0, "side": "BUY"},
    )
    store.update_stages(execution_id, order_id=115729, status="sent", broker_status="Submitted")
    conn = store.get_connection()
    try:
        conn.execute("UPDATE executions SET filled_qty = 'garbled' WHERE id = ?", (execution_id,))
        conn.commit()
    finally:
        conn.close()
    assert facts.mark_place_cancelled(order_id=115729) is None
    assert store.get_by_id(execution_id)["broker_status"] == "Submitted"


def test_live_presubmitted_place_plus_ib_cancel_overlay_uses_nova_placed():
    """Windows paper: place stays PreSubmitted; IB cancel is order_id=0 + perm_id."""
    from execution.closed_blotter import overlay_closed_orders

    place_id = _acked_presubmitted_place()
    cancel_id, _ = store.reserve(
        idempotency_key="cancel-live-116071",
        operation="cancel",
        source="manual",
        symbol="ZTG",
        received_ns=2,
        payload={},
    )
    store.update_stages(
        cancel_id,
        order_id=116071,
        status="acked",
        broker_status="Cancelled",
    )
    ib = {
        "order_id": 0,
        "symbol": "ZTG",
        "side": "BUY",
        "qty": 1,
        "filled_qty": 0.0,
        "remaining_qty": 1.0,
        "order_type": "LMT",
        "limit_price": 1.76,
        "stop_price": None,
        "avg_fill_price": None,
        "outside_rth": False,
        "status": "Cancelled",
        "submitted_at": None,
        "updated_at": None,
        "filled_at": None,
        "held_until": None,
        "perm_id": 888777,
    }
    out = overlay_closed_orders(
        [ib],
        ledger_rows=facts.list_session_place_overlay(since_ts=0, limit=50),
        limit=50,
    )
    assert len(out) == 1
    assert out[0]["source"] == "nova"
    assert out[0]["execution_id"] == place_id
    assert out[0]["submitted_at"] == _NOVA_PLACED
    assert out[0]["filled_at"] is None
    assert out[0]["status"] == "Cancelled"
    assert out[0]["order_id"] == 116071
    place = store.get_by_id(place_id)
    assert place["broker_status"] == "PreSubmitted"
    assert place["payload"]["nova_placed_at"] == _NOVA_PLACED


def test_mark_place_cancelled_crosses_prior_boot_id():
    """Restart mid-cancel: place row is a previous boot_id."""
    place_id = _acked_presubmitted_place()
    conn = store.get_connection()
    try:
        conn.execute(
            "UPDATE executions SET boot_id = 'previous-boot' WHERE id = ?",
            (place_id,),
        )
        conn.commit()
    finally:
        conn.close()
    marked = facts.mark_place_cancelled(order_id=116071, perm_id=888777)
    assert marked == place_id
    row = store.get_by_id(place_id)
    assert row["boot_id"] == "previous-boot"
    assert row["broker_status"] == "Cancelled"
    assert row["payload"]["nova_placed_at"] == _NOVA_PLACED
