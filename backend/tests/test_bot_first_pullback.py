"""Nova's own bot trades Paper and Sim, every setup at Strategy, with a practice bracket (ADR 030, ADR 042 I).

The trade tests run the real execution door and the real practice broker on the
Paper venue against a fake live market (``FakeLive``), and drive the bot's loop
one tick at a time with a pinned clock. The resting exits fill when the test hands
the practice broker a print (``try_fill_working``), as the practice matcher does.
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
from bot.errors import BotError
from bot.first_pullback import orders as fp_orders
from bot.first_pullback import runner
from bot.persist import load_session, save_session
from bot.session import get_session
from constants_bot import (
    BOT_FP_TIME_STOP_MIN,
    BOT_KIND_SETUP_ENTRY,
    BOT_REASON_VENUE_UNKNOWN,
    BOT_RUNNER_BRAIN_ID,
)
from execution import inflight
from ibkr import safety as _safety
from main import app
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests as reset_brokers
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
def paper(monkeypatch):
    """Paper venue, desk armed, the bot Active at Strategy on IMCC (the first pullback at Strategy)."""
    reset_venue()
    reset_brokers()
    inflight.reset_for_tests()
    fake = FakeLive()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: fake)
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    clock = {"t": NOW}
    runner.reset_for_tests(lambda: clock["t"])
    ready_l2(brain=None, symbols=(SYM,))
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
             "template_id": "default", "template_rev": 1, "template_name": "Default", "source": "live",
             "grade": "A", "pillars": {"passed": 5, "known": 5, "total": 5}, "filtered": None, "spread": 0.02}
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


def leg(p, order_id) -> dict:
    return p.broker.ledger.order_row(int(order_id))


# -- the venue -------------------------------------------------------------------
def test_an_unreadable_venue_counts_as_live(monkeypatch):
    import sim.mode

    from bot.activation import venue_block, venue_state

    def broken() -> str:
        raise RuntimeError("venue file unreadable")

    monkeypatch.setattr(sim.mode, "venue", broken)
    venue, edge, readable = venue_state()
    assert readable is False and venue_block(venue, edge, readable)[0] == BOT_REASON_VENUE_UNKNOWN


def test_a_bot_left_active_on_live_is_stopped(paper):
    """Moving to Live stops it (the dial is per venue); the runner stops one that got there
    another way (a session file that says Strategy and active on Live)."""
    assert get_session()["active"] is True
    set_venue("live")
    assert get_session()["active"] is False and get_session()["level"] == 0
    row = load_session()
    row.update(level=2, armed=True, desk_arm_token="t", setup_levels={"first_pullback": 2})
    save_session(row)
    tick(paper)
    view = get_session()
    assert view["active"] is False and view["deactivated"]["reason"] == "venue"
    assert "Paper and Sim only" in view["deactivated"]["text"]


# -- the session ---------------------------------------------------------------
def test_the_bot_holds_the_strategy_session_while_it_plays(paper):
    tick(paper)
    view = get_session()
    assert view["brain_session_id"] == BOT_RUNNER_BRAIN_ID and view["brain_alive"] is True
    assert view["runner"] == {"brain_id": BOT_RUNNER_BRAIN_ID, "playing": True, "reason": None}
    assert view["ready"] is True and view["live_fire_ready"] is True


def test_on_live_the_bot_does_not_play(paper):
    tick(paper)
    set_venue("live")
    apply_patch({"level": 2, "setup_levels": {"first_pullback": 2}}, desk=True)
    issue_arm_token()                                  # a session that says Active on Live
    _safety.set_armed(True, reason="test")
    runner.submit(trigger())
    tick(paper)
    view = get_session()
    assert view["runner"]["playing"] is False
    assert view["brain_session_id"] is None            # it let go of the session
    assert view["trade"] is None and [r for r in trade_rows() if r["outcome"] != "skipped"] == []


# -- the trade: a practice bracket ------------------------------------------------
def test_go_trigger_enters_with_a_bracket_and_closes_on_the_target(paper):
    runner.submit(trigger())
    trade = tick(paper)                              # marketable at the 10.02 ask: filled in the send
    assert trade["state"] == "open" and trade["qty"] == 1.0 and trade["venue"] == "paper"
    assert trade["size_text"] == "1 share: $20 risk / $0.13 a share = 153, capped at the sleeve's 1 max share"
    target, stop = leg(paper, trade["target_order_id"]), leg(paper, trade["stop_order_id"])
    assert target["order_type"] == "LMT" and target["limit_price"] == 10.30 and target["status"] == "Submitted"
    assert stop["order_type"] == "STP" and stop["stop_price"] == 9.89 and stop["status"] == "Submitted"
    [entry] = [r for r in list_entries(limit=50) if r["action"] == BOT_KIND_SETUP_ENTRY]
    assert entry["outcome"] == "ok" and entry["inputs"]["limit"] == 10.02 and "one bracket" in entry["reason"]
    assert entries_today() == 1
    assert trade["entry_fill_price"] == 10.02 and trade["slippage"] == 0.0
    assert load_session()["working"] == [] and load_session()["bot_qty"] == {SYM: 1.0}
    assert paper.broker.ledger.held_qty(SYM) == 1.0

    paper.broker.try_fill_working(SYM, [(NOW + 10, 10.35)])
    trade = tick(paper, NOW + 11)
    assert trade["state"] == "closed" and trade["exit_reason"] == "target"
    assert trade["exit_price"] == 10.30 and trade["r"] == pytest.approx(2.0)
    assert paper.broker.ledger.held_qty(SYM) == 0.0 and load_session()["bot_qty"] == {}
    assert leg(paper, trade["stop_order_id"])["status"] == "Cancelled"     # one cancelled the other
    assert [r["outcome"] for r in trade_rows()] == ["filled", "closed"]
    fills = [r for r in paper.broker.ledger.closed_orders() if r["status"] == "Filled"]
    assert {r["order_source"] for r in fills} == {"bot"}   # attributed to the bot


def test_every_order_is_stamped_with_its_setup(paper, monkeypatch):
    seen = []
    real = fp_orders.execute

    async def spy(cmd, **kw):
        seen.append(cmd)
        return await real(cmd, **kw)

    monkeypatch.setattr(fp_orders, "execute", spy)
    apply_patch({"setup_levels": {"bull_flag": 2}}, desk=True)
    runner.submit(trigger(setup_type="bull_flag", setup={"kind": "bull_flag"}))
    tick(paper)
    trade = tick(paper, NOW + 0.5 + BOT_FP_TIME_STOP_MIN * 60)
    assert trade["state"] in ("exiting", "closed")
    assert seen and {c.setup for c in seen if c.operation != "cancel"} == {"bull_flag"}
    assert seen[0].operation == "bracket" and seen[0].source == "bot" and seen[0].expected_venue == "paper"


def test_the_resting_stop_fills_at_the_broker_and_the_bot_closes_it(paper):
    runner.submit(trigger())
    tick(paper)
    paper.broker.try_fill_working(SYM, [(NOW + 5, 9.85)])
    trade = tick(paper, NOW + 5.5)
    assert trade["state"] == "closed" and trade["exit_reason"] == "stop" and trade["exit_price"] == 9.85
    assert leg(paper, trade["target_order_id"])["status"] == "Cancelled"
    assert paper.broker.ledger.held_qty(SYM) == 0.0 and paper.broker.ledger.working_orders() == []
    assert [r["outcome"] for r in trade_rows()] == ["filled", "closed"]


def test_a_stop_leg_cancelled_outside_is_watched_by_the_bot(paper):
    runner.submit(trigger())
    trade = tick(paper)
    paper.broker.cancel(trade["stop_order_id"])
    tick(paper, NOW + 1)
    assert "the bot watches the stop itself" in trade_rows("note")[0]["reason"]
    paper.quotes["last"] = 9.88
    trade = tick(paper, NOW + 5)
    assert trade["state"] == "exiting" and trade["exit_why"] == "stop" and trade["target_order_id"] is None
    trade = tick(paper, NOW + 5.5)
    assert trade["state"] == "closed" and trade["exit_reason"] == "stop" and trade["exit_price"] == 9.98
    assert paper.broker.ledger.held_qty(SYM) == 0.0 and paper.broker.ledger.working_orders() == []


def test_the_time_stop_cancels_both_legs_and_sells(paper):
    runner.submit(trigger())
    trade = tick(paper)
    legs = trade["target_order_id"], trade["stop_order_id"]
    trade = tick(paper, NOW + BOT_FP_TIME_STOP_MIN * 60 + 1)
    assert trade["state"] == "exiting" and trade["exit_why"] == "time"
    assert {leg(paper, oid)["status"] for oid in legs} == {"Cancelled"}
    trade = tick(paper, NOW + BOT_FP_TIME_STOP_MIN * 60 + 2)
    assert trade["state"] == "closed" and trade["exit_reason"] == "time"
    assert paper.broker.ledger.held_qty(SYM) == 0.0


def test_no_bid_ends_in_the_protective_flatten(paper):
    runner.submit(trigger())
    tick(paper)
    paper.quotes.update(bid=None)
    tick(paper, NOW + BOT_FP_TIME_STOP_MIN * 60 + 1)
    trade = tick(paper, NOW + BOT_FP_TIME_STOP_MIN * 60 + 2)
    assert trade["state"] == "closed" and trade["exit_reason"] == "time" and trade["exit_protective"] is True
    assert paper.broker.ledger.held_qty(SYM) == 0.0


def test_an_unfilled_entry_is_cancelled_after_the_sleeves_ttl_and_gives_the_day_back(paper):
    runner.submit(trigger(setup={"entry": 9.95, "trigger": 9.94, "stop": 9.85, "risk": 0.11, "target1": 10.20}))
    trade = tick(paper)
    assert trade["state"] == "entering" and trade["entry_ttl_sec"] == 3   # the sleeve's TTL
    assert load_session()["working"][0]["expire_ts"] is None   # the bot cancels it, not the TTL loop
    tick(paper, NOW + 1)
    assert tick(paper, NOW + 3.5)["entry_cancel_ts"] == NOW + 3.5
    trade = tick(paper, NOW + 4)
    assert trade["state"] == "missed" and "not filled in 3s" in trade["note"]
    assert {leg(paper, trade[k])["status"] for k in ("target_order_id", "stop_order_id")} == {"Cancelled"}
    assert load_session()["working"] == [] and paper.broker.ledger.held_qty(SYM) == 0.0
    assert entries_today() == 0                      # nothing was bought: the day's trade is still there


def test_closing_the_position_by_hand_ends_the_trade(paper):
    runner.submit(trigger())
    trade = tick(paper)
    paper.broker.cancel(trade["target_order_id"])
    paper.broker.place(SYM, "SELL", 1, "MKT")
    tick(paper, NOW + 2)
    trade = tick(paper, NOW + 3)
    assert trade["state"] == "closed" and trade["exit_reason"] == "outside"
    assert paper.broker.ledger.working_orders() == []           # the stop leg went with it
    assert [r["outcome"] for r in trade_rows()] == ["filled", "note", "closed"]


def test_deactivate_stops_new_entries_but_the_trade_on_is_still_managed(paper, api_key):
    runner.submit(trigger())
    tick(paper)
    assert client.post("/api/bot/session/disarm", json={}, headers=headers(api_key)).status_code == 200
    paper.broker.try_fill_working(SYM, [(NOW + 5, 9.85)])
    assert tick(paper, NOW + 5.5)["exit_reason"] == "stop"
    runner.submit(trigger(setup_id="OTHER", setup={"triggered_at": NOW + 6}))
    tick(paper, NOW + 6)
    assert load_session()["trade"]["setup_id"] != "OTHER"
    assert "not active" in trade_rows("skipped")[0]["reason"]


# -- Paper's exits fill while the desk is elsewhere; leaving cancels a working entry ----------
def test_papers_resting_exits_fill_while_the_desk_shows_live(paper):
    runner.submit(trigger())
    trade = tick(paper)
    set_venue("live")
    view = get_session()
    assert "its stop and target rest at the broker" in view["trade"]["waiting"]
    for_venue("paper").try_fill_working(SYM, [(NOW + 30, 10.40)])     # Paper's matcher runs on every venue
    tick(paper, NOW + 31)
    assert load_session()["trade"]["state"] == "open"               # the runner waits for the desk
    set_venue("paper")
    trade = tick(paper, NOW + 40)
    assert trade["state"] == "closed" and trade["exit_reason"] == "target"


def test_leaving_the_venue_cancels_the_bots_working_entry_first(paper):
    runner.submit(trigger(setup={"entry": 9.95, "trigger": 9.94, "stop": 9.85, "risk": 0.11, "target1": 10.20}))
    trade = tick(paper)
    assert trade["state"] == "entering"
    out = set_venue("live")
    [left] = out["left"]
    assert left["by"] == "bot" and left["ok"] is True and left["symbol"] == SYM and left["venue"] == "paper"
    trade = load_session()["trade"]
    assert trade["state"] == "missed" and "the desk left paper" in trade["note"]
    assert for_venue("paper").ledger.working_orders() == []
    assert entries_today() == 0


# -- every setup at Strategy; what it does not trade -----------------------------------------
@pytest.mark.parametrize("event, said", [
    (trigger(tape={"verdict": "wait"}), "the tape read wait at the trigger"),
    (trigger(tape={"verdict": "blind"}), "the tape read blind at the trigger"),
    (trigger(setup={"kind": "second_pullback", "nth": 2}), "a 2nd first pullback: this strategy buys the 1st of "
                                                           "the day only"),
    (trigger(grade="C", pillars={"passed": 2, "known": 5, "total": 5}), "not a trade: grade C: 2 of 5 pillars"),
    (trigger(filtered="float over 10M"), "the template's stock filter keeps it out: float over 10M"),
    (trigger(spread=0.15), "not a trade: the spread 0.15 is at least the 0.14 risk"),
])
def test_what_the_bot_skips_is_on_the_timeline_and_the_stocks_last_event(paper, event, said):
    from stock_mode import store

    runner.submit(event)
    assert tick(paper) is None
    [row] = trade_rows("skipped")
    assert said in row["reason"] and row["inputs"]["reasons"]
    assert paper.broker.ledger.working_orders() == []
    last = store.event(SYM)
    assert last["tone"] == "warn" and said in last["text"]


def test_a_setup_at_eyes_is_skipped_by_name(paper):
    apply_patch({"setup_levels": {"bull_flag": 1}}, desk=True)
    runner.submit(trigger(setup_type="bull_flag", setup={"kind": "bull_flag"}))
    assert tick(paper) is None
    [row] = trade_rows("skipped")
    assert "the bull flag is at Eyes: Nova buys only setups at Strategy" in row["reason"]
    assert row["inputs"]["code"] == "BOT_SETUP_NOT_STRATEGY"


def test_every_setup_at_strategy_plays_and_the_first_trigger_wins(paper):
    apply_patch({"setup_levels": {"bull_flag": 2}}, desk=True)
    runner.submit(trigger(setup_type="bull_flag", setup={"kind": "bull_flag"}, setup_id="BF"))
    runner.submit(trigger(setup_id="FP"))
    trade = tick(paper)
    assert trade["setup_type"] == "bull_flag" and trade["setup_id"] == "BF"
    [row] = trade_rows("skipped")
    assert "already in IMCC -- one trade at a time" in row["reason"]
    [entry] = [r for r in list_entries(limit=50) if r["action"] == BOT_KIND_SETUP_ENTRY]
    assert entry["reason"].startswith("bull flag over 10.01") and entry["inputs"]["setup_type"] == "bull_flag"


def test_a_name_off_the_list_is_left_to_auto_entry_or_the_scanner(paper):
    runner.submit(trigger(symbol="NOPE"))
    assert tick(paper) is None and trade_rows() == []


def test_a_bot_stock_off_todays_hot_list_is_skipped_with_the_reason(paper):
    """ADR 043: Nova buys only the stocks on today's hot list."""
    from constants_hot_list import HOT_LIST_FILE
    from paths import cache_dir

    (cache_dir() / HOT_LIST_FILE).unlink()
    runner.submit(trigger())
    assert tick(paper) is None
    [row] = trade_rows("skipped")
    assert row["inputs"]["code"] == "BOT_SKIP_NOT_LISTED" and "IMCC is not on today's hot list" in row["reason"]


