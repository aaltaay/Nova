"""The brain's door on Paper (ADR 072 decision 10, ``bot.md`` "The brain's door"): its session, its lane, its limits,
and its orders end to end through the real execution door and the real Paper broker on a scratch account.

The market is faked (last / bid / ask by symbol); the clock is pinned to Wednesday 2026-10-07.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from brain import book, rules, session, watcher
from brain.constants_brain import BRAIN_HEARTBEAT_STALE_SEC
from execution import inflight, service, telemetry
from ibkr import client as ibkr_client
from ibkr import safety as _safety
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests as reset_brokers
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue
from tests.bot_helpers import headers

ET = ZoneInfo("America/New_York")
LIMITS = {"max_shares": 1000, "risk_usd": 150, "budget_usd": 25_000, "flat_by": "15:55"}
GOOD = {"symbol": "SMPL", "qty": 500, "limit": 4.25, "stop": 4.00, "target": 6.00, "why": "the first +50% print"}


def at(clock: str, day: str = "2026-10-07") -> float:
    return datetime.fromisoformat(f"{day}T{clock}").replace(tzinfo=ET).timestamp()


class Market:
    def __init__(self) -> None:
        self.px = {"SMPL": [4.20, 4.19, 4.21], "GAPX": [1.90, 1.89, 1.91]}
        self.now = at("10:30:00")

    def reference(self, symbol):
        got = self.px.get(symbol)
        return Reference(*got, live=True) if got else Reference(None, live=True)

    def admission(self, symbol):
        return (True, "OK", None) if symbol in self.px else (False, "dark", "PRACTICE_NO_LIVE_PRINT")

    def prints_between(self, symbol, after_ts, through_ts):
        return []

    def bid_at(self, symbol, ts):
        return self.px[symbol][1]

    def now_ts(self):
        return self.now

    def session_close_ts(self, ts):
        return ts + 86_400


@pytest.fixture
def paper(monkeypatch, short_market_open):
    """The desk on Paper and armed, the brain's switch On, every lane's lines up, the view lock clear, 10:30 ET."""
    import ibkr.depth as depth_mod
    import market
    from agent_trader import clock as agent_clock
    from ibkr import tape_stream
    from line_lanes import lanes as lane_table
    from market_view import gate
    from short_sale import whatif
    from traders import switches

    reset_venue()
    reset_brokers()
    for mod in (service, inflight, telemetry):
        mod.reset_for_tests()
    m = Market()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: m)
    monkeypatch.setattr("practice.reference.LiveReference", lambda: m)
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    monkeypatch.setattr(ibkr_client, "is_ready", lambda: True)

    async def _no_answer(*args, **kwargs):
        return None

    async def _noop(symbol):
        return None

    monkeypatch.setattr(whatif, "request", lambda *a, **k: False)
    monkeypatch.setattr(whatif, "ask", _no_answer)
    monkeypatch.setattr(market, "now_et", lambda: datetime.fromtimestamp(m.now, tz=ET))
    monkeypatch.setattr(agent_clock, "now", lambda: m.now)             # Claude's seat reads the same clock
    monkeypatch.setattr(gate, "desk_lock", lambda symbol, **kw: None)
    monkeypatch.setattr(lane_table, "_ask", _noop)                    # no IBKR here: a lane's lines are "up" below
    monkeypatch.setattr(lane_table, "_end", lambda symbol: None)
    monkeypatch.setattr(depth_mod, "is_live", lambda s: s.upper() in lane_table.table().stocks())
    monkeypatch.setattr(tape_stream, "is_subscribed", lambda s: s.upper() in lane_table.table().stocks())
    monkeypatch.setenv("NOVA_API_KEY", "agent-test-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    from main import app

    switches.set_switch("brain", True, "test")                        # the operator switched the brain On
    yield SimpleNamespace(market=m, broker=for_venue("paper"), client=TestClient(app), key=headers("agent-test-key"))
    for mod in (service, inflight, telemetry):
        mod.reset_for_tests()
    reset_brokers()
    reset_venue()


def _brain(p, sid: str = "brain-1", symbol: str | None = "SMPL") -> dict:
    h = {**p.key, "X-Nova-Brain-Session": sid}
    got = p.client.post("/api/brain/claim", headers=h)
    assert got.status_code == 200, got.text
    if symbol:
        watched = p.client.post("/api/brain/watch", headers=h, json={"symbol": symbol, "why": "first +50% print"})
        assert watched.status_code == 200, watched.text
    return h


# -- the session ------------------------------------------------------------------------------------------
def test_one_program_holds_the_door_until_its_heartbeat_is_stale():
    assert session.claim("a", now=1000.0) is True and session.connected(now=1001.0)
    with pytest.raises(session.Held):
        session.claim("b", now=1000.0 + BRAIN_HEARTBEAT_STALE_SEC - 1)
    with pytest.raises(session.NotClaimed):
        session.beat("b", now=1001.0)
    late = 1000.0 + BRAIN_HEARTBEAT_STALE_SEC + 1
    assert not session.connected(now=late)
    assert session.went_silent(now=late) is True and session.went_silent(now=late) is False     # said once
    assert session.claim("b", now=late) is True and session.view("b", now=late)["mine"] is True


def test_a_write_needs_the_desk_key_and_the_claimed_session(paper):
    no_key = paper.client.post("/api/brain/claim", headers={"X-Nova-Brain-Session": "brain-1"})
    assert no_key.status_code in (401, 403)
    h = _brain(paper, symbol=None)
    other = {**paper.key, "X-Nova-Brain-Session": "someone-else"}
    assert paper.client.post("/api/brain/claim", headers=other).json()["detail"]["reason"] == "BRAIN_HELD"
    got = paper.client.post("/api/brain/order", headers=other, json=GOOD)
    assert got.status_code == 409 and got.json()["detail"]["reason"] == "BRAIN_NOT_CLAIMED"
    assert paper.client.post("/api/brain/heartbeat", headers=h).json()["session"]["mine"] is True


# -- the lane ---------------------------------------------------------------------------------------------
def test_the_brain_names_lane_three_and_the_lanes_route_says_so(paper):
    h = _brain(paper)
    lanes = paper.client.get("/api/ibkr/lanes").json()
    assert lanes["schema_version"] == 2 and "bots" not in lanes
    assert lanes["brain"]["symbol"] == "SMPL" and lanes["brain"]["why"] == "first +50% print" and lanes["brain"]["depth"]
    status = paper.client.get("/api/brain", headers=h).json()
    assert status["lane"]["symbol"] == "SMPL" and status["can_enter"] is True and status["connected"] is True
    gone = paper.client.post("/api/brain/watch", headers=h, json={"symbol": None})
    assert gone.json()["lane"] == {"symbol": None, "why": None, "since": None, "depth": False, "tape": False}


def test_the_lane_is_the_brains_even_while_its_switch_is_off(paper):
    from traders import switches

    switches.set_switch("brain", False, "test")
    h = _brain(paper)
    assert paper.client.get("/api/ibkr/lanes").json()["brain"]["symbol"] == "SMPL"
    got = paper.client.post("/api/brain/order", headers=h, json=GOOD)
    assert got.status_code == 409 and got.json()["detail"]["reason"] == "BRAIN_SWITCH_OFF"


# -- its limits -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("change,words", [
    ({"qty": 1001, "stop": 4.20}, "over the brain's 1,000 a trade"),
    ({"qty": 12.5}, "whole number"),
    ({"stop": 4.30}, "must be under the limit"),
    ({"stop": 3.90}, "over the brain's $150 a trade"),
    ({"target": 4.25}, "needs a target above its limit"),
])
def test_an_entrys_own_numbers_stay_inside_the_brains_limits(change, words):
    assert words in rules.shape_refusal({**GOOD, **change}, LIMITS)
    assert rules.shape_refusal(GOOD, LIMITS) is None


def test_the_door_says_why_in_its_own_order(paper, monkeypatch):
    from agent_trader import halts
    from sim import mode

    h = _brain(paper)

    def refused(body=GOOD):
        got = paper.client.post("/api/brain/order", headers=h, json=body)
        assert got.status_code == 409, got.text
        return got.json()["detail"]["reason"]

    assert refused({**GOOD, "symbol": "GAPX", "limit": 1.91, "stop": 1.80, "target": 2.50}) == "BRAIN_NO_LINE"
    monkeypatch.setattr(halts, "halted", lambda sym: True)
    assert refused() == "BRAIN_HALTED"
    monkeypatch.setattr(halts, "halted", lambda sym: False)
    paper.market.now = at("15:55:00")
    assert refused() == "BRAIN_PAST_FLAT_BY"
    paper.market.now = at("10:30:00")
    monkeypatch.setattr(book, "day_pnl", lambda: -500.0)
    assert refused() == "BRAIN_DAY_STOP"
    monkeypatch.setattr(mode, "venue", lambda: "sim")
    assert refused() == "BRAIN_NOT_PAPER"
    assert [e["kind"] for e in session.events(paper.market.now)].count("refused") == 5


# -- end to end on Paper ----------------------------------------------------------------------------------
def test_an_entry_rests_its_stop_and_target_and_is_the_brains_on_the_books(paper):
    h = _brain(paper)
    got = paper.client.post("/api/brain/order", headers=h, json={**GOOD, "limit": 4.10, "stop": 3.90})
    assert got.status_code == 200, got.text
    rows = book.working()
    assert {r["leg_role"] for r in rows} == {"parent", "target", "stop"}
    assert all(r["order_origin"] == "brain" and r["order_source"] == "bot" for r in rows)
    traders = paper.client.get("/api/traders").json()["traders"]["brain"]
    assert traders["state"] == "buy_set" and traders["text"] == "Brain · Buy set SMPL" and traders["connected"] is True
    assert traders["lane"] == {"symbol": "SMPL", "depth": True, "tape": True, "why": "first +50% print"}
    assert traders["note"]["text"] == "the first +50% print" and traders["today"]["loss_limit_usd"] == -500.0


def test_a_fill_is_one_position_its_stop_only_moves_up_and_close_sells_it(paper):
    h = _brain(paper)
    assert paper.client.post("/api/brain/order", headers=h, json=GOOD).status_code == 200
    assert book.positions() == {"SMPL": {"qty": 500.0, "avg_cost": pytest.approx(4.21)}}      # marketable: at the ask
    traders = paper.client.get("/api/traders").json()["traders"]["brain"]
    assert traders["state"] == "in_trade" and traders["text"].startswith("Brain · In SMPL")
    second = paper.client.post("/api/brain/order", headers=h, json=GOOD)
    assert second.json()["detail"]["reason"] == "BRAIN_IN_TRADE"
    down = paper.client.post("/api/brain/stop", headers=h, json={"symbol": "SMPL", "stop": 3.95})
    assert down.status_code == 409 and "only moves up" in down.json()["detail"]["error"]
    up = paper.client.post("/api/brain/stop", headers=h, json={"symbol": "SMPL", "stop": 4.10})
    assert up.status_code == 200, up.text
    assert float(book.stop_of("SMPL")["stop_price"]) == 4.10
    closed = paper.client.post("/api/brain/close", headers=h, json={"symbol": "SMPL", "why": "the forecast turned"})
    assert closed.status_code == 200, closed.text
    assert book.positions() == {} and book.working() == []
    assert closed.json()["position"] is None


def test_nova_sells_the_brains_shares_at_its_flat_by_time(paper):
    h = _brain(paper)
    asyncio.run(watcher.run_pass(now=0.0))                              # the watcher's first look: flat
    assert paper.client.post("/api/brain/order", headers=h, json=GOOD).status_code == 200
    asyncio.run(watcher.run_pass(now=1.0))                              # before flat by: nothing is sold
    assert book.positions()["SMPL"]["qty"] == 500
    paper.market.now = at("15:55:30")
    asyncio.run(watcher.run_pass(now=1000.0))
    assert book.positions() == {} and book.working() == []
    asyncio.run(watcher.run_pass(now=1005.0))                           # the next look says the close
    kinds = [e["kind"] for e in session.events(paper.market.now)]
    assert kinds[:3] == ["close", "flat_by", "fill"]


def test_off_hands_the_trade_to_you_and_the_brain_leaves_it_alone(paper):
    h = _brain(paper)
    assert paper.client.post("/api/brain/order", headers=h, json=GOOD).status_code == 200
    off = paper.client.put("/api/traders/brain/switch", headers=paper.key, json={"on": False})
    assert off.status_code == 200, off.text
    brain = off.json()["traders"]["brain"]
    assert brain["state"] == "off" and brain["text"] == "Brain · Off · SMPL is yours to close"
    assert brain["handed"][0]["symbol"] == "SMPL" and brain["handed"][0]["stop_price"] == 4.0
    assert book.positions() == {} and book.positions(with_handed=True)["SMPL"]["qty"] == 500
    paper.market.now = at("15:56:00")
    asyncio.run(watcher.run_pass(now=2000.0))                           # flat by never sells what is yours
    assert book.positions(with_handed=True)["SMPL"]["qty"] == 500
    legs = {r["leg_role"] for r in book.working()}
    assert legs == {"target", "stop"}                                   # and never cancels the exits that protect it
    assert book.working(with_handed=False) == [] and book.stop_of("SMPL") is None
    moved = paper.client.post("/api/brain/stop", headers=h, json={"symbol": "SMPL", "stop": 4.10})
    assert moved.status_code == 409                                     # a handed trade's stop is not the brain's to move
    assert paper.client.post("/api/brain/close", headers=h, json={"symbol": "SMPL"}).status_code == 200
    assert book.positions(with_handed=True)["SMPL"]["qty"] == 500 and legs == {r["leg_role"] for r in book.working()}
    assert "handed" in [e["kind"] for e in session.events(paper.market.now)]


def test_two_entries_at_once_never_both_pass(paper, monkeypatch):
    """Codex review on PR #1332: the check and the send are one step, so the second entry reads the first one's order."""
    from fastapi import HTTPException

    from brain import orders, routes

    _brain(paper)
    real = orders.send_entry

    async def slow(order):
        await asyncio.sleep(0.01)                                       # the door is busy: the other request runs meanwhile
        return await real(order)

    monkeypatch.setattr(orders, "send_entry", slow)

    async def both():
        body = routes.OrderBody(**GOOD)
        return await asyncio.gather(routes.place(body, "brain-1"), routes.place(body, "brain-1"), return_exceptions=True)

    first, second = asyncio.run(both())
    assert isinstance(first, dict) and isinstance(second, HTTPException)
    assert second.detail["reason"] == "BRAIN_IN_TRADE"
    assert book.positions()["SMPL"]["qty"] == 500


