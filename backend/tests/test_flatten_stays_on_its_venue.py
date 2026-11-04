"""KILL stays on one venue, and stops if the desk leaves it (#1281; the operator's decision, 2026-11-04).

Each test sends through the real ``execution.service.execute`` and the real Paper and Sim ledgers; only IBKR's edge
is faked. ``book.sent`` and ``book.cancels`` are what would have reached IBKR. The desk is disarmed throughout: moving
it always disarms, so these are the sends a KILL makes with no arm at all.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from bot import flatten
from execution import broker_send, inflight, store, telemetry, venue_door
from execution.models import ExecutionCommand
from execution.service import execute
from ibkr import client as client_mod
from ibkr import live_book
from ibkr import safety as safety_mod
from ibkr.errors import IbkrAccountError
from main import app
from practice import broker as practice_broker
from practice.broker import for_venue
from practice.broker import reset_for_tests as reset_brokers
from practice.ledger import Fees
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue
from sim.mode import set_venue

NOW = 1_700_000_000.0


class FakeLive:
    """The live feed Paper marks from."""

    def reference(self, symbol: str) -> Reference:
        return Reference(10.0, 9.98, 10.02, live=True)

    def admission(self, symbol: str):
        return True, "OK", None

    def prints_between(self, symbol, after_ts, through_ts):
        return []

    def now_ts(self) -> float:
        return NOW


class FakeIb:
    """What a flatten reads on Live: IBKR's positions and open trades."""

    def __init__(self, book) -> None:
        self.book = book

    def positions(self):
        return [SimpleNamespace(contract=SimpleNamespace(symbol=symbol), position=qty, avgCost=10.0)
                for symbol, qty in self.book.positions.items()]

    def openTrades(self):
        return []