def test_a_grade_the_strategy_does_not_buy_is_skipped(paper):
    """ADR 043: the template in play's ``bot_grades`` -- here A only -- holds a grade B trigger back."""
    from setup_templates.store import get_store

    get_store().update("first_pullback", "default", values={"bot_grades": "A"})
    runner.submit(trigger(grade="B", pillars={"passed": 4, "known": 5, "total": 5}))
    assert tick(paper) is None
    [row] = trade_rows("skipped")
    assert row["inputs"]["code"] == "BOT_SKIP_GRADE"
    assert "grade B: this strategy buys grade A only" in row["reason"]


def test_a_listed_name_without_its_level_2_is_skipped_with_the_reason(paper):
    from tests.bot_helpers import release_depth_lines

    release_depth_lines()
    runner.submit(trigger())
    assert tick(paper) is None
    [row] = trade_rows("skipped")
    assert "holds no depth line" in row["reason"] and row["inputs"]["code"] == "BOT_NO_DEPTH_LINE"


def test_one_trade_a_day(paper):
    runner.submit(trigger())
    tick(paper)
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


def test_a_stale_trigger_is_skipped_and_said(paper):
    runner.submit(trigger(setup={"triggered_at": NOW - 30}))
    assert tick(paper) is None
    [row] = trade_rows("skipped")
    assert "the trigger is 30s old" in row["reason"]