def test_only_the_operator_flips_the_brains_switch(paper):
    h = _brain(paper)
    got = paper.client.put("/api/traders/brain/switch", headers=h, json={"on": False})
    assert got.status_code == 409 and got.json()["detail"]["reason"] == "TRADER_OPERATOR_ONLY"


# -- its pill ---------------------------------------------------------------------------------------------
def test_the_pill_says_when_the_brains_program_is_not_running(paper):
    brain = paper.client.get("/api/traders").json()["traders"]["brain"]
    assert brain["on"] is True and brain["connected"] is False
    assert brain["text"] == "Brain · On · its program is not running" and brain["state"] == "watching"
    _brain(paper)
    brain = paper.client.get("/api/traders").json()["traders"]["brain"]
    assert brain["text"] == "Brain · Watching SMPL"
    paper.client.post("/api/brain/note", headers={**paper.key, "X-Nova-Brain-Session": "brain-1"}, json={
        "text": "Reading three runners", "reading": [{"symbol": "smpl", "text": "up 62%, book thin above"},
                                                      {"symbol": "GAPX", "text": "up 41%, waiting for +50%"}]})
    brain = paper.client.get("/api/traders").json()["traders"]["brain"]
    assert brain["reading"] == [{"symbol": "SMPL", "text": "up 62%, book thin above", "source": "lane"},
                                {"symbol": "GAPX", "text": "up 41%, waiting for +50%", "source": "level1"}]