@pytest.fixture
def book(monkeypatch, tmp_path):
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    store.init_db()
    telemetry.reset_for_tests()
    inflight.reset_for_tests()
    reset_venue()
    reset_brokers()
    monkeypatch.setattr(practice_broker, "LiveReference", FakeLive)
    ibkr = SimpleNamespace(positions={}, sent=[], cancels=[], rows=[])
    fake_ib = FakeIb(ibkr)
    monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "live")
    monkeypatch.setattr(client_mod, "broker_account_kind", lambda: "live")
    monkeypatch.setattr(client_mod, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(safety_mod, "orders_enabled", lambda: True)
    monkeypatch.setattr(safety_mod, "live_trading_confirmed", lambda: True)
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    monkeypatch.setattr(live_book, "positions", lambda: dict(ibkr.positions))
    monkeypatch.setattr(live_book, "open_rows", lambda: [dict(row) for row in ibkr.rows])

    import ibkr.orders as orders_mod

    def place(**kw):
        ibkr.sent.append(kw)
        return {"ok": True, "order_id": 9000 + len(ibkr.sent), "error": None, "mode": "live"}

    async def cancel(order_id, *, watch=None):
        ibkr.cancels.append(order_id)
        return {"ok": True, "error": None, "verified_gone": True, "order_id": order_id}

    monkeypatch.setattr(orders_mod, "place_order", place)
    monkeypatch.setattr(broker_send, "cancel_order_verified_on_ib", cancel)
    yield ibkr
    inflight.reset_for_tests()
    telemetry.reset_for_tests()
    reset_brokers()
    reset_venue()


def _move_after(monkeypatch, target_path: str, venue: str) -> None:
    """The operator clicks another venue pill just after this read, the first time it runs."""
    module_path, _, name = target_path.rpartition(".")
    module = __import__(module_path, fromlist=[name])
    real = getattr(module, name)
    moved = []

    def read(*args, **kwargs):
        rows = real(*args, **kwargs)
        if not moved:
            moved.append(True)
            set_venue(venue, persist=False)
        return rows

    monkeypatch.setattr(module, name, read)


def _move_after_positions(monkeypatch, venue: str) -> None:
    _move_after(monkeypatch, "ibkr.account.get_positions", venue)


def _move_after_the_list(monkeypatch, venue: str) -> None:
    _move_after(monkeypatch, "ibkr.orders.open_orders", venue)


def _kill() -> dict:
    return asyncio.run(flatten.flatten_account_with_retry(origin="emergency_kill"))


def _short(venue: str, symbol: str, qty: float) -> None:
    broker = for_venue(venue)
    ledger = broker.ledger
    order_id = ledger.alloc_id()
    row = broker._row(order_id, symbol, "SELL", qty, "MKT", None, None, NOW, "manual", None, "DAY", short_entry=True)
    ledger.place(row, ts=NOW, source="manual")
    ledger.fill(order_id, ts=NOW, price=10.0, basis="quote", fees=Fees(0.0, 0.0, 0.0, 0.0))


def _held(venue: str) -> dict[str, float]:
    return {row["symbol"]: float(row["qty"]) for row in for_venue(venue).positions()}


def _stopped(out: dict, venue: str, moved_to: str) -> None:
    assert (out["ok"], out.get("reason_code")) == (False, "VENUE_CHANGED")
    assert (out["venue"], out["moved_to"], out["attempt"]) == (venue, moved_to, 1)
    assert f"from {venue.capitalize()} to {moved_to.capitalize()}" in out["error"]


# ── the venue the desk moved to is never touched ──

def test_a_paper_position_never_sells_on_live(book, monkeypatch):
    set_venue("paper", persist=False)
    assert for_venue("paper").place("ABCD", "BUY", 100, "MKT")["broker_status"] == "Filled"
    for_venue("paper").place("WXYZ", "BUY", 5, "LMT", limit_price=1.0)
    _move_after_positions(monkeypatch, "live")

    out = _kill()

    assert book.sent == [] and book.cancels == []
    _stopped(out, "paper", "live")
    assert (out["left_open"], out["working_orders"]) == (["ABCD 100"], 1)
    assert "ABCD 100" in out["error"] and "1 working order" in out["error"] and "may have no stop" in out["error"]
    assert _held("paper") == {"ABCD": 100.0}


def test_a_paper_short_never_buys_on_live(book, monkeypatch):
    set_venue("paper", persist=False)
    _short("paper", "ABCD", 50)
    _move_after_positions(monkeypatch, "live")

    out = _kill()

    assert book.sent == []
    _stopped(out, "paper", "live")
    assert out["left_open"] == ["ABCD -50"]
    assert _held("paper") == {"ABCD": -50.0}


def test_a_papers_order_number_never_cancels_on_live(book, monkeypatch):
    """Practice ids restart at 1, so Paper's order 1 can be a real order of IBKR's."""
    set_venue("paper", persist=False)
    for_venue("paper").place("WXYZ", "BUY", 5, "LMT", limit_price=1.0)
    for_venue("paper").place("QQQQ", "BUY", 5, "LMT", limit_price=1.0)
    _move_after_the_list(monkeypatch, "live")

    out = _kill()

    assert book.cancels == []
    _stopped(out, "paper", "live")
    assert len(out["cancels"]) == 1     # the first refusal ends the run
    assert len(for_venue("paper").working_orders()) == 2


def test_a_retry_never_sells_the_venue_the_desk_moved_to(book, monkeypatch):
    set_venue("paper", persist=False)
    for_venue("paper").place("QQQQ", "BUY", 30, "MKT")
    book.positions = {"ABCD": 100.0}
    set_venue("live", persist=False)
    _move_after_positions(monkeypatch, "paper")

    out = _kill()

    _stopped(out, "live", "paper")
    assert _held("paper") == {"QQQQ": 30.0}


def test_a_live_short_never_buys_on_paper(book, monkeypatch):
    book.positions = {"ABCD": -100.0}
    set_venue("live", persist=False)
    _move_after_positions(monkeypatch, "paper")

    out = _kill()

    _stopped(out, "live", "paper")
    assert _held("paper") == {} and for_venue("paper").closed_orders() == []


def test_sim_is_never_touched_either(book, monkeypatch):
    set_venue("paper", persist=False)
    for_venue("paper").place("ABCD", "BUY", 100, "MKT")
    _move_after_positions(monkeypatch, "sim")

    out = _kill()

    _stopped(out, "paper", "sim")
    assert _held("paper") == {"ABCD": 100.0}


# ── it says so: a flat new venue is never read as a finished KILL ──

def test_a_flat_paper_never_reads_as_lives_shares_closed(book, monkeypatch):
    book.positions = {"ABCD": 100.0}
    set_venue("live", persist=False)
    _move_after_positions(monkeypatch, "paper")

    out = _kill()

    assert book.sent == []
    _stopped(out, "live", "paper")
    assert out["left_open"] == ["ABCD 100"] and "Still open on Live: ABCD 100" in out["error"]


def test_an_empty_list_read_after_the_move_is_no_proof(book, monkeypatch):
    """Nothing held, the list read on Live and empty: Paper's order still works, so this is no finished KILL."""
    set_venue("paper", persist=False)
    for_venue("paper").place("WXYZ", "BUY", 5, "LMT", limit_price=1.0)
    _move_after_positions(monkeypatch, "live")

    out = _kill()

    _stopped(out, "paper", "live")
    assert out["working_orders"] == 1 and "1 working order" in out["error"]


def test_a_book_it_cannot_read_is_said_never_flat(book, monkeypatch):
    book.positions = {"ABCD": 100.0}
    set_venue("live", persist=False)
    _move_after_positions(monkeypatch, "paper")

    def unreadable():
        raise IbkrAccountError("IBKR's own book cannot be read")

    monkeypatch.setattr(live_book, "positions", unreadable)
    monkeypatch.setattr(live_book, "open_rows", unreadable)

    out = _kill()

    _stopped(out, "live", "paper")
    assert (out["left_open"], out["working_orders"]) == (None, None)
    assert "could not be read" in out["error"] and "Nothing is open" not in out["error"]


def test_it_stops_between_two_closes_and_names_the_close_already_sent(book, monkeypatch):
    book.positions = {"AAAA": 100.0, "BBBB": 100.0}
    set_venue("live", persist=False)
    real = flatten._place_close
    sends = []

    async def place(symbol, qty, side, **kw):
        out = await real(symbol, qty, side, **kw)
        sends.append(symbol)
        if len(sends) == 1:
            set_venue("paper", persist=False)
        return out

    monkeypatch.setattr(flatten, "_place_close", place)

    out = _kill()

    assert [order["symbol"] for order in book.sent] == ["AAAA"]
    _stopped(out, "live", "paper")
    assert "Closes already sent on Live: AAAA" in out["error"]
    assert _held("paper") == {}


def test_a_second_pass_stays_on_the_venue_it_read(book, monkeypatch):
    """A first pass that fails for its own reason, then a desk that moved: the retry stops, it never reads the desk."""
    set_venue("paper", persist=False)
    for_venue("paper").place("ABCD", "BUY", 100, "MKT")

    async def busy(symbol, qty, side, **kw):
        set_venue("live", persist=False)
        return {"ok": False, "error": "busy"}

    monkeypatch.setattr(flatten, "_place_close", busy)

    out = _kill()

    assert book.sent == []
    assert (out["ok"], out.get("reason_code"), out["attempt"]) == (False, "VENUE_CHANGED", 2)
    assert out["left_open"] == ["ABCD 100"]


# ── the click names the venue: a desk that moved during KILL's first step ──

def test_the_flatten_that_lands_after_the_move_touches_neither_venue(book):
    set_venue("paper", persist=False)
    for_venue("paper").place("QQQQ", "BUY", 30, "MKT")
    book.positions = {"ABCD": 100.0}
    set_venue("live", persist=False)    # KILL confirmed here
    set_venue("paper", persist=False)   # the pill clicked while its cancels ran

    out = TestClient(app).post("/api/ibkr/flatten-account?venue=live").json()

    assert book.sent == []
    assert _held("paper") == {"QQQQ": 30.0}
    _stopped(out, "live", "paper")
    assert out["left_open"] == ["ABCD 100"]


def test_the_flatten_refuses_a_venue_it_does_not_know(book):
    set_venue("paper", persist=False)
    for_venue("paper").place("QQQQ", "BUY", 30, "MKT")

    res = TestClient(app).post("/api/ibkr/flatten-account?venue=mars")

    assert res.status_code == 400
    assert _held("paper") == {"QQQQ": 30.0}


def test_the_cancels_refuse_a_venue_that_does_not_exist_rather_than_say_the_desk_moved(book):
    set_venue("paper", persist=False)
    for_venue("paper").place("QQQQ", "BUY", 30, "LMT", limit_price=9.0)

    res = TestClient(app).delete("/api/ibkr/orders?all_symbols=true&venue=mars")

    assert res.status_code == 400
    assert "moved" not in res.text
    assert len(for_venue("paper").working_orders()) == 1


def test_the_cancels_named_for_paper_never_reach_ibkr(book):
    set_venue("paper", persist=False)
    working = for_venue("paper").place("WXYZ", "BUY", 5, "LMT", limit_price=1.0)
    book.rows = [{"order_id": working["order_id"], "symbol": "REAL", "side": "SELL", "qty": 10}]
    set_venue("live", persist=False)    # moved before the cancels arrived

    out = TestClient(app).delete("/api/ibkr/orders?all_symbols=true&venue=paper").json()

    assert book.cancels == []
    assert (out["ok"], out["cancelled"]) == (False, [])
    assert "from Paper to Live" in out["error"]
    assert len(for_venue("paper").working_orders()) == 1


def test_a_stocks_cancels_named_for_paper_never_reach_ibkr(book):
    """The header's Working menu: one DELETE per stock, each naming the venue it was confirmed on."""
    set_venue("paper", persist=False)
    working = for_venue("paper").place("WXYZ", "BUY", 5, "LMT", limit_price=1.0)
    book.rows = [{"order_id": working["order_id"], "symbol": "WXYZ", "side": "SELL", "qty": 10}]
    set_venue("live", persist=False)    # moved while the confirm was open

    out = TestClient(app).delete("/api/ibkr/orders?symbol=WXYZ&venue=paper").json()

    assert book.cancels == []
    assert (out["ok"], out["cancelled"], out["symbol"]) == (False, [], "WXYZ")
    assert "from Paper to Live" in out["error"]
    assert len(for_venue("paper").working_orders()) == 1


def test_a_named_cancel_still_cancels_while_the_desk_stays(book):
    set_venue("paper", persist=False)
    for_venue("paper").place("WXYZ", "BUY", 5, "LMT", limit_price=1.0)

    out = TestClient(app).delete("/api/ibkr/orders?symbol=WXYZ&venue=paper").json()

    assert (out["ok"], len(out["cancelled"]), out["error"]) == (True, 1, None)
    assert for_venue("paper").working_orders() == []


def test_cancel_all_holds_the_venue_it_read_on_arrival(book, monkeypatch):
    """No venue named (the Cancel All hotkey): the rows it read are still only that venue's."""
    set_venue("paper", persist=False)
    for_venue("paper").place("WXYZ", "BUY", 5, "LMT", limit_price=1.0)
    _move_after_the_list(monkeypatch, "live")

    out = TestClient(app).delete("/api/ibkr/orders?all_symbols=true").json()

    assert book.cancels == []
    assert (out["ok"], out["cancelled"], out["failed"]) == (False, [], [])
    assert "none went to Live" in out["error"]
    assert len(for_venue("paper").working_orders()) == 1


def test_the_first_cancel_the_door_refuses_ends_the_run(book, monkeypatch):
    set_venue("paper", persist=False)
    first, second, _third = (for_venue("paper").place(symbol, "BUY", 5, "LMT", limit_price=1.0)
                             for symbol in ("AAAA", "BBBB", "CCCC"))
    _move_after(monkeypatch, "execution.service.finalize_http_response", "live")

    out = TestClient(app).delete("/api/ibkr/orders?all_symbols=true&venue=paper").json()

    assert book.cancels == []
    assert (out["ok"], out["cancelled"]) == (False, [first["order_id"]])
    assert [row["order_id"] for row in out["failed"]] == [second["order_id"]]
    assert len(for_venue("paper").working_orders()) == 2


# ── a desk that stays put: nothing here changed ──

def test_kill_still_closes_live_disarmed(book):
    book.positions = {"ABCD": 100.0}
    set_venue("live", persist=False)
    assert safety_mod.armed() is False

    out = TestClient(app).post("/api/ibkr/flatten-account?venue=live").json()

    assert out["ok"] is True and out["attempt"] == 1 and "reason_code" not in out
    assert [(order["symbol"], order["side"], order["qty"]) for order in book.sent] == [("ABCD", "SELL", 100.0)]


def test_kill_still_cancels_and_closes_paper_disarmed(book):
    set_venue("paper", persist=False)
    for_venue("paper").place("ABCD", "BUY", 100, "MKT")
    for_venue("paper").place("WXYZ", "BUY", 5, "LMT", limit_price=1.0)
    assert safety_mod.armed() is False

    client = TestClient(app)
    cancels = client.delete("/api/ibkr/orders?all_symbols=true&venue=paper").json()
    out = client.post("/api/ibkr/flatten-account?venue=paper").json()

    assert cancels["ok"] is True and len(cancels["cancelled"]) == 1
    assert out["ok"] is True
    assert _held("paper") == {} and for_venue("paper").working_orders() == []
    assert book.sent == [] and book.cancels == []


def test_a_kill_with_no_venue_named_works_the_desks(book):
    set_venue("paper", persist=False)
    for_venue("paper").place("ABCD", "BUY", 100, "MKT")

    out = TestClient(app).post("/api/ibkr/flatten-account").json()

    assert out["ok"] is True and _held("paper") == {}


def test_a_desk_that_moves_after_the_last_close_is_a_finished_kill(book, monkeypatch):
    book.positions = {"ABCD": 100.0}
    set_venue("live", persist=False)
    real = flatten._place_close

    async def place(symbol, qty, side, **kw):
        out = await real(symbol, qty, side, **kw)
        set_venue("paper", persist=False)
        return out

    monkeypatch.setattr(flatten, "_place_close", place)

    out = _kill()

    assert out["ok"] is True and [order["symbol"] for order in book.sent] == ["ABCD"]


# ── Live's gates: the fix adds no way to Live ──

def test_kill_may_not_name_a_venue(book):
    book.positions = {"ABCD": 100.0}
    set_venue("paper", persist=False)

    receipt = asyncio.run(execute(ExecutionCommand(
        operation="place", idempotency_key="kill:names:live", source="flatten", symbol="ABCD", side="SELL", qty=100,
        order_type="MKT", skip_risk=True, origin="emergency_kill", target_venue="live", intent="flatten"),
        wait_ack=False))

    assert (receipt.ok, receipt.reason_code) == (False, venue_door.TARGET_REFUSED)
    assert book.sent == []
