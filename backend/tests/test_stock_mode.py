"""Who trades the stock (ADR 037): the per-stock switch, Auto-entry, Approve and taking over the exit.

The trade tests run the real execution door and the real practice broker on the Paper venue against a
fake live market (``FakeLive``), and drive the runner one tick at a time with a pinned clock.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from bot.audit import list_entries
from bot.first_pullback import orders as fp_orders
from bot.first_pullback import runner as bot_runner
from bot.persist import load_session, save_session
from constants_stock_mode import STOCK_MODE_ENTRY_TTL_SEC
from execution import inflight
from ibkr import safety as _safety
from main import app
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests as reset_brokers
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue
from stock_mode import runner, store
from tests.bot_helpers import headers, ready_l2

NOW = 1_790_000_000.0
SYM = "IMCC"
client = TestClient(app)


class FakeLive:
    """A live market that prices IMCC at 9.98 x 10.02 (last 10.00) and never prints on its own."""

    def __init__(self) -> None:
        self.now = NOW
        self.bid, self.ask, self.last = 9.98, 10.02, 10.00

    def reference(self, symbol: str) -> Reference:
        if symbol != SYM:
            return Reference(None, live=True)
        return Reference(self.last, self.bid, self.ask, live=True)

    def admission(self, symbol: str):
        return (True, "OK", None) if symbol == SYM else (False, "dark", "PRACTICE_NO_LIVE_PRINT")

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return self.now

    def session_close_ts(self, ts: float) -> float:
        return ts + 86_400


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("NOVA_API_KEY", "stock-mode-test-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    return "stock-mode-test-key"


@pytest.fixture
def paper(monkeypatch, api_key):
    """Paper venue, the desk armed, a fake live market, the runner's clock pinned."""
    reset_venue()
    reset_brokers()
    inflight.reset_for_tests()
    store.reset_for_tests()
    fake = FakeLive()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: fake)
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    clock = {"t": NOW}
    runner.reset_for_tests(lambda: clock["t"])
    yield SimpleNamespace(broker=for_venue("paper"), ref=fake, clock=clock, key=api_key)
    runner.reset_for_tests()
    store.reset_for_tests()
    inflight.reset_for_tests()
    reset_brokers()
    reset_venue()


def trigger(**over) -> dict:
    setup = {"kind": "first_pullback", "trigger": 10.01, "entry": 10.02, "stop": 9.89, "risk": 0.13,
             "target1": 10.28, "triggered_at": NOW, "trigger_price": 10.02, "nth": 1}
    setup.update(over.pop("setup", {}))
    event = {"symbol": SYM, "setup_id": f"{SYM}-2026-09-24-1790000000", "setup": setup,
             "tape": {"verdict": "go", "reasons": ["green on the tape"]}, "ts": NOW,
             "template_id": "default", "template_rev": 1, "template_name": "Default",
             "setup_type": "first_pullback", "source": "live"}
    event.update(over)
    return event


def tick(p, at: float | None = None) -> dict | None:
    if at is not None:
        p.clock["t"] = at
        p.ref.now = at
    asyncio.run(runner.tick())
    return store.trade("paper", SYM)


def put(p, buy: str, sell: str, risk: float | None = 20.0, sym: str = SYM):
    body = {"buy": buy, "sell": sell}
    if risk is not None:
        body["risk_usd"] = risk
    return client.put(f"/api/stock-mode/{sym}", json=body, headers=headers(p.key))


def mode_rows(outcome: str | None = None) -> list[dict]:
    return [r for r in list_entries(limit=100)
            if r["action"] == "stock_mode" and (outcome is None or r["outcome"] == outcome)]


# -- the switch ---------------------------------------------------------------------------
def test_every_stock_starts_at_signal_only_with_nothing_locked_on_paper(paper):
    body = client.get(f"/api/stock-mode/{SYM}").json()
    assert body["mode"] == "signal" and (body["buy"], body["sell"]) == ("you", "you")
    assert body["locks"] == {"buy": None, "sell": None} and body["venue"] == "paper"
    assert body["trade"] is None and body["approval"] is None and body["notes"] == []


