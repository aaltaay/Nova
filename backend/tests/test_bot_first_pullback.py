"""The first-pullback bot trades Paper and Sim; the read-out gates Live (ADR 030, #514).

The trade tests run the real execution door and the real practice broker on the
Paper venue against a fake live market (``FakeLive``), and drive the bot's loop
one tick at a time with a pinned clock.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from bot.arming import issue_arm_token
from bot.audit import list_entries
from bot.autonomy import apply_patch
from bot.entry_rules import entries_today
from bot.first_pullback import orders as fp_orders
from bot.first_pullback import runner
from bot.gates import readout_required, set_readout_for_tests
from bot.persist import load_session, save_session
from bot.session import get_session
from constants_bot import (
    BOT_FP_TIME_STOP_MIN,
    BOT_KIND_SETUP_ENTRY,
    BOT_REASON_READOUT_NOT_PASSED,
    BOT_RUNNER_BRAIN_ID,
)
from execution import inflight
from ibkr import safety as _safety
from main import app
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests as reset_brokers
from setup_scanner.readout import evaluate
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue
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
    monkeypatch.setenv("NOVA_API_KEY", "bot-test-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    return "bot-test-key"


@pytest.fixture
def closed_readout():
    set_readout_for_tests(evaluate([]))


@pytest.fixture
def paper(monkeypatch, closed_readout):
    """Paper venue, desk armed, the read-out still closed, the bot Active at Strategy on IMCC."""
    reset_venue()
    reset_brokers()
    inflight.reset_for_tests()
    fake = FakeLive()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: fake)
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    clock = {"t": NOW}
    runner.reset_for_tests(lambda: clock["t"])
    ready_l2(brain=None, symbols=(SYM,), readout_passed=False)
    quotes = {"last": 10.00, "bid": 9.98}
    monkeypatch.setattr(fp_orders, "last_price", lambda symbol: quotes["last"])
    monkeypatch.setattr(fp_orders, "best_bid", lambda symbol: quotes["bid"])
    yield SimpleNamespace(broker=for_venue("paper"), ref=fake, clock=clock, quotes=quotes)
    runner.reset_for_tests()
    inflight.reset_for_tests()
    reset_brokers()
    reset_venue()


def trigger(**over) -> dict:
    setup = {"kind": "first_pullback", "trigger": 10.01, "entry": 10.02, "stop": 9.89, "risk": 0.14,
             "target1": 10.30, "triggered_at": NOW, "trigger_price": 10.02, "nth": 1}
    setup.update(over.pop("setup", {}))
    event = {"symbol": SYM, "setup_id": f"{SYM}-2026-09-24-1790000000", "setup": setup,
             "tape": {"verdict": "go", "reasons": ["green on the tape"]}, "ts": NOW,
             "template_id": "default", "template_rev": 1, "template_name": "Default", "source": "live"}
    event.update(over)
    return event


def tick(p, at: float | None = None) -> dict | None:
    if at is not None:
        p.clock["t"] = at
        p.ref.now = at
    asyncio.run(runner.tick())
    return load_session().get("trade")


def trade_rows(outcome: str | None = None) -> list[dict]:
    return [r for r in list_entries(limit=100)
            if r["action"] == "bot_trade" and (outcome is None or r["outcome"] == outcome)]


# -- the read-out gates Live only ------------------------------------------------
def test_paper_skips_the_readout_live_keeps_it(closed_readout, api_key):
    reset_venue()
    try:
        set_venue("paper")
        assert readout_required() is False
        token = issue_arm_token()
        apply_patch({"level": 2}, desk=True, arm_token=token)
        view = get_session()
        assert view["armed"] is True and view["readout_required"] is False
        gate = {g["id"]: g for g in view["gates"]}["readout"]
        assert gate["ok"] is True and gate["detail"]["waived"] is True and gate["detail"]["venue"] == "paper"
        assert client.post("/api/bot/session/arm", json={}, headers=headers(api_key)).status_code == 200

        set_venue("live")
        assert readout_required() is True
        res = client.post("/api/bot/session/arm", json={}, headers=headers(api_key))
        assert res.status_code == 409 and res.json()["detail"]["reason"] == BOT_REASON_READOUT_NOT_PASSED
        gate = {g["id"]: g for g in get_session()["gates"]}["readout"]
        assert gate["ok"] is False and gate["detail"]["waived"] is False
    finally:
        reset_venue()


def test_an_unreadable_venue_counts_as_live(monkeypatch):
    import sim.mode

    def broken() -> str:
        raise RuntimeError("venue file unreadable")

    monkeypatch.setattr(sim.mode, "venue", broken)
    assert readout_required() is True


def test_a_strategy_bot_left_active_on_live_is_stopped(paper):
    assert get_session()["armed"] is True
    set_venue("live")
    tick(paper)
    assert get_session()["armed"] is False
    [row] = [r for r in list_entries(limit=50) if r["action"] == "deactivate"]
    assert "Live waits on the first-pullback read-out" in row["reason"]


# -- the session ---------------------------------------------------------------
def test_the_bot_holds_the_strategy_session_while_it_plays(paper):
    tick(paper)
    view = get_session()
    assert view["brain_session_id"] == BOT_RUNNER_BRAIN_ID and view["brain_alive"] is True
    assert view["runner"] == {"brain_id": BOT_RUNNER_BRAIN_ID, "playing": True, "reason": None}
    assert view["live_fire_ready"] is True


def test_on_live_the_bot_does_not_play(paper):
    set_readout_for_tests(None)
    from bot.gates import passed_readout_for_tests

    set_readout_for_tests(passed_readout_for_tests())
    tick(paper)
    set_venue("live")
    _safety.set_armed(True, reason="test")
    runner.submit(trigger())
    tick(paper)
    view = get_session()
    assert view["runner"]["playing"] is False and "Paper and Sim only" in view["runner"]["reason"]
    assert view["brain_session_id"] is None          # it let go of the session
    assert view["trade"] is None and trade_rows() == []


# -- the trade -----------------------------------------------------------------
def test_go_trigger_enters_rests_the_target_and_closes_on_it(paper):
    runner.submit(trigger())
    trade = tick(paper)                              # marketable at the 10.02 ask: filled in the send
    assert trade["state"] == "open" and trade["qty"] == 1.0 and trade["venue"] == "paper"
    [entry] = [r for r in list_entries(limit=50) if r["action"] == BOT_KIND_SETUP_ENTRY]
    assert entry["outcome"] == "ok" and entry["inputs"]["limit"] == 10.02
    assert entries_today() == 1
    assert trade["entry_fill_price"] == 10.02 and trade["slippage"] == 0.0
    assert trade["target_order_id"] is not None
    assert load_session()["working"] == [] and load_session()["bot_qty"] == {SYM: 1.0}
    assert paper.broker.ledger.held_qty(SYM) == 1.0

    paper.broker.try_fill_working(SYM, [(NOW + 10, 10.35)])
    trade = tick(paper, NOW + 11)
    assert trade["state"] == "closed" and trade["exit_reason"] == "target"
    assert trade["exit_price"] == 10.30 and trade["r"] == pytest.approx(2.0)
    assert paper.broker.ledger.held_qty(SYM) == 0.0 and load_session()["bot_qty"] == {}
    assert [r["outcome"] for r in trade_rows()] == ["filled", "closed"]
    fills = [r for r in paper.broker.ledger.closed_orders() if r["status"] == "Filled"]
    assert {r["order_source"] for r in fills} == {"bot"}   # attributed to the bot


def test_a_print_under_the_stop_cancels_the_target_and_sells_at_the_bid(paper):
    runner.submit(trigger())
    tick(paper)
    tick(paper, NOW + 0.5)
    paper.quotes["last"] = 9.88
    trade = tick(paper, NOW + 5)
    assert trade["state"] == "exiting" and trade["exit_why"] == "stop" and trade["target_order_id"] is None
    trade = tick(paper, NOW + 5.5)
    assert trade["state"] == "closed" and trade["exit_reason"] == "stop"
    assert trade["exit_price"] == 9.98                # the practice touch, never worse than the 9.95 limit
    assert paper.broker.ledger.held_qty(SYM) == 0.0
    assert paper.broker.ledger.working_orders() == []
    assert [r["outcome"] for r in trade_rows()] == ["filled", "closing", "closed"]


def test_the_time_stop_closes_a_trade_that_went_nowhere(paper):
    runner.submit(trigger())
    tick(paper)
    tick(paper, NOW + 0.5)
    trade = tick(paper, NOW + 0.5 + BOT_FP_TIME_STOP_MIN * 60 + 1)
    assert trade["state"] == "exiting" and trade["exit_why"] == "time"
    trade = tick(paper, NOW + BOT_FP_TIME_STOP_MIN * 60 + 2)
    assert trade["state"] == "closed" and trade["exit_reason"] == "time"
    assert paper.broker.ledger.held_qty(SYM) == 0.0


def test_no_bid_ends_in_the_protective_flatten(paper):
    runner.submit(trigger())
    tick(paper)
    tick(paper, NOW + 0.5)
    paper.quotes.update(last=9.80, bid=None)
    tick(paper, NOW + 5)
    trade = tick(paper, NOW + 5.5)
    assert trade["state"] == "closed" and trade["exit_reason"] == "stop" and trade["exit_protective"] is True
    assert paper.broker.ledger.held_qty(SYM) == 0.0


def test_an_unfilled_entry_is_cancelled_after_the_ttl_and_gives_the_day_back(paper):
    runner.submit(trigger(setup={"entry": 9.95, "trigger": 9.94, "stop": 9.85, "risk": 0.11, "target1": 10.20}))
    trade = tick(paper)
    assert trade["state"] == "entering"              # 9.95 under the 10.02 ask: it rests
    assert load_session()["working"][0]["expire_ts"] is None   # the bot cancels it, not the TTL loop
    tick(paper, NOW + 1)
    assert tick(paper, NOW + 3.5)["entry_cancel_ts"] == NOW + 3.5
    trade = tick(paper, NOW + 4)
    assert trade["state"] == "missed" and "not filled in 3s" in trade["note"]
    assert load_session()["working"] == [] and paper.broker.ledger.held_qty(SYM) == 0.0
    assert entries_today() == 0                      # nothing was bought: the day's trade is still there


def test_closing_the_position_by_hand_ends_the_trade(paper):
    runner.submit(trigger())
    tick(paper)
    tick(paper, NOW + 0.5)
    target = load_session()["trade"]["target_order_id"]
    paper.broker.cancel(target)
    paper.broker.place(SYM, "SELL", 1, "MKT")
    tick(paper, NOW + 2)
    trade = tick(paper, NOW + 3)
    assert trade["state"] == "closed" and trade["exit_reason"] == "outside"
    assert [r["outcome"] for r in trade_rows()] == ["filled", "note", "closed"]


def test_deactivate_stops_new_entries_but_the_trade_on_is_still_managed(paper, api_key):
    runner.submit(trigger())
    tick(paper)
    tick(paper, NOW + 0.5)
    assert client.post("/api/bot/session/disarm", json={}, headers=headers(api_key)).status_code == 200
    paper.quotes["last"] = 9.85
    tick(paper, NOW + 5)
    assert tick(paper, NOW + 5.5)["exit_reason"] == "stop"
    runner.submit(trigger(setup_id="OTHER", setup={"triggered_at": NOW + 6}))
    tick(paper, NOW + 6)
    assert load_session()["trade"]["setup_id"] != "OTHER"


# -- what it does not trade -------------------------------------------------------
@pytest.mark.parametrize("event, said", [
    (trigger(tape={"verdict": "wait"}), "the tape read wait at the trigger"),
    (trigger(tape={"verdict": "blind"}), "the tape read blind at the trigger"),
    (trigger(setup={"kind": "second_pullback"}), "a second pullback"),
])
def test_what_the_bot_skips_is_on_the_timeline(paper, event, said):
    runner.submit(event)
    assert tick(paper) is None
    [row] = trade_rows("skipped")
    assert said in row["reason"]
    assert paper.broker.ledger.working_orders() == []


def test_a_name_off_the_allowlist_is_left_to_the_scanner(paper):
    runner.submit(trigger(symbol="NOPE"))
    assert tick(paper) is None and trade_rows() == []


def test_an_allowlisted_name_without_its_level_2_is_skipped_with_the_reason(paper):
    from tests.bot_helpers import release_depth_lines

    release_depth_lines()
    runner.submit(trigger())
    assert tick(paper) is None
    [row] = trade_rows("skipped")
    assert "holds no depth line" in row["reason"] and row["inputs"]["code"] == "BOT_NO_DEPTH_LINE"


def test_one_trade_a_day(paper):
    runner.submit(trigger())
    tick(paper)
    tick(paper, NOW + 0.5)
    paper.broker.try_fill_working(SYM, [(NOW + 10, 10.35)])
    tick(paper, NOW + 11)
    runner.submit(trigger(setup_id="IMCC-second", setup={"triggered_at": NOW + 12}))
    tick(paper, NOW + 12)
    [row] = trade_rows("skipped")
    assert "a day" in row["reason"] and row["inputs"]["code"] == "BOT_DAY_TRADE_CAP"


def test_a_live_commission_hold_does_not_hold_paper(paper, monkeypatch):
    """#564: the hold is Live's; Paper's day P&L is the practice ledger's and reads no commissions."""
    import sqlite3

    from bot import day_pnl

    def locked(*, since_ts: float):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr("execution.store_facts.session_commission_by_symbol", locked)
    assert day_pnl.session_commission_total() is None      # a Live read failed earlier
    assert day_pnl.commission_hold("live") is not None
    runner.submit(trigger())
    trade = tick(paper)
    assert trade["state"] == "open" and trade_rows("skipped") == []


