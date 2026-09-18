"""Orders (Today) must overlay the execution ledger on IB replay zeros."""
from __future__ import annotations

from execution.closed_blotter import overlay_closed_orders


def _ib(**kw) -> dict:
    row = {
        "order_id": 0,
        "symbol": "IVF",
        "side": "BUY",
        "qty": 0,
        "filled_qty": 0.0,
        "remaining_qty": 0.0,
        "order_type": "MKT",
        "limit_price": None,
        "stop_price": None,
        "avg_fill_price": None,
        "outside_rth": False,
        "status": "Filled",
        "submitted_at": "2026-08-17T13:56:49.000Z",
        "updated_at": "2026-08-17T13:56:49.000Z",
        "filled_at": "2026-08-17T13:56:49.000Z",
        "held_until": None,
        "perm_id": None,
    }
    row.update(kw)
    return row


def _ledger(**kw) -> dict:
    row = {
        "id": "e-ivf",
        "operation": "place",
        "source": "manual",
        "symbol": "IVF",
        "status": "filled",
        "order_id": 19112,
        "perm_id": None,
        "filled_qty": 1.0,
        "avg_fill_price": 4.25,
        "broker_status": "Filled",
        "created_ts": 1_755_451_009.0,
        "payload": {
            "qty": 1,
            "sent_qty": 1.0,
            "side": "BUY",
            "order_type": "MKT",
        },
    }
    row.update(kw)
    return row


def test_overlay_heals_ib_zero_id_and_qty_from_ledger():
    out = overlay_closed_orders(
        [_ib()],
        ledger_rows=[_ledger()],
        limit=50,
    )
    assert len(out) == 1
    row = out[0]
    assert row["order_id"] == 19112
    assert row["qty"] == 1.0
    assert row["filled_qty"] == 1.0
    assert row["avg_fill_price"] == 4.25
    assert row["source"] == "nova"
    assert row["remaining_qty"] == 0.0


def test_overlay_matches_nonzero_order_id():
    ib = _ib(order_id=72165, symbol="NOMA", qty=1, filled_qty=1.0)
    led = _ledger(
        id="e-noma",
        symbol="NOMA",
        order_id=72165,
        filled_qty=1.0,
        payload={"qty": 1, "sent_qty": 1.0, "side": "BUY"},
    )
    out = overlay_closed_orders([ib], ledger_rows=[led], limit=50)
    assert out[0]["order_id"] == 72165
    assert out[0]["source"] == "nova"


def test_overlay_matches_perm_id_when_session_id_is_zero():
    ib = _ib(order_id=0, perm_id=888001, qty=0, filled_qty=0)
    led = _ledger(perm_id=888001, order_id=19085, filled_qty=1.0)
    out = overlay_closed_orders([ib], ledger_rows=[led], limit=50)
    assert out[0]["order_id"] == 19085
    assert out[0]["perm_id"] == 888001
    assert out[0]["source"] == "nova"


def test_unmatched_ib_row_is_labeled_recovered():
    ib = _ib(order_id=55, symbol="AAPL", qty=100, filled_qty=100.0)
    out = overlay_closed_orders([ib], ledger_rows=[], limit=50)
    assert out[0]["source"] == "ib_recovered"
    assert out[0]["order_id"] == 55
    assert out[0]["qty"] == 100


def test_ledger_fill_with_no_ib_row_is_appended():
    out = overlay_closed_orders(
        [],
        ledger_rows=[_ledger()],
        limit=50,
    )
    assert len(out) == 1
    assert out[0]["order_id"] == 19112
    assert out[0]["symbol"] == "IVF"
    assert out[0]["source"] == "nova"
    assert out[0]["status"] == "Filled"


def test_benchmark_ledger_rows_are_not_appended():
    out = overlay_closed_orders(
        [],
        ledger_rows=[_ledger(source="benchmark")],
        limit=50,
    )
    assert out == []


def test_two_zero_ib_rows_match_two_ledger_fills():
    ib_rows = [
        _ib(submitted_at="2026-08-17T13:56:37.000Z"),
        _ib(submitted_at="2026-08-17T13:56:49.000Z"),
    ]
    ledger = [
        _ledger(id="a", order_id=19085, created_ts=1.0),
        _ledger(id="b", order_id=19112, created_ts=2.0),
    ]
    out = overlay_closed_orders(ib_rows, ledger_rows=ledger, limit=50)
    ids = sorted(int(r["order_id"]) for r in out)
    assert ids == [19085, 19112]
    assert all(r["source"] == "nova" for r in out)
    assert all(r["qty"] == 1.0 for r in out)