def test_writes_need_the_desk_key(paper):
    assert client.put(f"/api/stock-mode/{SYM}", json={"buy": "nova", "sell": "you", "risk_usd": 20}).status_code == 401


def test_on_live_both_nova_sides_are_locked_and_say_why(paper):
    set_venue("live")
    body = client.get(f"/api/stock-mode/{SYM}").json()
    assert "never buys by itself" in body["locks"]["buy"] and "#604" in body["locks"]["sell"]
    r = put(paper, "nova", "you")
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_LIVE"
    r = put(paper, "you", "nova")
    assert r.status_code == 409 and "#604" in r.json()["detail"]["error"]
    assert put(paper, "you", "you").status_code == 200        # Signal only is always allowed


def test_off_the_live_edge_sim_is_a_replay_and_nova_is_locked(paper):
    set_venue("sim")                                          # conftest pins the live edge off
    r = put(paper, "nova", "you")
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_REPLAY"


def test_auto_entry_needs_the_risk_per_trade(paper):
    r = put(paper, "nova", "you", risk=None)
    assert r.status_code == 400 and r.json()["detail"]["reason"] == "STOCK_MODE_RISK"
    assert put(paper, "nova", "you", risk=0.5).status_code == 400


def test_the_four_modes_and_the_bot_list(paper):
    assert put(paper, "nova", "you").json()["mode"] == "auto_entry"
    assert put(paper, "you", "nova").json()["mode"] == "approve"
    body = put(paper, "nova", "nova").json()
    assert body["mode"] == "bot" and body["bot"]["on_list"] is True
    assert SYM in load_session()["symbol_allowlist"]
    assert put(paper, "you", "you").json()["mode"] == "signal"
    assert SYM not in load_session()["symbol_allowlist"]
    assert [r["inputs"]["to"] for r in mode_rows("set")] == ["auto_entry", "approve", "bot", "signal"]


def test_the_bots_list_is_the_truth_for_bot_at_strategy(paper):
    row = load_session()
    row["symbol_allowlist"] = [SYM]
    save_session(row)
    assert client.get(f"/api/stock-mode/{SYM}").json()["mode"] == "bot"


def test_sell_never_moves_to_nova_while_the_stock_is_held(paper):
    paper.broker.place(SYM, "BUY", 5, "MKT")
    r = put(paper, "you", "nova")
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_HELD"
    assert "You hold IMCC" in r.json()["detail"]["error"]


def test_a_venue_change_returns_every_stock_to_signal_only(paper):
    put(paper, "nova", "you")
    set_venue("sim")
    set_venue("paper")
    body = client.get(f"/api/stock-mode/{SYM}").json()
    assert body["mode"] == "signal"


def test_notes_say_what_will_keep_nova_from_acting(paper, monkeypatch):
    monkeypatch.setattr("ibkr.trading_allowed.places_allowed", lambda: (False, "disarmed"))
    notes = {n["id"]: n["text"] for n in put(paper, "nova", "you").json()["notes"]}
    assert "padlock" in notes["desk_disarmed"]
    assert "does not follow IMCC" in notes["not_followed"]


# -- Auto-entry ----------------------------------------------------------------------------------
def test_auto_entry_buys_the_go_trigger_sized_by_the_risk_and_never_sells(paper):
    put(paper, "nova", "you", risk=20.0)
    runner.submit(trigger())
    trade = tick(paper)
    assert trade["kind"] == "auto_entry" and trade["qty"] == 153      # floor(20 / 0.13)
    trade = tick(paper, NOW + 0.5)                                    # marketable at the ask: filled in the send
    assert trade["state"] == "holding" and trade["exits"] == "you" and trade["fill_price"] == 10.02
    assert paper.broker.ledger.held_qty(SYM) == 153.0
    assert paper.broker.ledger.working_orders() == []                 # no target, no stop: the exit is yours
    fills = [r for r in paper.broker.ledger.closed_orders() if r["status"] == "Filled"]
    assert {r["order_source"] for r in fills} == {"bot"}
    assert [r["outcome"] for r in mode_rows()][-2:] == ["sent", "filled"]
    view = client.get(f"/api/stock-mode/{SYM}").json()
    assert view["trade"]["exits"] == "you" and view["nova_entries_today"] == 1
    assert "the exit is yours" in view["last_event"]["text"]


