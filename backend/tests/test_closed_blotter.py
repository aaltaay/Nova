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
