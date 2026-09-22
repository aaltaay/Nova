"""Orders (Today) shows the desk's own orders only (QA V5 / C18 / C53 / C54, 2026-09-22).

The execution ledger is one table for every venue. The closed-orders overlay
used to append its leftovers on any venue -- four filled Paper orders were
listed on Sim as "Inactive, filled 0" -- and to join rows on the order id
alone, which practice venues reuse. Leftover rows showed a stop as a limit and
the placement time as the fill time.
"""
from __future__ import annotations

from execution.closed_blotter import DeskLedger, ledger_rows_for_desk, overlay_closed_orders
from execution.fill_audit import classify_fill_audit, remember_fill_audit, reset_fill_audit_store_for_testing
from execution.fill_audit_attach import attach_fill_audit

LIVE = DeskLedger(practice=False, mode="live")
LIVE_ON_PAPER_GATEWAY = DeskLedger(practice=False, mode="paper")
PAPER = DeskLedger(practice=True, mode="paper")
SIM = DeskLedger(practice=True, mode="sim")


def _ledger(**kw) -> dict:
    row = {
        "id": "e-grml-1",
        "operation": "place",
        "source": "manual",
        "symbol": "GRML",
        "status": "filled",
        "order_id": 1,
        "perm_id": None,
        "filled_qty": None,
        "avg_fill_price": None,
        "broker_status": None,
        "mode": "paper",
        "created_ts": 1_790_000_000.0,
        "updated_ts": 1_790_000_030.0,
        "payload": {"qty": 1, "sent_qty": 1.0, "side": "BUY", "order_type": "MKT"},
    }
    row.update(kw)
    return row


def _practice_row(**kw) -> dict:
    row = {
        "order_id": 7, "perm_id": 7, "symbol": "GDC", "side": "BUY", "qty": 100.0,
        "filled_qty": 100.0, "remaining_qty": 0.0, "order_type": "LMT", "limit_price": 1.55,
        "stop_price": None, "avg_fill_price": 1.55, "status": "Filled", "venue": "sim", "mode": "sim",
        "submitted_at": "2026-09-22T14:00:00.000Z", "filled_at": "2026-09-22T14:00:05.000Z",
        "nova_placed_at": "2026-09-22T14:00:00.000Z", "fill_estimated": True, "source": "nova",
    }
    row.update(kw)
    return row


# ── V5 / C18: a practice desk lists its own ledger, nothing else ─────────────

def test_sim_never_lists_papers_filled_orders() -> None:
    papers_four = [_ledger(id=f"e-{i}", order_id=i) for i in range(1, 5)]
    assert overlay_closed_orders([], ledger_rows=papers_four, desk=SIM) == []


def test_a_practice_desks_rows_come_back_untouched_newest_first() -> None:
    older = _practice_row(order_id=1, perm_id=1, submitted_at="2026-09-22T13:00:00.000Z")
    newer = _practice_row(order_id=2, perm_id=2, submitted_at="2026-09-22T14:00:00.000Z")
    ledger = [_ledger(order_id=1, mode="sim"), _ledger(order_id=2, mode="sim")]
    out = overlay_closed_orders([older, newer], ledger_rows=ledger, desk=SIM)
    assert [row["order_id"] for row in out] == [2, 1]
    assert out == [newer, older]
    assert all("execution_id" not in row for row in out)


def test_live_leaves_practice_stamped_rows_out() -> None:
    rows = [
        _ledger(id="e-paper", order_id=11, mode="paper"),
        _ledger(id="e-sim", order_id=12, mode="sim"),
        _ledger(id="e-live", order_id=13, mode="live", broker_status="Filled", filled_qty=1.0),
        _ledger(id="e-old", order_id=14, mode=None, broker_status="Filled", filled_qty=1.0),
    ]
    assert [row["id"] for row in ledger_rows_for_desk(rows, LIVE)] == ["e-live", "e-old"]
    out = overlay_closed_orders([], ledger_rows=rows, desk=LIVE)
    assert sorted(row["order_id"] for row in out) == [13, 14]


def test_the_by_hand_paper_gateway_keeps_its_orders_but_not_papers_practice_orders(monkeypatch) -> None:
    from execution import closed_blotter

    practice_placed = "2026-09-22T14:10:00.000Z"
    monkeypatch.setattr(closed_blotter, "_practice_paper_stamps", lambda: {(21, practice_placed)})
    rows = [
        _ledger(id="e-practice", order_id=21, payload={"side": "BUY", "nova_placed_at": practice_placed}),
        _ledger(id="e-du-account", order_id=21, payload={"side": "BUY", "nova_placed_at": "2026-09-22T15:00:00.000Z"}),
        _ledger(id="e-live-login", order_id=22, mode="live"),
    ]
    assert [row["id"] for row in ledger_rows_for_desk(rows, LIVE_ON_PAPER_GATEWAY)] == ["e-du-account"]


