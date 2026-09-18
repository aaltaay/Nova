"""Orders Today fill-audit join -- fixtures only. No live IBKR."""
from __future__ import annotations

from datetime import datetime, timezone

from execution.fill_audit import (
    classify_fill_audit,
    remember_fill_audit,
    reset_fill_audit_store_for_testing,
)
from execution.fill_audit_attach import attach_fill_audit, public_fill_audit


def setup_function() -> None:
    reset_fill_audit_store_for_testing()


def _ok_row(**kw) -> dict:
    row = classify_fill_audit(
        order_id=115728,
        symbol="SPCX",
        side="BUY",
        order_type="MKT",
        mode="paper",
        status="Filled",
        nova_placed_at="2026-09-16T14:05:00.000Z",
        submitted_at="2026-09-16T14:05:00.012Z",
        filled_at="2026-09-16T14:05:00.180Z",
        terminal_at="2026-09-16T14:05:00.180Z",
        has_fill=True,
        rth=True,
        status_history=("PendingSubmit", "PreSubmitted", "Filled"),
    )
    row.update(kw)
    return row


def _order(**kw) -> dict:
    row = {
        "order_id": 115728,
        "perm_id": 4001,
        "symbol": "SPCX",
        "side": "BUY",
        "qty": 1,
        "filled_qty": 1.0,
        "remaining_qty": 0.0,
        "order_type": "MKT",
        "outside_rth": False,
        "status": "Filled",
        "submitted_at": "2026-09-16T14:05:00.012Z",
        "updated_at": "2026-09-16T14:05:00.180Z",
        "filled_at": "2026-09-16T14:05:00.180Z",
    }
    row.update(kw)
    return row


def test_missing_audit_is_null_never_invented():
    out = attach_fill_audit([_order()], ledger_rows=[])
    assert out[0]["fill_audit"] is None
    assert out[0]["order_id"] == 115728


def test_remembered_audit_joins_by_order_id():
    remember_fill_audit(
        _ok_row(),
        nova_placed_at="2026-09-16T14:05:00.000Z",
    )
    out = attach_fill_audit([_order()], ledger_rows=[])
    audit = out[0]["fill_audit"]
    assert audit["place_to_submit_ms"] == 12
    assert audit["place_to_fill_ms"] == 180
    assert audit["place_to_terminal_ms"] is None
    assert audit["level"] == "ok"


def test_ledger_clocks_recompute_warn_mkt_rth():
    placed_ts = datetime(2026, 9, 16, 14, 5, 0, tzinfo=timezone.utc).timestamp()
    led = {
        "order_id": 115728,
        "perm_id": 4001,
        "created_ts": placed_ts,
        "operation": "place",
        "status": "filled",
    }
    row = _order(
        submitted_at="2026-09-16T14:05:00.100Z",
        filled_at="2026-09-16T14:05:02.100Z",
        updated_at="2026-09-16T14:05:02.100Z",
    )
    out = attach_fill_audit([row], ledger_rows=[led])
    audit = out[0]["fill_audit"]
    assert audit["place_to_fill_ms"] == 2100
    assert audit["level"] == "warn"
    assert audit["place_to_submit_ms"] == 100


def test_collapsed_ledger_clocks_stay_blank():
    """Same created_ts used as submitted + filled is not a measured latency."""
    iso = "2026-09-16T14:05:00.000Z"
    placed_ts = datetime(2026, 9, 16, 14, 5, 0, tzinfo=timezone.utc).timestamp()
    led = {
        "order_id": 99,
        "created_ts": placed_ts,
        "operation": "place",
        "status": "filled",
    }
    row = _order(
        order_id=99,
        perm_id=None,
        submitted_at=iso,
        filled_at=iso,
        updated_at=iso,
    )
    out = attach_fill_audit([row], ledger_rows=[led])
    assert out[0]["fill_audit"] is None


def test_working_without_fill_does_not_show_ack_as_terminal():
    remember_fill_audit(
        classify_fill_audit(
            order_id=7,
            symbol="AAPL",
            side="BUY",
            order_type="MKT",
            mode="paper",
            status="Submitted",
            nova_placed_at="2026-09-16T14:05:00.000Z",
            submitted_at="2026-09-16T14:05:00.012Z",
            filled_at=None,
            terminal_at="2026-09-16T14:05:00.050Z",
            has_fill=False,
            rth=True,
            status_history=("PendingSubmit", "Submitted"),
        ),
        nova_placed_at="2026-09-16T14:05:00.000Z",
    )
    row = _order(
        order_id=7,
        perm_id=None,
        filled_qty=0,
        remaining_qty=1,
        status="Submitted",
        filled_at=None,
        submitted_at="2026-09-16T14:05:00.012Z",
        updated_at="2026-09-16T14:05:00.050Z",
    )
    out = attach_fill_audit([row], ledger_rows=[])
    assert out[0]["fill_audit"] is None


def test_cancelled_uses_click_to_terminal():
    placed_ts = datetime(2026, 9, 16, 14, 5, 0, tzinfo=timezone.utc).timestamp()
    led = {
        "order_id": 8,
        "created_ts": placed_ts,
        "operation": "place",
        "status": "rejected",
        "broker_status": "Cancelled",
    }
    row = _order(
        order_id=8,
        perm_id=None,
        filled_qty=0,
        remaining_qty=0,
        status="Cancelled",
        filled_at=None,
        submitted_at="2026-09-16T14:05:00.020Z",
        updated_at="2026-09-16T14:05:03.000Z",
        order_type="LMT",
    )
    out = attach_fill_audit([row], ledger_rows=[led])
    audit = out[0]["fill_audit"]
    assert audit["place_to_fill_ms"] is None
    assert audit["place_to_terminal_ms"] == 3000
    assert audit["level"] == "ok"


def test_public_fill_audit_drops_empty_row():
    assert public_fill_audit({"order_id": 1, "level": "ok"}) is None
    assert public_fill_audit(None) is None


def test_placed_index_prefers_payload_nova_placed_at():
    from execution.fill_audit_attach import placed_index_from_ledger

    stamp = "2026-09-16T18:04:12.123456Z"
    led = {
        "order_id": 116071,
        "perm_id": 0,
        "created_ts": 1_000.0,
        "payload": {"nova_placed_at": stamp},
    }
    index = placed_index_from_ledger([led])
    assert index[("order", 116071)] == stamp