def test_a_stale_trigger_is_not_traded(paper):
    runner.submit(trigger(setup={"triggered_at": NOW - 30}))
    assert tick(paper) is None and trade_rows() == []


def test_the_bot_is_silent_when_it_does_not_play(paper):
    row = load_session()
    row["level"] = 1
    save_session(row)
    runner.submit(trigger())
    assert tick(paper) is None and trade_rows() == []


def test_the_budget_cuts_the_size(paper):
    row = load_session()
    row["caps"] = {**row["caps"], "max_shares": 10, "bp_budget_usd": 35.0}
    save_session(row)
    runner.submit(trigger())
    assert tick(paper)["qty"] == 3.0                 # $35 buys three at 10.02


def test_a_restart_resumes_the_trade(paper):
    runner.submit(trigger())
    tick(paper)
    tick(paper, NOW + 0.5)
    runner.reset_for_tests(lambda: paper.clock["t"])   # a new process: the loop's memory is gone
    paper.broker.try_fill_working(SYM, [(NOW + 10, 10.35)])
    assert tick(paper, NOW + 11)["exit_reason"] == "target"


# -- ADR 031: the bot plays the chosen setup --------------------------------------------
def choose(setup: str) -> None:
    """The chosen setup, without the deactivation a desk PATCH makes (tests of the runner alone)."""
    row = load_session()
    row["setup"] = setup
    save_session(row)