def test_the_day_stop_reads_done_for_today_and_on_is_refused(paper, monkeypatch):
    from traders import switches

    monkeypatch.setattr(book, "day_pnl", lambda: -512.0)
    switches.set_switch("brain", False, "test")
    brain = paper.client.get("/api/traders").json()["traders"]["brain"]
    assert brain["done_for_today"] is True and brain["state"] == "done" and brain["can_turn_on"] is False
    got = paper.client.put("/api/traders/brain/switch", headers=paper.key, json={"on": True})
    assert got.status_code == 409 and got.json()["detail"]["reason"] == "TRADER_DAY_STOP"


def test_on_live_the_brain_opens_nothing_and_its_paper_trade_keeps_working(paper):
    """ADR 072 Amendment 3 (the operator, 2026-11-18: "Pause it, as now"): on Live the brain opens nothing, its
    switch and lane stay as they were, and its open Paper trade keeps its stop -- which still moves up -- and closes."""
    h = _brain(paper)
    assert paper.client.post("/api/brain/order", headers=h, json=GOOD).status_code == 200
    set_venue("live")
    assert _safety.armed() is False                                  # the venue change disarmed the desk
    brain = paper.client.get("/api/traders").json()["traders"]["brain"]
    assert brain["on"] is True and brain["lane"]["symbol"] == "SMPL"    # Live switches nothing Off and moves no lane
    entry = paper.client.post("/api/brain/order", headers=h, json={**GOOD, "symbol": "GAPX", "limit": 1.92,
                                                                    "stop": 1.80, "target": 2.40})
    assert entry.status_code == 409 and entry.json()["detail"]["reason"] == "BRAIN_NOT_PAPER"
    assert paper.client.post("/api/brain/arm", headers=h).json()["detail"]["reason"] == "BRAIN_NOT_PAPER"
    up = paper.client.post("/api/brain/stop", headers=h, json={"symbol": "SMPL", "stop": 4.10})
    assert up.status_code == 200, up.text
    assert float(book.stop_of("SMPL")["stop_price"]) == 4.10 and book.positions()["SMPL"]["qty"] == 500
    assert paper.client.post("/api/brain/close", headers=h, json={"symbol": "SMPL"}).status_code == 200
    assert book.positions() == {} and book.working() == []