def test_auto_entry_buys_once_per_stock_per_day(paper):
    put(paper, "nova", "you")
    runner.submit(trigger())
    tick(paper)
    tick(paper, NOW + 0.5)
    runner.submit(trigger(setup_id="SECOND", ts=NOW + 60, setup={"triggered_at": NOW + 60}))
    tick(paper, NOW + 60)
    [skip] = mode_rows("skipped")
    assert skip["inputs"]["code"] == "ENTRY_USED" and paper.broker.ledger.held_qty(SYM) == 153.0


@pytest.mark.parametrize("event, code", [
    (trigger(tape={"verdict": "wait", "reasons": ["a seller at 10.05"]}), "TAPE_NOT_GO"),
    (trigger(tape={"verdict": "blind"}), "TAPE_NOT_GO"),
    (trigger(ts=NOW - 30), "TRIGGER_STALE"),
])
def test_what_keeps_auto_entry_from_buying_is_said(paper, event, code):
    put(paper, "nova", "you")
    runner.submit(event)
    tick(paper)
    [skip] = mode_rows("skipped")
    assert skip["inputs"]["code"] == code
    assert paper.broker.ledger.held_qty(SYM) == 0.0
    assert client.get(f"/api/stock-mode/{SYM}").json()["last_event"]["text"].startswith("Nova did not buy")


def test_a_locked_padlock_keeps_auto_entry_from_buying(paper, monkeypatch):
    put(paper, "nova", "you")
    monkeypatch.setattr("ibkr.trading_allowed.places_allowed", lambda: (False, "disarmed"))
    runner.submit(trigger())
    tick(paper)
    [skip] = mode_rows("skipped")
    assert skip["inputs"]["code"] == "DESK_DISARMED"


def test_an_unfilled_entry_is_cancelled_after_the_ttl_as_a_miss(paper):
    put(paper, "nova", "you")
    runner.submit(trigger(setup={"entry": 9.95, "stop": 9.85, "target1": 10.15}))
    trade = tick(paper)
    assert trade["state"] == "entering"                               # 9.95 under the 10.02 ask: it rests
    tick(paper, NOW + STOCK_MODE_ENTRY_TTL_SEC + 0.5)
    trade = tick(paper, NOW + STOCK_MODE_ENTRY_TTL_SEC + 1)
    assert trade["state"] == "missed" and "not filled" in trade["note"]
    assert paper.broker.ledger.working_orders() == []
    assert client.get(f"/api/stock-mode/{SYM}").json()["nova_entries_today"] == 0


def test_turning_auto_entry_off_cancels_its_working_entry(paper):
    put(paper, "nova", "you")
    runner.submit(trigger(setup={"entry": 9.95, "stop": 9.85, "target1": 10.15}))
    tick(paper)
    assert paper.broker.ledger.working_orders()
    assert put(paper, "you", "you").status_code == 200
    assert paper.broker.ledger.working_orders() == []


def test_the_holding_trade_closes_when_you_sell(paper):
    put(paper, "nova", "you")
    runner.submit(trigger())
    tick(paper)
    tick(paper, NOW + 0.5)
    paper.broker.place(SYM, "SELL", 153, "MKT")
    trade = tick(paper, NOW + 2)
    assert trade["state"] == "closed" and trade["exit_reason"] == "outside"


def test_a_trigger_on_a_signal_only_stock_does_nothing(paper):
    runner.submit(trigger())
    assert tick(paper) is None and mode_rows() == []