def test_a_bot_at_eyes_says_why_it_did_not_buy(paper):
    apply_patch({"level": 1}, desk=True)
    runner.submit(trigger())
    assert tick(paper) is None
    [row] = trade_rows("skipped")
    assert "the master level is Eyes" in row["reason"] and "not active" in row["reason"]


def test_the_sleeve_sizes_the_trade(paper):
    apply_patch({"caps": {"max_shares": 10, "bp_budget_usd": 35.0}}, desk=True)
    runner.submit(trigger())
    trade = tick(paper)
    assert trade["qty"] == 3.0                        # $35 buys three at 10.02
    assert "budget" in trade["size_text"]


def test_a_size_under_one_share_is_a_stated_skip(paper):
    apply_patch({"caps": {"risk_usd": 1.0}}, desk=True)          # $1 / $0.13 = 7 ... at $0.14 risk: 7
    runner.submit(trigger(setup={"stop": 8.0, "risk": 2.02}))      # $1 / $2.02 a share: under one share
    assert tick(paper) is None
    [row] = trade_rows("skipped")
    assert "under one share" in row["reason"] and row["inputs"]["code"] == "BOT_SIZE_ZERO"


def test_a_restart_resumes_the_trade(paper):
    runner.submit(trigger())
    tick(paper)
    runner.reset_for_tests(lambda: paper.clock["t"])   # a new process: the loop's memory is gone
    paper.broker.try_fill_working(SYM, [(NOW + 10, 10.35)])
    assert tick(paper, NOW + 11)["exit_reason"] == "target"