def test_leaving_paper_cancels_the_brains_waiting_buy_and_back_on_paper_it_trades_again(paper):
    """ADR 072 Amendment 4: a buy still waiting on Paper is cancelled on the way to Live, so nothing opens during the
    pause. The switch names it before and after, the pill says paused, the lane stays, and back on Paper the brain
    arms the desk itself and trades."""
    from agent_desk import safety as desk_safety

    h = _brain(paper)
    waiting = {**GOOD, "limit": 4.10, "stop": 3.90}
    assert paper.client.post("/api/brain/order", headers=h, json=waiting).status_code == 200
    assert len(book.entries()) == 1 and book.positions() == {}
    items, unknown = desk_safety.switch_changes("paper")              # what the phone's venue menu reads first
    assert unknown == [] and [i["kind"] for i in items] == ["armed", "trader_entry"]
    assert items[1]["text"] == "The brain's buy on SMPL is waiting: switching cancels it"

    moved = paper.client.post("/api/desk/venue", headers=paper.key, json={"venue": "live"})
    assert moved.status_code == 200, moved.text
    left = moved.json()["left"]
    assert [(r["venue"], r["symbol"], r["by"]) for r in left] == [("paper", "SMPL", "brain")]
    assert "was cancelled: the desk left Paper for Live" in left[0]["text"]
    assert book.working() == [] and book.positions() == {}            # the entry took its waiting exits along
    gone = for_venue("paper").ledger.order_row(left[0]["order_id"])
    assert gone["reason_code"] == "TRADER_PAUSED"
    brain = paper.client.get("/api/traders").json()["traders"]["brain"]
    assert brain["on"] is True and brain["lane"]["symbol"] == "SMPL"   # no switch flipped, no lane moved
    assert brain["paused"]["reason"] == "TRADER_PAUSED" and brain["paused"]["venue"] == "live"
    assert brain["text"] == "Brain · Paper only · paused while you're on Live"
    status = paper.client.get("/api/brain", headers=h).json()
    assert status["trades_on"] == "paper" and status["paused"]["venue"] == "live"
    assert status["can_enter"] is False and status["why_not"]["code"] == "BRAIN_NOT_PAPER"
    assert [e["kind"] for e in session.events(paper.market.now)][:2] == ["paused", "paused"]
    assert desk_safety.switch_changes("live") == ([], [])

    back = paper.client.post("/api/desk/venue", headers=paper.key, json={"venue": "paper"})
    assert back.status_code == 200 and back.json()["left"] == []
    assert session.events(paper.market.now)[0]["kind"] == "resumed"
    status = paper.client.get("/api/brain", headers=h).json()
    assert status["paused"] is None and status["can_enter"] is True and status["lane"]["symbol"] == "SMPL"
    assert _safety.armed() is False                                  # the round trip left the desk disarmed
    assert paper.client.post("/api/brain/arm", headers=h).status_code == 200
    assert paper.client.post("/api/brain/order", headers=h, json=GOOD).status_code == 200
    assert book.positions()["SMPL"]["qty"] == 500