# ── the leftover row itself ──────────────────────────────────────────────────

def test_a_ledger_fill_with_no_recorded_size_is_filled_never_inactive() -> None:
    out = overlay_closed_orders([], ledger_rows=[_ledger(mode="live")], desk=LIVE)
    assert out[0]["status"] == "Filled"


def test_a_broker_closed_status_still_wins_without_a_recorded_fill() -> None:
    led = _ledger(mode="live", status="failed", broker_status="Inactive")
    assert overlay_closed_orders([], ledger_rows=[led], desk=LIVE)[0]["status"] == "Inactive"


def test_a_stop_is_a_stop_and_a_trail_amount_is_not_a_limit() -> None:
    stop = _ledger(mode="live", payload={"side": "SELL", "order_type": "STP", "requested_price": 8.5})
    trail = _ledger(id="e-trail", order_id=2, mode="live", payload={"side": "SELL", "order_type": "TRAIL", "requested_price": 0.25})
    limit = _ledger(id="e-lmt", order_id=3, mode="live", payload={"side": "BUY", "order_type": "LMT", "requested_price": 1.76})
    rows = {row["order_id"]: row for row in overlay_closed_orders([], ledger_rows=[stop, trail, limit], desk=LIVE)}
    assert (rows[1]["limit_price"], rows[1]["stop_price"]) == (None, 8.5)
    assert (rows[2]["limit_price"], rows[2]["stop_price"]) == (None, 0.25)
    assert (rows[3]["limit_price"], rows[3]["stop_price"]) == (1.76, None)


def test_placement_time_is_never_shown_as_the_fill_time() -> None:
    from datetime import datetime, timezone

    led = _ledger(mode="live", filled_qty=1.0, avg_fill_price=9.1, broker_status="Filled")
    row = overlay_closed_orders([], ledger_rows=[led], desk=LIVE)[0]
    assert row["filled_qty"] == 1.0
    assert row["filled_at"] is None
    updated = datetime.fromtimestamp(led["updated_ts"], tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    assert row["updated_at"] == updated  # last activity (updated_ts), not placement (created_ts)


# ── C53: latency joins are scoped to the order ───────────────────────────────

def _audit(symbol: str, mode: str) -> dict:
    return classify_fill_audit(
        order_id=7, symbol=symbol, side="BUY", order_type="MKT", mode=mode, status="Filled",
        nova_placed_at="2026-09-16T14:05:00.000Z", submitted_at="2026-09-16T14:05:00.012Z",
        filled_at="2026-09-16T14:05:00.180Z", terminal_at=None, has_fill=True, rth=True,
    )


def test_another_venues_audit_with_the_same_order_id_is_not_attached() -> None:
    reset_fill_audit_store_for_testing()
    remember_fill_audit(_audit("GRML", "live"), nova_placed_at="2026-09-16T14:05:00.000Z")
    row = _practice_row(filled_at=None, nova_placed_at=None, submitted_at=None)
    out = attach_fill_audit([row], ledger_rows=[], desk=SIM)
    assert out[0]["fill_audit"] is None


def test_the_same_order_audit_still_attaches_on_live() -> None:
    reset_fill_audit_store_for_testing()
    remember_fill_audit(_audit("SPCX", "live"), nova_placed_at="2026-09-16T14:05:00.000Z")
    row = {
        "order_id": 7, "symbol": "SPCX", "side": "BUY", "qty": 1, "filled_qty": 1.0, "order_type": "MKT",
        "status": "Filled", "submitted_at": "2026-09-16T14:05:00.012Z", "filled_at": "2026-09-16T14:05:00.180Z",
    }
    audit = attach_fill_audit([row], ledger_rows=[], desk=LIVE)[0]["fill_audit"]
    assert audit is not None and audit["place_to_fill_ms"] == 180


def test_a_practice_row_never_borrows_an_unwound_orders_audit() -> None:
    reset_fill_audit_store_for_testing()
    remember_fill_audit(_audit("GDC", "sim"), nova_placed_at="2026-09-16T14:05:00.000Z")
    row = _practice_row(nova_placed_at="2026-09-22T14:00:00.000Z", filled_at="2026-09-22T14:00:00.000Z")
    out = attach_fill_audit([row], ledger_rows=[], desk=SIM)
    assert out[0]["fill_audit"] is None
