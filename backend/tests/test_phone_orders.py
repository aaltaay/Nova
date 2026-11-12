"""The phone's door (ADR 070, amendment 2026-11-10): another device may write only to ``/api/phone``,
only after the phone PIN, and only Paper orders -- handed to the desk's own order door."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from ibkr import arm_pin
from phone import pin, routes, session
from phone.constants_phone import (
    PHONE_LOCKED,
    PHONE_NOT_PAPER,
    PHONE_PIN_HASH_ENV,
    PHONE_PIN_INVALID,
    PHONE_PIN_LOCKED,
    PHONE_PIN_LOCKOUT_SEC,
    PHONE_PIN_MAX_FAILURES,
    PHONE_PIN_NOT_SET,
    PHONE_SESSION_HEADER,
    PHONE_SESSION_SEC,
)
from request_guard.constants_request_guard import REASON_REMOTE_VIEW_ONLY
from request_guard.middleware import RequestGuardMiddleware
from request_guard.policy import load_policy

PHONE = "desk.tail1234.ts.net"
REMOTE = {"host": PHONE, "tailscale-user-login": "operator@example.com"}
PIN = "246810"
TIMING = {"action_wall_ms": 1.0, "action_performance_ms": 1.0, "request_wall_ms": 2.0, "request_performance_ms": 2.0}
ORDER = {"symbol": "f", "side": "BUY", "qty": 1, "client_timing": TIMING,
         "view": {"action_wall_ms": 1.0, "instance": "this-backend", "book": {"seq": 4}}}


@pytest.fixture
def phone(monkeypatch):
    """The real app as another device sees it, with a phone PIN set, the desk on Paper and the door stubbed."""
    from main import app

    monkeypatch.setenv(PHONE_PIN_HASH_ENV, arm_pin.hash_pin(PIN, iterations=1000))
    monkeypatch.setenv("NOVA_API_KEY", "the-desk-key")
    pin.reset_for_tests()
    session.close()
    state = {"venue": "paper", "sent": []}
    monkeypatch.setattr(routes, "_venue", lambda: state["venue"])

    async def place_order(order, request):
        state["sent"].append(order)
        return {"ok": True, "order_id": 7}

    async def cancel_order(order_id, request, idempotency_key=None, venue=None):
        state["sent"].append(("cancel", order_id, venue))
        return {"ok": True}

    async def cancel_orders_for_symbol(request, symbol=None, all_symbols=False, venue=None):
        state["sent"].append(("cancel_symbol", symbol, all_symbols, venue))
        return {"ok": True, "cancelled": []}

    monkeypatch.setattr(routes.desk, "opens_a_position", lambda order: order.side == "BUY")
    monkeypatch.setattr(routes.desk, "place_order", place_order)
    monkeypatch.setattr(routes.desk, "cancel_order", cancel_order)
    monkeypatch.setattr(routes.desk, "cancel_orders_for_symbol", cancel_orders_for_symbol)
    guard = next(m for m in app.user_middleware if m.cls is RequestGuardMiddleware)
    monkeypatch.setitem(guard.kwargs, "policy", load_policy({"NOVA_ALLOWED_HOSTS": PHONE})[0])
    monkeypatch.setattr(app, "middleware_stack", None)
    try:
        yield TestClient(app), state
    finally:
        app.middleware_stack = None  # the next test rebuilds the stack with the app's own policy
        session.close()
        pin.reset_for_tests()


def _unlock(client: TestClient) -> dict:
    res = client.post("/api/phone/unlock", headers=REMOTE, json={"pin": PIN})
    assert res.status_code == 200, res.text
    return {**REMOTE, PHONE_SESSION_HEADER: res.json()["token"]}


def test_another_device_writes_to_the_phone_door_and_nowhere_else(phone):
    client, _state = phone
    # No desk key on the phone: the PIN opens its own door, and every other write is still refused.
    unlocked = _unlock(client)
    for res in (client.post("/api/ibkr/order", headers=unlocked, json={}),
                client.post("/api/desk/venue", headers=unlocked, json={"venue": "live"}),
                client.post("/api/ibkr/arm", headers=unlocked, json={"armed": True})):
        assert res.status_code == 403 and res.json()["reason"] == REASON_REMOTE_VIEW_ONLY


def test_a_locked_phone_sends_nothing(phone):
    client, state = phone
    for res in (client.post("/api/phone/order", headers=REMOTE, json=ORDER),
                client.post("/api/phone/order", headers={**REMOTE, PHONE_SESSION_HEADER: "guess"}, json=ORDER),
                client.delete("/api/phone/order/3", headers=REMOTE),
                client.delete("/api/phone/orders?symbol=F", headers=REMOTE),
                client.post("/api/phone/arm", headers=REMOTE, json={"armed": True})):
        assert res.status_code == 401 and res.json()["detail"]["reason"] == PHONE_LOCKED
    assert state["sent"] == []
    status = client.get("/api/phone", headers=REMOTE).json()
    assert (status["pin_set"], status["unlocked"], status["venue"]) == (True, False, "paper")
    # The phone's screens time the link and correct their clock against this.
    assert abs(status["now"] - time.time()) < 5


def test_the_pin_unlocks_and_wrong_pins_lock_it_out(phone, monkeypatch):
    client, _state = phone
    for _ in range(PHONE_PIN_MAX_FAILURES - 1):
        res = client.post("/api/phone/unlock", headers=REMOTE, json={"pin": "000000"})
        assert res.status_code == 403 and res.json()["detail"]["reason"] == PHONE_PIN_INVALID
    assert client.post("/api/phone/unlock", headers=REMOTE, json={"pin": "000000"}).json()["detail"]["reason"] == PHONE_PIN_LOCKED
    # Locked out: the right PIN waits too.
    assert client.post("/api/phone/unlock", headers=REMOTE, json={"pin": PIN}).json()["detail"]["reason"] == PHONE_PIN_LOCKED
    assert pin.check(PIN, now=pin._locked_until + 1) == (None, "")
    assert PHONE_PIN_LOCKOUT_SEC > 0
    monkeypatch.delenv(PHONE_PIN_HASH_ENV)
    monkeypatch.setattr(arm_pin, "read_hash", lambda name, **_: None)
    pin.reset_for_tests()
    assert pin.check(PIN)[0] == PHONE_PIN_NOT_SET
    assert client.get("/api/phone", headers=REMOTE).json()["pin_set"] is False


def test_a_pin_changed_on_the_pc_replaces_the_old_one_without_a_restart(monkeypatch, tmp_path):
    # The API loaded .env into its environment at start, so the environment still holds the old hash.
    import paths

    env_file = tmp_path / ".env"
    env_file.write_text(f"{PHONE_PIN_HASH_ENV}={arm_pin.hash_pin('111111', iterations=1000)}\n", encoding="utf-8")
    monkeypatch.setattr(paths, "env_file_path", lambda: env_file)
    monkeypatch.setenv(PHONE_PIN_HASH_ENV, arm_pin.hash_pin(PIN, iterations=1000))
    pin.reset_for_tests()
    assert pin.check("111111") == (None, "")
    assert pin.check(PIN)[0] == PHONE_PIN_INVALID
    # No line in the file: the environment's value still counts (a desk configured by environment alone).
    env_file.write_text("", encoding="utf-8")
    pin.reset_for_tests()
    assert pin.check(PIN) == (None, "")
    pin.reset_for_tests()


def test_a_buy_without_a_received_level_2_is_refused_and_a_sell_goes(phone):
    from phone.constants_phone import PHONE_NO_VIEW

    client, state = phone
    unlocked = _unlock(client)
    for view in ({"action_wall_ms": 1.0}, {"action_wall_ms": 1.0, "book": {"seq": 4}}, {"action_wall_ms": 1.0, "instance": "x"}):
        res = client.post("/api/phone/order", headers=unlocked, json={**ORDER, "view": view})
        assert res.status_code == 409 and res.json()["detail"]["reason"] == PHONE_NO_VIEW
        assert "Level 2" in res.json()["detail"]["error"]
    assert state["sent"] == []
    assert client.post("/api/phone/order", headers=unlocked, json={**ORDER, "side": "SELL", "view": {"action_wall_ms": 1.0}}).status_code == 200
    assert [o.side for o in state["sent"]] == ["SELL"]


def test_an_unlocked_phone_orders_on_paper_through_the_desks_own_handlers(phone):
    client, state = phone
    unlocked = _unlock(client)
    res = client.post("/api/phone/order", headers=unlocked, json={**ORDER, "order_type": "LMT", "limit_price": 12.5})
    assert res.json() == {"ok": True, "order_id": 7}
    order = state["sent"][0]
    assert (order.symbol, order.side, order.qty, order.order_type, order.limit_price) == ("F", "BUY", 1, "LMT", 12.5)
    # Paper is named on every send, so the door refuses it if the desk moved; a phone never shorts or brackets.
    assert (order.venue, order.short_entry, order.take_profit_price, order.stop_loss_price) == ("paper", False, None, None)
    assert order.client_timing is not None and order.view is not None
    client.delete("/api/phone/order/3", headers=unlocked)
    client.delete("/api/phone/orders?symbol=F", headers=unlocked)
    assert state["sent"][1:] == [("cancel", 3, "paper"), ("cancel_symbol", "F", False, "paper")]


def test_the_command_the_door_gets_names_paper():
    from routes.trading_execution import OrderRequest, _manual_order_command

    cmd = _manual_order_command(OrderRequest(symbol="F", side="BUY", qty=1, venue="paper"), "k", None, 0)
    assert (cmd.expected_venue, cmd.source, cmd.short_entry) == ("paper", "manual", False)


@pytest.mark.parametrize("venue", ["live", "sim"])
def test_off_paper_the_phone_sends_nothing_and_says_why(phone, venue):
    client, state = phone
    unlocked = _unlock(client)
    state["venue"] = venue
    for res in (client.post("/api/phone/order", headers=unlocked, json=ORDER),
                client.delete("/api/phone/order/3", headers=unlocked),
                client.delete("/api/phone/orders?symbol=F", headers=unlocked),
                client.post("/api/phone/arm", headers=unlocked, json={"armed": True})):
        assert res.status_code == 409 and res.json()["detail"]["reason"] == PHONE_NOT_PAPER
        assert "Paper only" in res.json()["detail"]["error"] and "Nothing was sent" in res.json()["detail"]["error"]
    assert state["sent"] == []


def test_an_order_without_its_timing_or_its_view_is_not_an_order(phone):
    client, state = phone
    unlocked = _unlock(client)
    for missing in ("client_timing", "view"):
        body = {k: v for k, v in ORDER.items() if k != missing}
        assert client.post("/api/phone/order", headers=unlocked, json=body).status_code == 422
    assert client.post("/api/phone/order", headers=unlocked, json={**ORDER, "short_entry": True, "side": "SHORT"}).status_code == 422
    assert state["sent"] == []


def test_the_phone_locks_paper_from_anywhere_and_unlocks_it_only_on_paper(phone, monkeypatch):
    from ibkr import safety

    client, state = phone
    calls = []
    monkeypatch.setattr(safety, "arm", lambda value, *, pin=None, actor="operator": calls.append((value, pin, actor)) or (None, ""))
    monkeypatch.setattr(safety, "armed", lambda: bool(calls and calls[-1][0]))
    unlocked = _unlock(client)
    assert client.post("/api/phone/arm", headers=unlocked, json={"armed": True}).json()["armed"] is True
    state["venue"] = "live"
    assert client.post("/api/phone/arm", headers=unlocked, json={"armed": False}).json()["armed"] is False
    # Never a PIN passed on: Live's own PIN rule is what refuses an arm if the desk moved.
    assert calls == [(True, None, "operator"), (False, None, "operator")]


def test_a_session_ends_on_lock_on_a_second_unlock_and_with_time(phone):
    client, _state = phone
    first = _unlock(client)
    second = _unlock(client)
    assert client.post("/api/phone/order", headers=first, json=ORDER).status_code == 401
    assert client.post("/api/phone/order", headers=second, json=ORDER).status_code == 200
    token = second[PHONE_SESSION_HEADER]
    assert session.valid(token, now=session._expires_at - 1) and not session.valid(token, now=session._expires_at)
    assert PHONE_SESSION_SEC == 8 * 3600
    assert client.post("/api/phone/lock", headers=second).json()["unlocked"] is False
    assert client.post("/api/phone/order", headers=second, json=ORDER).status_code == 401


def test_the_desk_on_this_pc_still_needs_its_key(phone):
    client, _state = phone
    local = {"host": "127.0.0.1:8000"}
    assert client.post("/api/ibkr/arm", headers=local, json={"armed": False}).status_code == 401
