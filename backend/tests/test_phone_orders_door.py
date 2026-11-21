"""A phone order through the real door on a Paper broker (ADR 070, amendment 2026-11-10): nothing stubbed
between the phone's route and the practice venue but the market itself and the feed's health."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from execution import inflight, service, store
from ibkr import arm_pin
from ibkr import safety as _safety
from market_view import gate
from phone import pin, session
from constants_ibkr import ARM_PIN_HASH_ENV
from phone.constants_phone import PHONE_PIN_HASH_ENV, PHONE_SESSION_HEADER, PHONE_SHOWN_VENUE_HEADER
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests
from request_guard.middleware import RequestGuardMiddleware
from request_guard.policy import load_policy
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue

PHONE = "desk.tail1234.ts.net"
REMOTE = {"host": PHONE, "tailscale-user-login": "operator@example.com"}
PIN = "135790"
# The desk's Live PIN, set apart from the phone's own here: the Live padlock takes this one only.
LIVE_PIN = "864202"
SYM = "IMCC"


class FakeLive:
    """A live market that prices IMCC at 9.98 x 10.02 and never prints on its own."""

    def reference(self, symbol: str) -> Reference:
        return Reference(10.0, 9.98, 10.02, live=True) if symbol == SYM else Reference(None, live=True)

    def admission(self, symbol: str):
        return (True, "OK", None) if symbol == SYM else (False, "dark", "PRACTICE_NO_LIVE_PRINT")

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return time.time()

    def session_close_ts(self, ts: float) -> float:
        return ts + 86_400


@pytest.fixture
def phone(monkeypatch):
    from main import app

    reset_venue()
    reset_for_tests()
    service.reset_for_tests()
    store.init_db()
    from market_view import versions

    versions.reset_for_tests()
    monkeypatch.setattr(practice_broker, "LiveReference", FakeLive)
    monkeypatch.setattr(gate, "desk_lock", lambda symbol, **_: None)  # the feed is healthy
    monkeypatch.setenv(PHONE_PIN_HASH_ENV, arm_pin.hash_pin(PIN, iterations=1000))
    monkeypatch.setenv(ARM_PIN_HASH_ENV, arm_pin.hash_pin(LIVE_PIN, iterations=1000))
    monkeypatch.delenv("NOVA_API_KEY", raising=False)
    pin.reset_for_tests()
    arm_pin.reset_for_tests()
    session.close()
    set_venue("paper")
    guard = next(m for m in app.user_middleware if m.cls is RequestGuardMiddleware)
    monkeypatch.setitem(guard.kwargs, "policy", load_policy({"NOVA_ALLOWED_HOSTS": PHONE})[0])
    monkeypatch.setattr(app, "middleware_stack", None)
    client = TestClient(app)
    token = client.post("/api/phone/unlock", headers=REMOTE, json={"pin": PIN}).json()["token"]
    try:
        yield client, {**REMOTE, PHONE_SESSION_HEADER: token}
    finally:
        app.middleware_stack = None
        session.close()
        arm_pin.reset_for_tests()
        _safety.set_armed(False, reason="test teardown")
        service.reset_for_tests()
        inflight.reset_for_tests()
        reset_for_tests()
        reset_venue()


def _order(tapped_ms_ago: float = 20.0, *, with_book: bool = True, **over) -> dict:
    """A phone order whose view holds the newest Level 2 version this backend issued for IMCC."""
    import instance_identity
    from market_view import versions

    tapped = time.time() * 1000.0 - tapped_ms_ago
    timing = {"action_wall_ms": tapped, "action_performance_ms": 1.0, "request_wall_ms": tapped, "request_performance_ms": 1.0}
    view: dict = {"action_wall_ms": tapped, "symbol": SYM}
    if with_book:
        seq = (versions.latest(versions.BOOK, SYM) or versions.bump(versions.BOOK, SYM)).seq
        view.update(instance=instance_identity.INSTANCE_ID, book={"seq": seq, "bid": 9.98, "ask": 10.02})
    return {"symbol": SYM, "side": "BUY", "qty": 1, "order_type": "LMT", "limit_price": 9.90,
            "client_timing": timing, "view": view, **over}


def test_a_phone_buy_rests_on_paper_and_the_phone_cancels_it(phone):
    client, unlocked = phone
    # The padlock is closed after a venue change: the door refuses the buy in its own words.
    shut = client.post("/api/phone/order", headers=unlocked, json=_order()).json()
    assert (shut["ok"], shut["reason_code"]) == (False, "DISARMED")
    assert client.post("/api/phone/arm", headers=unlocked, json={"armed": True}).json()["armed"] is True
    placed = client.post("/api/phone/order", headers=unlocked, json=_order()).json()
    assert (placed["ok"], placed["broker_status"]) == (True, "Submitted"), placed
    working = for_venue("paper").working_orders()
    assert [(row["symbol"], row["side"], float(row["qty"])) for row in working] == [(SYM, "BUY", 1.0)]
    row = store.get_by_id(placed["execution_id"])
    assert row["source"] == "manual"
    done = client.delete(f"/api/phone/orders?symbol={SYM}", headers=unlocked).json()
    assert done["ok"] is True and done["cancelled"] == [placed["order_id"]]
    assert for_venue("paper").working_orders() == []


def test_a_phone_buy_tapped_too_long_ago_is_refused_by_the_desks_own_rule(phone):
    client, unlocked = phone
    _safety.set_armed(True, reason="test")
    late = client.post("/api/phone/order", headers=unlocked, json=_order(tapped_ms_ago=900.0)).json()
    assert (late["ok"], late["reason_code"]) == (False, "ORDER_LATE")
    assert for_venue("paper").working_orders() == []


def test_a_buy_from_a_phone_that_received_no_level_2_is_not_sent_and_its_ways_out_are(phone):
    from phone.constants_phone import PHONE_NO_VIEW

    client, unlocked = phone
    _safety.set_armed(True, reason="test")
    blind = client.post("/api/phone/order", headers=unlocked, json=_order(with_book=False))
    assert blind.status_code == 409 and blind.json()["detail"]["reason"] == PHONE_NO_VIEW
    assert for_venue("paper").working_orders() == []
    # A book the phone holds that this backend never issued is the door's own refusal.
    stale = _order()
    stale["view"]["book"]["seq"] = 10_000_000
    assert client.post("/api/phone/order", headers=unlocked, json=stale).json()["reason_code"] == "VIEW_STALE"
    # A sell is a way out: it reaches the door without a view, and the door answers for the position.
    sell = client.post("/api/phone/order", headers=unlocked, json=_order(with_book=False, side="SELL")).json()
    assert sell.get("reason_code") != "VIEW_STALE" and "detail" not in sell


def test_on_live_the_padlock_opens_only_with_the_desks_live_pin(phone):
    """Amendment 2026-11-20: the phone opens the Live padlock through the desk's own rule -- the PC's Live PIN, never
    the phone's own PIN, and the PC's count of wrong ones. Locking needs none."""
    client, unlocked = phone
    set_venue("live")
    assert client.get("/api/phone", headers=unlocked).json()["arm_requires_pin"] is True
    for body, code in (({"armed": True}, "ARM_PIN_REQUIRED"),
                       ({"armed": True, "pin": PIN}, "ARM_PIN_INVALID"),  # the phone's own PIN opens the phone only
                       ({"armed": True, "pin": "000000"}, "ARM_PIN_INVALID")):
        res = client.post("/api/phone/arm", headers=unlocked, json=body)
        assert res.status_code == 403 and res.json()["detail"]["reason"] == code, res.text
    assert _safety.armed() is False
    opened = client.post("/api/phone/arm", headers=unlocked, json={"armed": True, "pin": LIVE_PIN})
    assert opened.status_code == 200 and opened.json()["armed"] is True
    assert (_safety.armed(), _safety.armed_by()) == (True, "operator")
    assert client.post("/api/phone/arm", headers=unlocked, json={"armed": False}).json()["armed"] is False
    # Wrong PINs typed on the phone count with the PC's: five, and Live arming is locked even for the right one.
    for _ in range(5):
        client.post("/api/phone/arm", headers=unlocked, json={"armed": True, "pin": "111111"})
    locked = client.post("/api/phone/arm", headers=unlocked, json={"armed": True, "pin": LIVE_PIN})
    assert locked.status_code == 403 and locked.json()["detail"]["reason"] == "ARM_PIN_LOCKED"
    assert _safety.armed() is False


def test_on_live_a_phone_order_is_the_desks_live_order(phone, monkeypatch):
    """A Live order from the phone reaches the desk's Live door: the padlock holds it, the Live share limit cuts it,
    and with the padlock open it goes on to the IBKR door's own checks (no Gateway here, so it stops there)."""
    from constants import IBKR_FORCE_ONE_SHARE, IBKR_QTY_CAP_ENV

    client, unlocked = phone
    monkeypatch.setenv(IBKR_QTY_CAP_ENV, "1")
    set_venue("live")
    shows_live = {**unlocked, PHONE_SHOWN_VENUE_HEADER: "live"}
    shut = client.post("/api/phone/order", headers=shows_live, json=_order(venue="live")).json()
    assert (shut["ok"], shut["reason_code"]) == (False, "DISARMED")
    assert client.post("/api/phone/arm", headers=unlocked, json={"armed": True, "pin": LIVE_PIN}).json()["armed"] is True
    sent = client.post("/api/phone/order", headers=shows_live, json=_order(venue="live", qty=5)).json()
    assert sent["ok"] is False and sent["reason_code"] == "ORDERS_GATE", sent
    row = store.get_by_id(sent["execution_id"])
    assert (row["source"], row["payload"]["venue"]) == ("manual", "live")
    if IBKR_FORCE_ONE_SHARE:
        payload = row["payload"]
        assert (payload["requested_qty"], payload["sent_qty"], payload["forced_one_share"]) == (5.0, 1.0, True)
    assert for_venue("paper").working_orders() == [] and for_venue("sim").working_orders() == []


