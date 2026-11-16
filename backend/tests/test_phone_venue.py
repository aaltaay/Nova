"""The phone moves the desk's venue and the Sim's playhead (ADR 070, amendment 2026-11-13).

Each write goes through the desk's own handler -- ``POST /api/desk/venue`` and ``POST /api/sim/clock`` --
after the phone PIN. Before a switch, the phone's menu reads what leaving the venue would cancel."""
from __future__ import annotations

import pytest

from phone.constants_phone import PHONE_LOCKED
from tests.test_phone_orders import REMOTE, _unlock, phone  # noqa: F401 -- the fixture is used by name

SIM_ANSWER = {"sim": True, "paused": True, "minute_from_open": 30}


@pytest.fixture
def desk(monkeypatch):
    """The desk's venue route and Gateway call, stubbed: what the phone hands them is what is checked."""
    import routes.desk as desk_routes
    import sim.routes as sim_routes
    from ibkr import client

    seen = {"venue": [], "gateway": [], "clock": []}

    async def post_desk_venue(body):
        seen["venue"].append(body.venue)
        return {"ok": True, "venue": body.venue, "left": [{"symbol": "F", "text": "cancelled"}]}

    async def request_gateway_mode(mode):
        seen["gateway"].append(mode)
        return {"ok": True, "launch_action": "noop", "message": "already live"}

    def post_sim_clock(body):
        seen["clock"].append(dict(body))
        return SIM_ANSWER

    monkeypatch.setattr(desk_routes, "post_desk_venue", post_desk_venue)
    monkeypatch.setattr(client, "request_gateway_mode", request_gateway_mode)
    monkeypatch.setattr(sim_routes, "post_sim_clock", post_sim_clock)
    return seen


def test_a_locked_phone_moves_nothing(phone, desk):
    client, _state = phone
    for res in (client.post("/api/phone/venue", headers=REMOTE, json={"venue": "sim"}),
                client.post("/api/phone/sim/clock", headers=REMOTE, json={"paused": True})):
        assert res.status_code == 401 and res.json()["detail"]["reason"] == PHONE_LOCKED
    assert desk == {"venue": [], "gateway": [], "clock": []}


def test_the_phone_moves_the_desk_through_the_desks_own_route(phone, desk):
    client, _state = phone
    unlocked = _unlock(client)
    res = client.post("/api/phone/venue", headers=unlocked, json={"venue": "sim"})
    assert res.status_code == 200
    body = res.json()
    assert desk["venue"] == ["sim"] and desk["gateway"] == []
    assert body["left"] == [{"symbol": "F", "text": "cancelled"}] and body["gateway"] is None
    # The answer carries the phone's status, so the header follows at once.
    assert {"venue", "armed", "unlocked"} <= set(body)


def test_a_move_to_live_asks_for_the_live_gateway_as_the_desks_pill_does(phone, desk, monkeypatch):
    from ibkr import client as ib

    client, _state = phone
    unlocked = _unlock(client)
    assert client.post("/api/phone/venue", headers=unlocked, json={"venue": "live"}).json()["gateway"] is None
    assert desk["gateway"] == ["live"]

    async def starting(mode):
        return {"ok": True, "launch_action": "restart", "message": "Starting the live Gateway"}

    monkeypatch.setattr(ib, "request_gateway_mode", starting)
    said = client.post("/api/phone/venue", headers=unlocked, json={"venue": "live"}).json()
    assert said["gateway"] == "Starting the live Gateway"


def test_an_unknown_venue_is_not_a_venue(phone, desk):
    client, _state = phone
    unlocked = _unlock(client)
    assert client.post("/api/phone/venue", headers=unlocked, json={"venue": "bank"}).status_code == 422
    assert desk["venue"] == []


def test_the_menu_reads_what_leaving_would_change(phone, monkeypatch):
    """The padlock is all a switch changes now: the Bot and Nova's own entries retired with the bots (ADR 072)."""
    from agent_desk import safety

    client, state = phone
    state["venue"] = "paper"
    monkeypatch.setattr(safety, "switch_changes", lambda old: (
        [{"kind": "armed", "text": "The desk is armed on Paper: switching disarms it"}], []))
    # A read: no session needed, and another device may make it.
    res = client.get("/api/phone/venue/effects", headers=REMOTE)
    assert res.status_code == 200
    assert res.json() == {"venue": "paper", "unknown": [], "lines": [
        "The desk is armed on Paper: switching disarms it"]}


def test_a_check_that_cannot_be_read_is_unknown_never_nothing(phone, monkeypatch):
    from agent_desk import safety

    client, _state = phone
    monkeypatch.setattr(safety, "switch_changes", lambda old: ([], [{"kind": "armed", "error": "x"}]))
    body = client.get("/api/phone/venue/effects", headers=REMOTE).json()
    assert body["lines"] == [] and body["unknown"] == ["armed"]


def test_nothing_waiting_reads_as_no_lines(phone, monkeypatch):
    from agent_desk import safety

    client, _state = phone
    monkeypatch.setattr(safety, "switch_changes", lambda old: ([], []))
    assert client.get("/api/phone/venue/effects", headers=REMOTE).json() == {"venue": "paper", "lines": [], "unknown": []}


def test_the_sim_playhead_goes_through_the_desks_own_clock_route(phone, desk):
    client, _state = phone
    unlocked = _unlock(client)
    assert client.post("/api/phone/sim/clock", headers=unlocked, json={"paused": False}).json() == SIM_ANSWER
    client.post("/api/phone/sim/clock", headers=unlocked, json={"minute_from_open": 29, "symbol": "F"})
    assert desk["clock"] == [{"paused": False}, {"minute_from_open": 29, "symbol": "F"}]


@pytest.mark.parametrize("body", [
    {}, {"symbol": "F"}, {"follow_wall": True}, {"session_date": "2026-11-12"},
    {"paused": True, "second_from_open": 5}, {"minute_from_open": 2.5}, {"minute_from_open": True},
])
def test_the_phone_asks_the_sim_clock_for_a_pause_or_a_minute_only(phone, desk, body):
    client, _state = phone
    unlocked = _unlock(client)
    assert client.post("/api/phone/sim/clock", headers=unlocked, json=body).status_code == 422
    assert desk["clock"] == []


def test_a_switch_names_only_the_padlock(monkeypatch):
    """No Bot to turn off and no Nova entry to cancel (ADR 072): an armed desk is the one thing a switch changes."""
    from agent_desk import safety
    from ibkr import safety as ibkr_safety

    monkeypatch.setattr(ibkr_safety, "armed", lambda: True)
    items, unknown = safety.switch_changes("paper")
    assert unknown == []
    assert [i["kind"] for i in items] == ["armed"]
    assert items[0]["text"] == "The desk is armed on Paper: switching disarms it"
    monkeypatch.setattr(ibkr_safety, "armed", lambda: False)
    assert safety.switch_changes("paper") == ([], [])