@pytest.mark.parametrize("venue", ["live", "sim"])
def test_a_paused_brains_paper_trade_stays_on_its_pill(paper, venue):
    """Its figures are its own account's: Paper, whatever the desk shows. On Sim they used to read Sim's account, so
    the open Paper trade vanished from the pill."""
    h = _brain(paper)
    assert paper.client.post("/api/brain/order", headers=h, json=GOOD).status_code == 200
    set_venue(venue, persist=False)
    brain = paper.client.get("/api/traders").json()["traders"]["brain"]
    assert brain["position"]["symbol"] == "SMPL" and brain["position"]["qty"] == 500
    assert brain["text"].startswith("Brain · In SMPL") and brain["text"].endswith(f" on Paper · paused while you're on {venue.capitalize()}")
    assert brain["paused"]["venue"] == venue and brain["state"] == "in_trade"
    status = paper.client.get("/api/brain", headers=h).json()
    assert status["position"]["symbol"] == "SMPL" and status["limits"]["budget_used_usd"] > 0
    assert float(book.stop_of("SMPL")["stop_price"]) == 4.00            # its exits keep resting on Paper
    set_venue("paper", persist=False)
    assert paper.client.get("/api/traders").json()["traders"]["brain"]["paused"] is None


def test_a_brain_that_is_off_is_not_paused(paper):
    from traders import pause, switches

    switches.set_switch("brain", False, "test")
    set_venue("live")
    brain = paper.client.get("/api/traders").json()["traders"]["brain"]
    assert brain["paused"] is None and brain["text"] == "Brain · Off" and pause.paused("brain") is None
    assert session.events(paper.market.now) == []                       # nothing to say: it was not trading