def test_the_bot_trades_only_the_chosen_setups_triggers(paper):
    choose("bull_flag")
    runner.submit(trigger())                                  # a first pullback: another setup's now
    assert tick(paper) is None and trade_rows() == []
    runner.submit(trigger(setup_type="bull_flag", setup={"kind": "bull_flag"}))
    trade = tick(paper)
    assert trade["setup_type"] == "bull_flag" and trade["state"] in ("entering", "open")
    [entry] = [r for r in list_entries(limit=50) if r["action"] == BOT_KIND_SETUP_ENTRY]
    assert entry["reason"].startswith("bull flag over 10.01") and entry["inputs"]["setup_type"] == "bull_flag"


def test_a_second_of_the_chosen_setup_is_skipped_by_name(paper):
    choose("flat_top_breakout")
    runner.submit(trigger(setup_type="flat_top_breakout", setup={"kind": "second_flat_top_breakout"}))
    tick(paper)
    [row] = trade_rows("skipped")
    assert "a second flat top breakout on IMCC" in row["reason"] and row["inputs"]["setup_type"] == "flat_top_breakout"


def test_a_setup_without_a_scanner_never_plays(paper):
    choose("gap_and_go")
    status = runner.status(load_session())
    assert status["playing"] is False and "no scanner" in status["reason"]


