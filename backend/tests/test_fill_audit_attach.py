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


def test_imcc_ledger_clocks_do_not_publish_four_hours():
    remember_fill_audit(
        {"order_id": 106416, "level": "ok", "reason": "filled"},
        nova_placed_at="2026-09-18T14:06:06.963023Z",
    )
    row = _order(
        order_id=106416,
        perm_id=5001,
        symbol="IMCC",
        side="SELL",
        submitted_at="2026-09-18T14:06:06.962023Z",
        filled_at="2026-09-18T18:06:10Z",
        updated_at="2026-09-18T18:06:10Z",
    )
    out = attach_fill_audit([row], ledger_rows=[])
    audit = out[0]["fill_audit"]
    assert audit is not None
    assert audit["place_to_fill_ms"] == 3037
    assert audit["place_to_fill_ms"] < 10_000
    assert audit["place_to_submit_ms"] == -1


def test_imcc_second_resolution_ledger_still_refuses_four_hours():
    """created_ts loses micros -- still must not publish ~14400s as ok."""
    placed_ts = datetime(2026, 9, 18, 14, 6, 6, tzinfo=timezone.utc).timestamp()
    led = {
        "order_id": 106416,
        "perm_id": 5001,
        "created_ts": placed_ts,
        "operation": "place",
        "status": "filled",
    }
    row = _order(
        order_id=106416,
        perm_id=5001,
        symbol="IMCC",
        side="SELL",
        submitted_at="2026-09-18T14:06:06.962023Z",
        filled_at="2026-09-18T18:06:10Z",
        updated_at="2026-09-18T18:06:10Z",
    )
    out = attach_fill_audit([row], ledger_rows=[led])
    audit = out[0]["fill_audit"]
    assert audit is not None
    assert audit["place_to_fill_ms"] is not None
    assert audit["place_to_fill_ms"] < 10_000


def test_stored_leftover_four_hour_row_is_corrected():
    pub = public_fill_audit(
        {
            "place_to_submit_ms": -1,
            "place_to_fill_ms": 14_403_037,
            "place_to_terminal_ms": None,
            "level": "ok",
            "reason": "filled",
            "type": "MKT",
        },
    )
    assert pub is not None
    assert pub["place_to_fill_ms"] == 3037
    assert pub["level"] == "warn"
    assert pub["reason"] == "mkt_rth_slow"


def test_lmt_timezone_shaped_stored_row_is_invalid_not_four_hours():
    pub = public_fill_audit(
        {
            "place_to_submit_ms": -1,
            "place_to_fill_ms": 14_403_037,
            "place_to_terminal_ms": None,
            "level": "ok",
            "reason": "filled",
            "type": "LMT",
        },
    )
    assert pub is not None
    assert pub["place_to_fill_ms"] is None
    assert pub["reason"] == "timezone_shaped_clock"
    assert pub["level"] == "warn"


def test_imcc_buy_106411_ledger_publishes_clock_skew():
    remember_fill_audit(
        {"order_id": 106411, "level": "ok", "reason": "filled"},
        nova_placed_at="2026-09-18T14:05:58.296Z",
    )
    row = _order(
        order_id=106411,
        perm_id=5002,
        symbol="IMCC",
        side="BUY",
        submitted_at="2026-09-18T14:05:58Z",
        filled_at="2026-09-18T14:05:58Z",
        updated_at="2026-09-18T14:05:58Z",
    )
    out = attach_fill_audit([row], ledger_rows=[])
    audit = out[0]["fill_audit"]
    assert audit is not None
    assert audit["place_to_fill_ms"] == -296
    assert audit["place_to_submit_ms"] == -296
    assert audit["face_ms"] is None
    assert audit["reason"] == "clock_skew"
    assert audit["level"] == "ok"


def test_stored_negative_fill_is_clock_skew_not_ok_filled():
    pub = public_fill_audit(
        {
            "place_to_submit_ms": -296,
            "place_to_fill_ms": -296,
            "place_to_terminal_ms": None,
            "level": "ok",
            "reason": "filled",
            "type": "MKT",
        },
    )
    assert pub is not None
    assert pub["place_to_fill_ms"] == -296
    assert pub["face_ms"] is None
    assert pub["reason"] == "clock_skew"
    assert pub["level"] == "ok"


def test_imcc_sell_3037_stays_warn():
    pub = public_fill_audit(
        {
            "place_to_submit_ms": -1,
            "place_to_fill_ms": 3037,
            "place_to_terminal_ms": None,
            "level": "warn",
            "reason": "mkt_rth_slow",
            "type": "MKT",
        },
    )
    assert pub is not None
    assert pub["place_to_fill_ms"] == 3037
    assert pub["face_ms"] == 3037
    assert pub["reason"] == "mkt_rth_slow"
    assert pub["level"] == "warn"


def test_order_109741_four_hour_fill_is_not_zero_ms():
    """Desk F row: Time Placed 11:02:48.551 ET, Time Filled 15:02:48 ET, Latency 0ms.

    created_ts is second-rounded UTC. ib_async already converted naive UTC
    execution.time through the Eastern host TZ, so filled_at is +4h Zulu.
    """
    placed_ts = datetime(2026, 9, 18, 15, 2, 48, tzinfo=timezone.utc).timestamp()
    led = {
        "order_id": 109741,
        "perm_id": 6001,
        "created_ts": placed_ts,
        "operation": "place",
        "status": "filled",
    }
    row = _order(
        order_id=109741,
        perm_id=6001,
        symbol="TEST",
        side="BUY",
        submitted_at="2026-09-18T15:02:48.551Z",
        filled_at="2026-09-18T19:02:48Z",
        updated_at="2026-09-18T19:02:48Z",
    )
    out = attach_fill_audit([row], ledger_rows=[led])
    assert out[0]["filled_at"] == "2026-09-18T15:02:48Z"
    assert not str(out[0]["filled_at"]).startswith("2026-09-18T19:02:48")
    audit = out[0]["fill_audit"]
    assert audit is None or audit.get("face_ms") in (None,)
    if audit is not None:
        assert audit.get("face_ms") != 0
        assert audit.get("place_to_fill_ms") != 0


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
