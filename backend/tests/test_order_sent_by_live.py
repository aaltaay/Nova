"""Who sent a Live order, joined from this desk's execution rows (#677).

Paper and Sim rows stamp their own sender. A Live row comes from IBKR with none, so the Orders
table's Sent by read "—" on every working Live order, and a Live bracket's exit leg -- whose id
is its own, not the entry's -- read "Outside Nova" once it closed.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from execution.closed_blotter import DeskLedger, overlay_closed_orders
from execution.sent_by import attach_sent_by, lookup, sent_by_index

LIVE = DeskLedger(practice=False, mode="live")


def _led(**kw) -> dict:
    row = {
        "id": "e1", "operation": "place", "source": "manual", "symbol": "ACN", "status": "acked",
        "order_id": 70, "perm_id": 7070, "mode": "live", "created_ts": 1790862300.0,
        "payload": {"side": "BUY", "qty": 100, "origin": None},
    }
    row.update(kw)
    return row


def _ib(**kw) -> dict:
    row = {"order_id": 70, "perm_id": 7070, "symbol": "ACN", "side": "BUY", "qty": 100, "filled_qty": 0,
           "remaining_qty": 100, "order_type": "LMT", "limit_price": 224.0, "status": "Submitted"}
    row.update(kw)
    return row


def test_a_live_row_is_found_by_perm_then_order_id_and_only_on_its_own_symbol() -> None:
    index = sent_by_index([_led()])
    assert lookup(index, _ib())["id"] == "e1"
    assert lookup(index, _ib(perm_id=None))["id"] == "e1"                  # order id alone
    assert lookup(index, _ib(symbol="NXL")) is None                         # same id, another stock
    assert lookup(index, _ib(order_id=0, perm_id=0)) is None                # a TWS order: no ids
    cancel = _led(id="c1", operation="cancel", order_id=71, perm_id=None)
    assert lookup(sent_by_index([cancel]), _ib(order_id=71, perm_id=None)) is None


def test_a_brackets_exit_legs_share_their_entrys_sender() -> None:
    bracket = _led(operation="bracket", source="manual", order_id=80, perm_id=8080, parent_order_id=80,
                   target_order_id=81, stop_order_id=82, payload={"side": "BUY", "qty": 10, "origin": "approve"})
    index = sent_by_index([bracket])
    for leg in (81, 82):
        assert lookup(index, _ib(order_id=leg, perm_id=9000 + leg, side="SELL"))["id"] == "e1"


def test_working_rows_take_their_sender_and_a_practice_row_keeps_its_own() -> None:
    led = _led(source="flatten", payload={"side": "SELL", "qty": 100, "origin": "emergency_kill"})
    rows = attach_sent_by([_ib(), _ib(order_id=99, perm_id=9999), {**_ib(), "order_source": "bot",
                                                                     "order_origin": "auto_entry"}], [led])
    assert (rows[0]["order_source"], rows[0]["order_origin"]) == ("flatten", "emergency_kill")
    assert "order_source" not in rows[1]                                    # not Nova's: no sender
    assert (rows[2]["order_source"], rows[2]["order_origin"]) == ("bot", "auto_entry")


def test_a_closed_bracket_leg_is_novas_not_outside_nova() -> None:
    bracket = _led(operation="bracket", status="filled", order_id=80, perm_id=8080, parent_order_id=80,
                   target_order_id=81, stop_order_id=82, filled_qty=10, avg_fill_price=224.0,
                   payload={"side": "BUY", "qty": 10, "origin": None})
    entry = _ib(order_id=80, perm_id=8080, qty=10, filled_qty=10, status="Filled")
    target = _ib(order_id=81, perm_id=8181, side="SELL", qty=10, filled_qty=10, status="Filled")
    tws = _ib(order_id=0, perm_id=5555, symbol="AAPL", status="Filled")
    rows = {r["perm_id"]: r for r in overlay_closed_orders([entry, target, tws], ledger_rows=[bracket], desk=LIVE)}
    assert (rows[8080]["source"], rows[8080]["order_source"]) == ("nova", "manual")
    assert (rows[8181]["source"], rows[8181]["order_source"], rows[8181]["filled_qty"]) == ("nova", "manual", 10)
    assert rows[5555]["source"] == "ib_recovered" and "order_source" not in rows[5555]


def test_the_working_orders_route_says_who_sent_each_live_order(monkeypatch) -> None:
    from main import app

    led = _led(source="flatten", payload={"side": "SELL", "qty": 100, "origin": "all_stop"})
    monkeypatch.setattr("ibkr.orders.open_orders", lambda: [_ib(side="SELL")])
    monkeypatch.setattr("execution.closed_blotter.load_session_ledger", lambda: [led])
    monkeypatch.setattr("execution.closed_blotter.current_desk", lambda: LIVE)
    body = TestClient(app).get("/api/ibkr/orders").json()
    assert (body[0]["order_source"], body[0]["order_origin"]) == ("flatten", "all_stop")
    assert "fill_audit" in body[0]


def test_an_unreadable_ledger_leaves_the_rows_unjoined_not_failed(monkeypatch) -> None:
    from main import app

    def broken():
        raise RuntimeError("database is locked")

    monkeypatch.setattr("ibkr.orders.open_orders", lambda: [_ib()])
    monkeypatch.setattr("execution.closed_blotter.load_session_ledger", broken)
    monkeypatch.setattr("execution.closed_blotter.current_desk", lambda: LIVE)
    res = TestClient(app).get("/api/ibkr/orders")
    assert res.status_code == 200 and "order_source" not in res.json()[0]


def test_a_live_short_entry_row_says_so_and_its_cover_legs_do_not() -> None:
    """ADR 048 gap 7: Fill now reads ``short_entry`` from the row, so only the SELL that opened the short
    carries it; the short bracket's BUY exits cover and never read as a short entry."""
    bracket = _led(operation="bracket", order_id=90, perm_id=9090, parent_order_id=90, target_order_id=91,
                   stop_order_id=92, payload={"side": "SELL", "qty": 416, "origin": None, "short_entry": True})
    plain = _led(id="e2", order_id=95, perm_id=9595, payload={"side": "SELL", "qty": 10, "short_entry": False})
    rows = attach_sent_by([
        _ib(order_id=90, perm_id=9090, side="SELL"),
        _ib(order_id=91, perm_id=9191, side="BUY"),
        _ib(order_id=92, perm_id=9292, side="BUY", order_type="STP"),
        _ib(order_id=95, perm_id=9595, side="SELL"),
        _ib(order_id=99, perm_id=9999, side="SELL"),
    ], [bracket, plain])
    assert [row.get("short_entry") for row in rows] == [True, False, False, False, None]