# -- the template's flush exit (ADR 034) --------------------------------------------------
def flush_reading(monkeypatch, **policy):
    """The setup scanner's newest flow reading on the bot's setup, set by the test."""
    from bot.first_pullback import flush as fp_flush

    box: dict = {}
    rule = {"mode": "off", "hold_sec": 10.0, "trail_r": 0.5, "min_r": None, **policy}
    monkeypatch.setattr(fp_flush, "reading", lambda setup_id: {**box["r"], "policy": rule} if "r" in box else None)
    return box


def test_a_flush_closes_the_trade_when_the_template_says_exit(paper, monkeypatch):
    box = flush_reading(monkeypatch, mode="exit")
    runner.submit(trigger())
    tick(paper)
    tick(paper, NOW + 0.5)
    box["r"] = {"ts": NOW + 5, "label": "flush", "score": -0.8, "price": 10.05, "bid": 10.04}
    assert tick(paper, NOW + 5.5)["state"] == "open"                 # inside the hold: the entry's own noise
    box["r"] = {"ts": NOW + 20, "label": "flush", "score": -0.8, "price": 10.05, "bid": 10.04}
    paper.quotes["last"] = 10.05
    trade = tick(paper, NOW + 20.5)
    assert trade["state"] == "exiting" and trade["exit_why"] == "flush"
    trade = tick(paper, NOW + 21)
    assert trade["state"] == "closed" and trade["exit_reason"] == "flush"
    assert paper.broker.ledger.held_qty(SYM) == 0.0
    [closing] = trade_rows("closing")
    assert closing["reason"].startswith("flush on the tape (score -0.80)")
    assert trade_rows("closed")[0]["reason"].startswith("out on a flush on the tape")