# -- Approve --------------------------------------------------------------------------------
def lane(state: str = "armed", **over) -> dict:
    setup = {"trigger": 10.01, "entry": 10.02, "stop": 9.89, "target1": 10.28, "risk": 0.13,
             "triggered_at": NOW if state == "triggered" else None}
    setup.update(over.pop("setup", {}))
    row = {"setup_id": f"{SYM}-2026-09-24-1790000000", "setup_type": "first_pullback", "state": state,
           "reason": "", "setup": setup}
    row.update(over)
    return row


def approve_body(**over) -> dict:
    body = {"setup_id": f"{SYM}-2026-09-24-1790000000", "entry": 10.02, "stop": 9.89, "target": 10.28, "qty": 153}
    body.update(over)
    return body


class Receipt(SimpleNamespace):
    pass


@pytest.fixture
def sent(monkeypatch):
    """Capture the brackets Nova sends (the practice broker's own bracket tests cover the fills)."""
    calls: list[dict] = []

    async def send_bracket(trade):
        calls.append(dict(trade))
        return Receipt(ok=True, order_id=101, parent_order_id=101, target_order_id=102, stop_order_id=103,
                       error=None, reason_code=None)

    from stock_mode import orders as sm_orders

    monkeypatch.setattr(sm_orders, "send_bracket", send_bracket)
    # the stubbed legs rest at the broker (the practice broker's own bracket tests cover real fills)
    monkeypatch.setattr(sm_orders, "order_row",
                        lambda oid: {"order_id": oid, "status": "Submitted"} if oid in (101, 102, 103) else None)
    return calls


def test_approve_needs_the_approve_mode(paper, monkeypatch):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    r = client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_NOT_APPROVE"


def test_an_approval_binds_to_the_lanes_own_levels(paper, monkeypatch):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane(setup={"entry": 9.99, "stop": 9.86}))
    put(paper, "you", "nova")
    r = client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_PLAN_CHANGED"
    assert "9.99 / 9.86 / 10.28" in r.json()["detail"]["error"]


def test_an_approved_plan_is_sent_as_one_bracket_at_its_trigger(paper, monkeypatch, sent):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    put(paper, "you", "nova")
    r = client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    assert r.status_code == 200 and r.json()["approval"]["state"] == "waiting"
    runner.submit(trigger(setup_id="SOMETHING-ELSE"))
    tick(paper)
    assert sent == []                                                  # another setup's trigger sends nothing
    runner.submit(trigger())
    trade = tick(paper, NOW + 0.2)
    assert [(c["entry"], c["stop"], c["target"], c["qty"]) for c in sent] == [(10.02, 9.89, 10.28, 153)]
    assert trade["kind"] == "approve" and trade["exits"] == "nova"
    assert (trade["entry_order_id"], trade["target_order_id"], trade["stop_order_id"]) == (101, 102, 103)
    assert client.get(f"/api/stock-mode/{SYM}").json()["approval"]["state"] == "sent"


def test_a_trigger_the_tape_does_not_pass_withdraws_the_approval_and_says_why(paper, monkeypatch, sent):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    put(paper, "you", "nova")
    client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    runner.submit(trigger(tape={"verdict": "veto", "reasons": ["spread 0.08"]}))
    tick(paper)
    assert sent == []
    approval = client.get(f"/api/stock-mode/{SYM}").json()["approval"]
    assert approval["state"] == "withdrawn" and "VETO" in approval["reason"]


def test_a_rearm_at_other_levels_withdraws_the_approval(paper, monkeypatch, sent):
    state = {"lane": lane()}
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: state["lane"])
    put(paper, "you", "nova")
    client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    state["lane"] = lane(setup={"entry": 9.97, "stop": 9.89, "target1": 10.13})
    tick(paper, NOW + 3)
    approval = client.get(f"/api/stock-mode/{SYM}").json()["approval"]
    assert approval["state"] == "withdrawn" and "re-armed at 9.97" in approval["reason"]