def test_a_tap_on_live_never_trades_paper_after_the_desk_moved(phone):
    """The venue the phone names is the one the operator tapped on; the door refuses it once the desk left it."""
    client, unlocked = phone
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    shows_live = {**unlocked, PHONE_SHOWN_VENUE_HEADER: "live"}
    moved = client.post("/api/phone/order", headers=shows_live, json=_order(venue="live")).json()
    assert (moved["ok"], moved["reason_code"]) == (False, "VENUE_CHANGED")
    assert for_venue("paper").working_orders() == []
    # A padlock opened on Paper is not one on Live: a move to Live leaves the desk locked there.
    set_venue("live")
    assert _safety.armed() is False


def test_a_tap_on_paper_never_trades_sim_after_the_desk_moved(phone):
    """The venue the phone names is the one the operator tapped on; the door refuses it once the desk left it."""
    client, unlocked = phone
    _safety.set_armed(True, reason="test")
    set_venue("sim")
    _safety.set_armed(True, reason="test")
    moved = client.post("/api/phone/order", headers=unlocked, json=_order(venue="paper", side="SELL")).json()
    assert (moved["ok"], moved["reason_code"]) == (False, "VENUE_CHANGED")
    assert for_venue("sim").working_orders() == [] and for_venue("paper").working_orders() == []
    # A cancel tapped on Paper does not cancel Sim's orders: the door's own words say the desk moved.
    cancel = client.delete(f"/api/phone/orders?symbol={SYM}&venue=paper", headers=unlocked).json()
    assert (cancel["ok"], cancel["cancelled"]) == (False, [])
    assert "moved from Paper to Sim" in cancel["error"]
    one = client.delete("/api/phone/order/41?venue=paper", headers=unlocked).json()
    assert one["ok"] is False, one
    # A tap on Live goes to Live's door, which the desk has left; a venue that does not exist is not read at all.
    shows_live = {**unlocked, PHONE_SHOWN_VENUE_HEADER: "live"}
    live = client.post("/api/phone/order", headers=shows_live, json=_order(venue="live")).json()
    assert (live["ok"], live["reason_code"]) == (False, "VENUE_CHANGED")
    assert client.delete(f"/api/phone/orders?symbol={SYM}&venue=bank", headers=unlocked).status_code == 422


def test_a_tap_on_sim_trades_sim(phone):
    client, unlocked = phone
    set_venue("sim")
    _safety.set_armed(True, reason="test")
    placed = client.post("/api/phone/order", headers=unlocked, json=_order(venue="sim")).json()
    assert placed.get("reason_code") != "VENUE_CHANGED", placed