def test_tighten_moves_the_watched_stop_up_and_the_stop_then_closes(paper, monkeypatch):
    box = flush_reading(monkeypatch, mode="tighten", trail_r=0.5)
    runner.submit(trigger())
    tick(paper)
    tick(paper, NOW + 0.5)
    paper.quotes["last"] = 10.20
    box["r"] = {"ts": NOW + 30, "label": "flush", "score": -0.7, "price": 10.20, "bid": 10.19}
    trade = tick(paper, NOW + 30.5)
    assert trade["state"] == "open" and trade["stop"] == pytest.approx(10.13)   # 10.20 - 0.5 x 0.14
    assert trade_rows("note")[0]["reason"].endswith("the stop moves up to 10.13")
    box["r"] = {"ts": NOW + 40, "label": "flush", "score": -0.7, "price": 10.10, "bid": 10.09}
    paper.quotes["last"] = 10.12
    trade = tick(paper, NOW + 40.5)
    assert trade["state"] == "exiting" and trade["exit_why"] == "stop"


def test_off_a_stale_reading_or_no_reading_changes_nothing(paper, monkeypatch):
    box = flush_reading(monkeypatch, mode="off")
    runner.submit(trigger())
    tick(paper)
    box["r"] = {"ts": NOW + 20, "label": "flush", "score": -0.9, "price": 10.05, "bid": 10.04}
    assert tick(paper, NOW + 20.5)["state"] == "open"
    box = flush_reading(monkeypatch, mode="exit")
    box["r"] = {"ts": NOW + 20, "label": "flush", "score": -0.9, "price": 10.05, "bid": 10.04}
    assert tick(paper, NOW + 40)["state"] == "open"                   # 20 s old: not acted on
    box.clear()
    assert tick(paper, NOW + 41)["state"] == "open" and trade_rows("closing") == []