def test_approve_now_sends_on_a_triggered_setup(paper, monkeypatch, sent):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane("triggered"))
    put(paper, "you", "nova")
    r = client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(now=True), headers=headers(paper.key))
    assert r.status_code == 200 and len(sent) == 1 and r.json()["trade"]["kind"] == "approve"
    assert r.json()["approval"]["state"] == "sent"


def test_cancel_approval_before_the_trigger(paper, monkeypatch, sent):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    put(paper, "you", "nova")
    client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    r = client.delete(f"/api/stock-mode/{SYM}/approve", headers=headers(paper.key))
    assert r.status_code == 200 and r.json()["approval"] is None
    runner.submit(trigger())
    tick(paper)
    assert sent == []


# -- taking over ----------------------------------------------------------------------------
def test_nothing_to_take_over_is_said(paper):
    r = client.post(f"/api/stock-mode/{SYM}/take-over", headers=headers(paper.key))
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_NOTHING_HELD"


def test_taking_over_the_bots_trade_hands_it_to_you(paper, monkeypatch, api_key):
    from bot.gates import set_readout_for_tests
    from setup_scanner.readout import evaluate

    set_readout_for_tests(evaluate([]))
    bot_runner.reset_for_tests(lambda: paper.clock["t"])
    ready_l2(brain=None, symbols=(SYM,), readout_passed=False)
    monkeypatch.setattr(fp_orders, "last_price", lambda symbol: 10.00)
    monkeypatch.setattr(fp_orders, "best_bid", lambda symbol: 9.98)
    bot_runner.submit(trigger())
    asyncio.run(bot_runner.tick())
    assert load_session()["trade"]["state"] == "open"
    assert client.get(f"/api/stock-mode/{SYM}").json()["mode"] == "bot"
    r = client.post(f"/api/stock-mode/{SYM}/take-over", json={"risk_usd": 20}, headers=headers(paper.key))
    assert r.status_code == 200
    bot_trade = load_session()["trade"]
    assert bot_trade["state"] == "handed" and bot_trade["target_order_id"] is None
    assert paper.broker.ledger.working_orders() == [] and paper.broker.ledger.held_qty(SYM) == 1.0
    assert SYM not in load_session()["symbol_allowlist"]
    body = r.json()
    assert body["mode"] == "auto_entry" and body["trade"]["exits"] == "you" and body["nova_entries_today"] == 1
    assert any(row["action"] == "bot_trade" and row["outcome"] == "handed" for row in list_entries(limit=50))
    bot_runner.reset_for_tests()


def test_setting_sell_to_you_takes_over_an_approved_bracket(paper, monkeypatch, sent):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    cancels: list[int] = []

    async def cancel(trade, order_id, *, source="bot"):
        cancels.append(int(order_id))
        return Receipt(ok=True, order_id=order_id, error=None, reason_code=None)

    from stock_mode import orders as sm_orders

    monkeypatch.setattr(sm_orders, "cancel", cancel)
    monkeypatch.setattr(sm_orders, "order_row", lambda oid: {"order_id": oid, "status": "Filled", "filled_qty": 153,
                                                              "avg_fill_price": 10.02} if oid == 101 else
                        {"order_id": oid, "status": "Submitted"})
    assert put(paper, "you", "nova").status_code == 200
    assert client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key)).status_code == 200
    monkeypatch.setattr(sm_orders, "held_qty", lambda sym: 153.0)     # the stubbed entry filled
    runner.submit(trigger())
    tick(paper)
    trade = tick(paper, NOW + 0.5)
    assert trade["state"] == "holding" and trade["exits"] == "nova"
    body = put(paper, "you", "you").json()
    assert sorted(cancels) == [102, 103] and body["mode"] == "signal"
    assert body["trade"]["exits"] == "you"



# -- Approve on the practice broker's own brackets (#606 step 1) -------------------------------
def _legs(p) -> dict[int, dict]:
    ledger = p.broker.ledger
    return {int(r["order_id"]): r for r in [*ledger.working_orders(), *ledger.closed_orders()]}


