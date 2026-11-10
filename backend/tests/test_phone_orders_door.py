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
from phone.constants_phone import PHONE_NOT_PAPER, PHONE_PIN_HASH_ENV, PHONE_SESSION_HEADER
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests
from request_guard.middleware import RequestGuardMiddleware
from request_guard.policy import load_policy
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue

PHONE = "desk.tail1234.ts.net"
REMOTE = {"host": PHONE, "tailscale-user-login": "operator@example.com"}
PIN = "135790"
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
    monkeypatch.delenv("NOVA_API_KEY", raising=False)
    pin.reset_for_tests()
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


def test_the_desk_off_paper_refuses_the_phone_at_its_route_and_at_the_door(phone, monkeypatch):
    client, unlocked = phone
    set_venue("sim")
    res = client.post("/api/phone/order", headers=unlocked, json=_order())
    assert res.status_code == 409 and res.json()["detail"]["reason"] == PHONE_NOT_PAPER
    # The route's check passed and the desk moved before the send: the door itself holds the line.
    from phone import routes

    monkeypatch.setattr(routes, "_paper_only", lambda: None)
    moved = client.post("/api/phone/order", headers=unlocked, json=_order()).json()
    assert (moved["ok"], moved["reason_code"]) == (False, "VENUE_CHANGED")
    assert for_venue("paper").working_orders() == []