def test_inactive_ledger_row_does_not_invent_a_fill():
    """ZTG leftover -- sent_qty 1 + Inactive is Failed, not Filled 1 @ limit."""
    led = _ledger(
        id="e-ztg",
        symbol="ZTG",
        status="failed",
        order_id=116071,
        filled_qty=None,
        avg_fill_price=None,
        broker_status="Inactive",
        payload={
            "qty": 1,
            "sent_qty": 1.0,
            "side": "BUY",
            "order_type": "LMT",
            "requested_price": 1.76,
        },
    )
    out = overlay_closed_orders([], ledger_rows=[led], limit=50)
    assert len(out) == 1
    row = out[0]
    assert row["status"] == "Inactive"
    assert row["qty"] == 1.0
    assert row["filled_qty"] == 0.0
    assert row["avg_fill_price"] is None
    assert row["filled_at"] is None
    assert row["commission"] is None
    assert row["limit_price"] == 1.76


def test_ledger_commission_passes_through_on_real_fill():
    led = _ledger(commission=1.0)
    out = overlay_closed_orders([], ledger_rows=[led], limit=50)
    assert out[0]["commission"] == 1.0
    assert out[0]["filled_qty"] == 1.0


_NOVA_PLACED = "2026-09-16T18:04:12.123456Z"
_BROKER_SUBMIT = "2026-09-16T18:04:12.200000Z"
_BROKER_FILL = "2026-09-16T18:04:12.380000Z"


def _ztg_cancel_ib(**kw) -> dict:
    row = _ib(
        order_id=116071,
        symbol="ZTG",
        status="Cancelled",
        qty=1,
        filled_qty=0.0,
        remaining_qty=1.0,
        order_type="LMT",
        limit_price=1.76,
        submitted_at=None,
        updated_at=None,
        filled_at=None,
        avg_fill_price=None,
    )
    row.update(kw)
    return row


def _ztg_cancel_ledger(**kw) -> dict:
    row = _ledger(
        id="e-ztg-116071",
        symbol="ZTG",
        status="failed",
        order_id=116071,
        filled_qty=None,
        avg_fill_price=None,
        broker_status="Cancelled",
        created_ts=1_755_451_009.0,
        payload={
            "qty": 1,
            "sent_qty": 1.0,
            "side": "BUY",
            "order_type": "LMT",
            "requested_price": 1.76,
            "nova_placed_at": _NOVA_PLACED,
        },
    )
    row.update(kw)
    return row


def test_overlay_cancel_missing_broker_log_uses_persisted_nova_placed():
    """ZTG #116071: IB clocks null, Nova ledger row present -- Time Placed lives."""
    out = overlay_closed_orders(
        [_ztg_cancel_ib()],
        ledger_rows=[_ztg_cancel_ledger()],
        limit=50,
    )
    assert len(out) == 1
    row = out[0]
    assert row["source"] == "nova"
    assert row["execution_id"] == "e-ztg-116071"
    assert row["submitted_at"] == _NOVA_PLACED
    assert row["filled_at"] is None
    assert row["status"] == "Cancelled"


def test_overlay_prefers_broker_submit_over_ledger_stamp():
    out = overlay_closed_orders(
        [_ztg_cancel_ib(submitted_at=_BROKER_SUBMIT)],
        ledger_rows=[_ztg_cancel_ledger()],
        limit=50,
    )
    assert out[0]["submitted_at"] == _BROKER_SUBMIT
    assert out[0]["filled_at"] is None


def test_overlay_filled_keeps_broker_fill_clock():
    ib = _ib(
        order_id=115728,
        symbol="SPCX",
        qty=1,
        filled_qty=1.0,
        remaining_qty=0.0,
        submitted_at=_BROKER_SUBMIT,
        filled_at=_BROKER_FILL,
        updated_at=_BROKER_FILL,
    )
    led = _ledger(
        id="e-spcx",
        symbol="SPCX",
        order_id=115728,
        filled_qty=1.0,
        payload={
            "qty": 1,
            "sent_qty": 1.0,
            "side": "BUY",
            "order_type": "MKT",
            "nova_placed_at": _NOVA_PLACED,
        },
    )
    out = overlay_closed_orders([ib], ledger_rows=[led], limit=50)
    assert out[0]["submitted_at"] == _BROKER_SUBMIT
    assert out[0]["filled_at"] == _BROKER_FILL