def test_a_padlock_you_locked_is_the_brains_why_not(paper):
    """Its arm would be refused, so its status says so before it tries: never a silent block."""
    h = _brain(paper)
    _safety.arm(False, actor="operator")
    status = paper.client.get("/api/brain", headers=h).json()
    assert status["can_enter"] is False and status["why_not"]["code"] == "BRAIN_PADLOCK"
    assert "You locked the padlock" in status["why_not"]["text"]
    assert paper.client.post("/api/brain/arm", headers=h).json()["detail"]["reason"] == "BRAIN_PADLOCK"
    _safety.arm(True, actor="operator")
    assert paper.client.get("/api/brain", headers=h).json()["can_enter"] is True


def test_a_venue_change_never_fails_on_a_traders_book(paper, monkeypatch):
    from traders import off

    def unreadable(*args, **kwargs):
        raise RuntimeError("the ledger is locked")

    _brain(paper)
    monkeypatch.setattr(off, "cancel_entries", unreadable)
    moved = paper.client.post("/api/desk/venue", headers=paper.key, json={"venue": "live"})
    assert moved.status_code == 200 and moved.json()["venue"] == "live" and moved.json()["left"] == []
    said = session.events(paper.market.now)[0]
    assert said["kind"] == "paused" and "could not read the brain's orders on Paper" in said["text"]