def test_an_approved_bracket_fills_at_the_broker_and_its_target_closes_the_trade(paper, monkeypatch):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    put(paper, "you", "nova")
    client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    runner.submit(trigger())
    tick(paper)                                              # the bracket goes out: the entry takes the 10.02 ask
    trade = tick(paper, NOW + 0.5)
    assert trade["state"] == "holding" and trade["exits"] == "nova" and trade["fill_price"] == 10.02
    legs = _legs(paper)
    target, stop = legs[trade["target_order_id"]], legs[trade["stop_order_id"]]
    assert (target["leg_role"], target["status"], target["limit_price"]) == ("target", "Submitted", 10.28)
    assert (stop["leg_role"], stop["status"], stop["stop_price"]) == ("stop", "Submitted", 9.89)
    assert target["oca_group"] == stop["oca_group"] == f"oca-{trade['entry_order_id']}"

    paper.broker.try_fill_working(SYM, [(NOW + 2, 10.30)])     # a print through the target
    trade = tick(paper, NOW + 2.5)
    assert (trade["state"], trade["exit_reason"], trade["exit_price"]) == ("closed", "target", 10.28)
    legs = _legs(paper)
    assert legs[trade["stop_order_id"]]["status"] == "Cancelled"
    assert legs[trade["stop_order_id"]]["reason_code"] == "PRACTICE_OCO_CANCELLED"
    assert paper.broker.ledger.held_qty(SYM) == 0.0
    view = client.get(f"/api/stock-mode/{SYM}").json()
    assert view["trade"]["state"] == "closed" and view["trade"]["closed_at"] == NOW + 2.5
    assert "10.28" in view["last_event"]["text"] and "+$39.78" in view["last_event"]["text"]


def test_taking_over_a_real_bracket_cancels_both_exits_and_keeps_the_shares(paper, monkeypatch):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    put(paper, "you", "nova")
    client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    runner.submit(trigger())
    tick(paper)
    trade = tick(paper, NOW + 0.5)
    body = client.post(f"/api/stock-mode/{SYM}/take-over", headers=headers(paper.key)).json()
    assert body["trade"]["exits"] == "you" and body["mode"] == "signal"
    assert paper.broker.ledger.working_orders() == [] and paper.broker.ledger.held_qty(SYM) == 153.0
    legs = _legs(paper)
    assert {legs[trade["target_order_id"]]["status"], legs[trade["stop_order_id"]]["status"]} == {"Cancelled"}
    paper.broker.try_fill_working(SYM, [(NOW + 3, 10.30), (NOW + 4, 9.80)])
    assert paper.broker.ledger.held_qty(SYM) == 153.0            # Nova sells nothing once the exit is yours


def test_an_approved_entry_left_unfilled_is_cancelled_with_its_exits(paper, monkeypatch):
    monkeypatch.setattr(runner, "lane_of", lambda sym, sid: lane())
    paper.ref.bid, paper.ref.ask, paper.ref.last = 10.06, 10.10, 10.08     # the entry rests under the ask
    put(paper, "you", "nova")
    client.post(f"/api/stock-mode/{SYM}/approve", json=approve_body(), headers=headers(paper.key))
    runner.submit(trigger())
    trade = tick(paper)
    assert trade["state"] == "entering"
    legs = _legs(paper)
    assert {legs[trade["target_order_id"]]["status"], legs[trade["stop_order_id"]]["status"]} == {"PreSubmitted"}
    tick(paper, NOW + STOCK_MODE_ENTRY_TTL_SEC + 0.5)
    trade = tick(paper, NOW + STOCK_MODE_ENTRY_TTL_SEC + 1.0)
    assert trade["state"] == "missed"
    legs = _legs(paper)
    assert legs[trade["entry_order_id"]]["status"] == "Cancelled"
    assert {legs[trade["target_order_id"]]["reason_code"], legs[trade["stop_order_id"]]["reason_code"]} == {
        "PRACTICE_PARENT_CANCELLED"}
    assert paper.broker.ledger.working_orders() == [] and paper.broker.ledger.held_qty(SYM) == 0.0