def test_overlay_survives_cleared_in_memory_nova_placed_map():
    from ibkr.order_times import (
        clear_nova_placed_for_tests,
        remember_nova_placed,
        resolve_submitted_at,
    )

    remember_nova_placed(116071, _NOVA_PLACED)
    clear_nova_placed_for_tests()
    assert resolve_submitted_at(None, 116071) is None
    out = overlay_closed_orders(
        [_ztg_cancel_ib()],
        ledger_rows=[_ztg_cancel_ledger()],
        limit=50,
    )
    assert out[0]["submitted_at"] == _NOVA_PLACED
    assert out[0]["filled_at"] is None


def test_ib_recovered_cancel_does_not_invent_time_placed():
    out = overlay_closed_orders(
        [_ztg_cancel_ib(order_id=555, symbol="FTFT")],
        ledger_rows=[],
        limit=50,
    )
    assert len(out) == 1
    assert out[0]["source"] == "ib_recovered"
    assert out[0]["submitted_at"] is None
    assert out[0]["filled_at"] is None


def test_overlay_created_ts_fallback_when_payload_lacks_nova_placed():
    """Already-written Nova rows (ZTG before persist) still get an honest clock."""
    from datetime import datetime, timezone

    created_ts = 1_755_451_009.0
    payload = {
        "qty": 1,
        "sent_qty": 1.0,
        "side": "BUY",
        "order_type": "LMT",
        "requested_price": 1.76,
    }
    out = overlay_closed_orders(
        [_ztg_cancel_ib()],
        ledger_rows=[_ztg_cancel_ledger(payload=payload, created_ts=created_ts)],
        limit=50,
    )
    expected = datetime.fromtimestamp(created_ts, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    assert out[0]["submitted_at"] == expected
    assert out[0]["filled_at"] is None


def test_leftover_ledger_prefers_nova_placed_at_over_created_ts():
    out = overlay_closed_orders(
        [],
        ledger_rows=[_ztg_cancel_ledger()],
        limit=50,
    )
    assert out[0]["submitted_at"] == _NOVA_PLACED
    assert out[0]["filled_at"] is None


def test_live_presubmitted_place_and_cancel_op_join_ib_zero_id():
    """Red Team live shape: place stays PreSubmitted; cancel is a separate op."""
    place = _ztg_cancel_ledger(
        status="acked",
        broker_status="PreSubmitted",
        perm_id=888777,
        filled_qty=None,
    )
    cancel_op = {
        "id": "e-cancel-116071",
        "operation": "cancel",
        "source": "manual",
        "symbol": "ZTG",
        "status": "acked",
        "order_id": 116071,
        "perm_id": 888777,
        "filled_qty": None,
        "broker_status": "Cancelled",
        "created_ts": 1_755_451_010.0,
        "payload": {},
    }
    ib = _ztg_cancel_ib(order_id=0, perm_id=888777, submitted_at=None)
    out = overlay_closed_orders(
        [ib],
        ledger_rows=[place, cancel_op],
        limit=50,
    )
    assert len(out) == 1
    assert out[0]["source"] == "nova"
    assert out[0]["execution_id"] == "e-ztg-116071"
    assert out[0]["submitted_at"] == _NOVA_PLACED
    assert out[0]["filled_at"] is None
    assert out[0]["status"] == "Cancelled"
    assert out[0]["order_id"] == 116071


def test_presubmitted_place_leftover_is_not_appended_to_closed():
    """Working PreSubmitted must not become a Closed leftover row."""
    place = _ztg_cancel_ledger(
        status="acked",
        broker_status="PreSubmitted",
        perm_id=888777,
    )
    assert overlay_closed_orders([], ledger_rows=[place], limit=50) == []


def test_overlay_filled_joins_presubmitted_place_by_perm_id():
    ib = _ib(
        order_id=0,
        perm_id=888001,
        symbol="SPCX",
        status="Filled",
        qty=0,
        filled_qty=0,
        submitted_at=None,
        filled_at=_BROKER_FILL,
    )
    led = _ledger(
        id="e-spcx-open",
        symbol="SPCX",
        status="acked",
        broker_status="PreSubmitted",
        order_id=115728,
        perm_id=888001,
        filled_qty=None,
        payload={
            "qty": 1,
            "sent_qty": 1.0,
            "side": "BUY",
            "order_type": "MKT",
            "nova_placed_at": _NOVA_PLACED,
        },
    )
    out = overlay_closed_orders([ib], ledger_rows=[led], limit=50)
    assert out[0]["source"] == "nova"
    assert out[0]["submitted_at"] == _NOVA_PLACED
    assert out[0]["filled_at"] == _BROKER_FILL
    assert out[0]["order_id"] == 115728