def test_only_a_traders_own_stop_moved_up_may_name_paper(paper):
    """The door's own check of a stop raise (``execution.stop_raise``): nothing else shaped like it names a venue."""
    from execution import venue_door
    from execution.models import ExecutionCommand

    h = _brain(paper)
    assert paper.client.post("/api/brain/order", headers=h, json=GOOD).status_code == 200
    rows = {r["leg_role"]: int(r["order_id"]) for r in book.working()}

    def refusal(**change):
        fields = {"operation": "replace", "idempotency_key": "raise", "source": "cancel_working", "symbol": "SMPL",
                  "order_id": rows["stop"], "stop_price": 4.10, "target_venue": "paper", "origin": "brain", **change}
        return venue_door.target_refusal(ExecutionCommand(**fields))

    assert refusal() is None
    assert "only moves up" in refusal(stop_price=3.95)
    assert "only moves up" in refusal(stop_price=4.00)                  # the same price is not a raise
    assert "not The brain's own resting stop" in refusal(order_id=rows["target"])
    assert "not Claude's own resting stop" in refusal(origin="claude")
    assert "not working on Paper" in refusal(order_id=9999)
    assert "never go to Live" in refusal(target_venue="live")
    assert "on Paper only" in refusal(target_venue="sim")
    for not_a_raise in ({"limit_price": 4.30}, {"resize_qty": 100.0}, {"source": "bot"}, {"origin": None},
                        {"origin": "loss_limit"}):
        assert "only the kill switch's cancels" in refusal(**not_a_raise)
    assert paper.client.put("/api/traders/brain/switch", headers=paper.key, json={"on": False}).status_code == 200
    assert "handed to you" in refusal()                                 # Off handed SMPL: its stop is yours to move


def test_a_stop_raise_is_refused_when_papers_book_cannot_be_read(paper, monkeypatch):
    from execution import stop_raise
    from execution.models import ExecutionCommand

    def unread(venue):
        raise RuntimeError("ledger locked")

    monkeypatch.setattr(practice_broker, "for_venue", unread)
    cmd = ExecutionCommand(operation="replace", idempotency_key="raise-unread", source="cancel_working",
                           symbol="SMPL", order_id=1, stop_price=4.10, target_venue="paper", origin="brain")
    assert stop_raise.is_one(cmd) and "could not be read" in stop_raise.refusal(cmd, "paper")


def test_the_brain_never_reaches_live(paper):
    from execution import venue_door
    from execution.models import ExecutionCommand

    cmd = ExecutionCommand(operation="place", idempotency_key="b-live", source="flatten", symbol="SMPL", side="SELL",
                           qty=1.0, order_type="MKT", target_venue="live", origin="brain")
    assert "never go to Live" in venue_door.target_refusal(cmd)
    assert "Paper only" in venue_door.wrong_venue(
        ExecutionCommand(operation="cancel", idempotency_key="b-sim", source="bot", symbol="SMPL", order_id=1,
                         origin="brain"), "sim")