# -- the operator takes over the exit (ADR 037) -------------------------------------------------
def test_a_take_over_cancels_both_legs_and_hands_the_trade(paper):
    runner.submit(trigger())
    trade = tick(paper)
    handed = asyncio.run(runner.hand_over(SYM, now=NOW + 1))
    assert handed["state"] == "handed" and handed["exit_reason"] == "handed"
    assert paper.broker.ledger.working_orders() == [] and paper.broker.ledger.held_qty(SYM) == 1.0
    assert {leg(paper, trade[k])["status"] for k in ("target_order_id", "stop_order_id")} == {"Cancelled"}


def test_a_take_over_whose_cancel_is_refused_keeps_the_trade(paper, monkeypatch):
    from execution.models import ExecutionReceipt

    runner.submit(trigger())
    tick(paper)

    async def refuse(trade, order_id):
        return ExecutionReceipt(ok=False, execution_id="x", operation="cancel", source="bot", idempotency_key="k",
                                error="broker said no", reason_code="BROKER_REJECT")

    monkeypatch.setattr(fp_orders, "cancel", refuse)
    with pytest.raises(BotError) as refused:
        asyncio.run(runner.hand_over(SYM, now=NOW + 1))
    assert "still rests" in refused.value.message and "keeps" in refused.value.message
    assert load_session()["trade"]["state"] == "open"
    assert any("could not be cancelled" in r["reason"] for r in trade_rows("note"))


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
    box["r"] = {"ts": NOW + 5, "label": "flush", "score": -0.8, "price": 10.05, "bid": 10.04}
    assert tick(paper, NOW + 5.5)["state"] == "open"                 # inside the hold: the entry's own noise
    box["r"] = {"ts": NOW + 20, "label": "flush", "score": -0.8, "price": 10.05, "bid": 10.04}
    paper.quotes["last"] = 10.05
    trade = tick(paper, NOW + 20.5)
    assert trade["state"] == "exiting" and trade["exit_why"] == "flush"
    trade = tick(paper, NOW + 21)
    assert trade["state"] == "closed" and trade["exit_reason"] == "flush"
    assert paper.broker.ledger.held_qty(SYM) == 0.0 and paper.broker.ledger.working_orders() == []
    [closing] = trade_rows("closing")
    assert closing["reason"].startswith("flush on the tape (score -0.80)")
    assert trade_rows("closed")[0]["reason"].startswith("out on a flush on the tape")


def test_tighten_replaces_the_stop_leg_which_then_fills(paper, monkeypatch):
    box = flush_reading(monkeypatch, mode="tighten", trail_r=0.5)
    runner.submit(trigger())
    trade = tick(paper)
    paper.quotes["last"] = 10.20
    paper.ref.last, paper.ref.bid, paper.ref.ask = 10.20, 10.19, 10.21     # the market moved up
    box["r"] = {"ts": NOW + 30, "label": "flush", "score": -0.7, "price": 10.20, "bid": 10.19}
    trade = tick(paper, NOW + 30.5)
    assert trade["state"] == "open" and trade["stop"] == pytest.approx(10.13)   # 10.20 - 0.5 x 0.14
    assert leg(paper, trade["stop_order_id"])["stop_price"] == pytest.approx(10.13)   # the leg moved
    assert trade_rows("note")[0]["reason"].endswith("the stop moves up to 10.13")
    paper.broker.try_fill_working(SYM, [(NOW + 40, 10.12)])
    trade = tick(paper, NOW + 40.5)
    assert trade["state"] == "closed" and trade["exit_reason"] == "stop" and trade["exit_price"] == 10.12


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
