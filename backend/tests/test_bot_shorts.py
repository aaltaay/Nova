"""Nova's bot trades both sides on Paper (ADR 049, #778 step 5): the strategy that triggers decides the side.

The trade tests run the real execution door, the one short check and the practice broker on the Paper
venue against a fake live market, and drive the bot's loop one tick at a time. A short goes out as a
bracket mirrored -- a short limit, a BUY stop over it and a BUY limit at its cover -- priced at the ask
under SSR, through every rule a long meets and its own short check.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

import ibkr.shortability as short_mod
from bot.audit import list_entries
from bot.entry_rules import entries_today
from bot.first_pullback import admit, runner, short_side
from bot.first_pullback import orders as fp_orders
from bot.persist import load_session
from bot.sizing import size
from constants_bot import BOT_KIND_SETUP_SHORT, BOT_SKIP_HELD_OTHER_SIDE, BOT_SKIP_SHORT_PRICE
from execution import inflight, service, telemetry
from execution.models import ExecutionCommand
from ibkr import safety as _safety
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests as reset_brokers
from short_sale import ssr
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue
from tests.bot_helpers import open_entry_window, ready_l2
from tests.test_short_tests_lock import write_result

SYM = "FADE"
SETUP = "bear_flag"


class Market:
    """The live feed as Paper sees it: FADE at 4.00 (3.99 x 4.01), its clock set by the test."""

    def __init__(self, now: float) -> None:
        self.now = now
        self.last, self.bid, self.ask = 4.00, 3.99, 4.01

    def reference(self, symbol: str) -> Reference:
        if symbol != SYM:
            return Reference(None, live=True)
        return Reference(self.last, self.bid, self.ask, live=True)

    def admission(self, symbol: str):
        return (True, "OK", None) if symbol == SYM else (False, "dark", "PRACTICE_NO_LIVE_PRINT")

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def bid_at(self, symbol: str, ts: float) -> float | None:
        return self.bid if symbol == SYM else None

    def now_ts(self) -> float:
        return self.now

    def session_close_ts(self, ts: float) -> float:
        return ts + 86_400


def _borrow(shares: float = 50_000) -> dict:
    return short_mod.enrich_ibkr_listing(
        {"connected": True, "qualified": True, "shortable_shares": shares, "error": None}, fetched_at=time.time())


@pytest.fixture
def paper(monkeypatch, short_market_open):
    """Paper, the desk armed, the Bot on with the bear flag On (its five-year test passed) and FADE set to Bot."""
    reset_venue()
    reset_brokers()
    service.reset_for_tests()
    inflight.reset_for_tests()
    telemetry.reset_for_tests()
    short_mod.reset_for_tests()
    market = Market(short_market_open)
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: market)
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    short_mod.remember_for_tests(SYM, _borrow())
    clock = {"t": short_market_open}
    runner.reset_for_tests(lambda: clock["t"])
    write_result(SETUP)
    ready_l2(brain=None, symbols=(SYM,), setups=(SETUP,))
    open_entry_window(10, 30)
    quotes = {"last": 4.00, "bid": 3.99, "ask": 4.01}
    monkeypatch.setattr(fp_orders, "last_price", lambda symbol: quotes["last"])
    monkeypatch.setattr(fp_orders, "best_bid", lambda symbol: quotes["bid"])
    monkeypatch.setattr(fp_orders, "best_ask", lambda symbol: quotes["ask"])
    yield SimpleNamespace(broker=for_venue("paper"), market=market, clock=clock, quotes=quotes, now=short_market_open)
    runner.reset_for_tests()
    service.reset_for_tests()
    inflight.reset_for_tests()
    telemetry.reset_for_tests()
    short_mod.reset_for_tests()
    reset_brokers()
    reset_venue()


def trigger(p, **over) -> dict:
    setup = {"kind": SETUP, "trigger": 4.00, "entry": 3.99, "stop": 4.13, "risk": 0.14, "target1": 3.71,
             "triggered_at": p.now, "trigger_price": 3.99, "nth": 1}
    setup.update(over.pop("setup", {}))
    event = {"symbol": SYM, "setup_id": f"{SYM}-2026-10-07-1@bear_flag", "setup_type": SETUP, "side": "short",
             "ssr": "off", "setup": setup, "tape": {"verdict": "go", "reasons": ["red on the tape"]}, "ts": p.now,
             "template_id": "default", "template_rev": 1, "template_name": "Default", "source": "live", "grade": "A",
             "pillars": {"passed": 5, "known": 5, "total": 5}, "filtered": None, "spread": 0.02}
    event.update(over)
    return event


def tick(p, at: float | None = None) -> dict | None:
    if at is not None:
        p.clock["t"] = at
        p.market.now = at
    asyncio.run(runner.tick())
    return load_session().get("trade")


def leg(p, order_id) -> dict:
    return p.broker.ledger.order_row(int(order_id))


def skipped() -> list[dict]:
    return [r for r in list_entries(limit=100) if r["action"] == "bot_trade" and r["outcome"] == "skipped"]


# -- the size ----------------------------------------------------------------------------------
def test_a_short_is_sized_up_to_its_buy_stop():
    got = size(20, 3.99, 4.13, 200, None, side="short")
    assert got["qty"] == 142 and got["text"] == "142 shares: $20 risk / $0.14 a share = 142"
    bad = size(20, 3.99, 3.90, 200, None, side="short")
    assert bad["qty"] == 0 and bad["text"] == "the buy stop 3.90 is not over the entry 3.99: nothing to size by"
    assert size(20, 3.99, 4.13, 200, 2.0, side="short")["text"].endswith("budget shorts no share at 3.99")


# -- the price ---------------------------------------------------------------------------------
def test_under_ssr_a_short_sells_at_the_ask_never_under_the_plan():
    facts = SimpleNamespace(ssr=SimpleNamespace(state="on"), bid=3.99, ask=4.01)
    setup = {"entry": 3.99, "stop": 4.13}
    assert short_side.price(setup, facts) == short_side.Priced(4.01, True, "on", None)
    assert short_side.price({"entry": 4.05, "stop": 4.13}, facts).limit == 4.05        # never under the plan
    off = SimpleNamespace(ssr=SimpleNamespace(state="off"), bid=3.99, ask=4.01)
    assert short_side.price(setup, off) == short_side.Priced(3.99, False, "off", None)
    no_ask = SimpleNamespace(ssr=SimpleNamespace(state="unknown"), bid=3.99, ask=None)
    assert "the book shows no ask" in short_side.price(setup, no_ask).why
    high = SimpleNamespace(ssr=SimpleNamespace(state="on"), bid=4.10, ask=4.14)
    assert "no room for a short" in short_side.price(setup, high).why


# -- the trade: a short bracket -----------------------------------------------------------------
def test_a_short_trigger_enters_a_short_bracket_and_covers_at_the_target(paper):
    assert admit.taker(SYM, SETUP) == "bot"
    runner.submit(trigger(paper))
    trade = tick(paper)                              # marketable at the 3.99 bid: filled in the send
    assert trade["side"] == "short" and trade["state"] == "open" and trade["qty"] == 1.0
    assert trade["entry_fill_price"] == 3.99 and trade["slippage"] == 0.0 and trade["risk"] == pytest.approx(0.14)
    target, stop = leg(paper, trade["target_order_id"]), leg(paper, trade["stop_order_id"])
    assert target["side"] == "BUY" and target["order_type"] == "LMT" and target["limit_price"] == 3.71
    assert stop["side"] == "BUY" and stop["order_type"] == "STP" and stop["stop_price"] == 4.13
    [entry] = [r for r in list_entries(limit=50) if r["action"] == BOT_KIND_SETUP_SHORT]
    assert entry["outcome"] == "ok" and entry["inputs"]["side"] == "short" and "buy stop 4.13" in entry["reason"]
    assert {v["id"] for v in entry["inputs"]["short_check"]} >= {"borrow", "ssr", "halt", "hours", "cushion"}
    assert all(v["ok"] for v in entry["inputs"]["short_check"])
    assert entries_today() == 1                      # a short counts toward the day's cap
    assert load_session()["bot_qty"] == {SYM: -1.0} and paper.broker.ledger.held_qty(SYM) == -1.0

    paper.broker.try_fill_working(SYM, [(paper.now + 10, 3.70)])
    trade = tick(paper, paper.now + 11)
    assert trade["state"] == "closed" and trade["exit_reason"] == "target"
    assert trade["exit_price"] == 3.71 and trade["r"] == pytest.approx(2.0)
    assert load_session()["bot_qty"] == {} and paper.broker.ledger.held_qty(SYM) == 0.0


def test_a_short_whose_buy_stop_prints_is_covered_at_the_ask(paper):
    runner.submit(trigger(paper))
    trade = tick(paper)
    asyncio.run(runner._cancel_legs(dict(trade)))      # the stop leg gone: the bot watches the stop itself
    row = load_session()
    row["trade"] = {**row["trade"], "stop_order_id": None, "target_order_id": None}
    from bot.persist import save_session

    save_session(row)
    paper.quotes.update(last=4.14, bid=4.13, ask=4.15)
    paper.market.last, paper.market.bid, paper.market.ask = 4.14, 4.13, 4.15
    trade = tick(paper, paper.now + 5)
    assert trade["exit_why"] == "stop" and trade["exit_limit"] == pytest.approx(4.18)     # 3c over the ask
    assert paper.broker.ledger.held_qty(SYM) == 0.0
    trade = tick(paper, paper.now + 6)
    assert trade["state"] == "closed" and trade["exit_reason"] == "stop" and trade["r"] < 0


def test_under_ssr_the_bots_short_rests_at_the_ask(paper, monkeypatch):
    monkeypatch.setattr(ssr, "live", lambda symbol, now=None: ssr.SsrRead("on", "SSR is on (the test)."))
    runner.submit(trigger(paper))
    trade = tick(paper)
    assert trade["entry_planned"] == 4.01 and trade["priced_at_ask"] is True and trade["ssr"] == "on"
    assert trade["risk"] == pytest.approx(0.12) and trade["state"] == "entering"   # above the bid: it rests
    assert leg(paper, trade["entry_order_id"])["limit_price"] == 4.01


# -- the rules a short meets --------------------------------------------------------------------
def test_a_short_the_check_refuses_is_a_stated_skip_with_its_check(paper, monkeypatch):
    short_mod.reset_for_tests()                       # no borrow read
    monkeypatch.setattr(short_mod, "request_refresh", lambda symbol: True)   # no worker asks IBKR
    runner.submit(trigger(paper))
    assert tick(paper) is None
    [row] = skipped()
    assert any(code.startswith("SHORT_") for code in row["inputs"]["codes"])
    borrow = next(v for v in row["inputs"]["short_check"] if v["id"] == "borrow")
    assert borrow["ok"] is False and f"{borrow['label']}: {borrow['text']}" in row["reason"]


def test_the_bot_never_shorts_a_stock_you_hold_long(paper):
    cmd = ExecutionCommand(operation="place", idempotency_key="buy-1", source="manual", symbol=SYM, side="BUY",
                           qty=1, order_type="LMT", limit_price=4.01, skip_risk=True)
    assert asyncio.run(service.execute(cmd, wait_ack=False)).ok
    runner.submit(trigger(paper))
    assert tick(paper) is None
    [row] = skipped()
    assert BOT_SKIP_HELD_OTHER_SIDE in row["inputs"]["codes"] and "you hold FADE long" in row["reason"]


def test_a_short_with_no_ask_under_ssr_is_skipped_for_its_price(paper, monkeypatch):
    monkeypatch.setattr(ssr, "live", lambda symbol, now=None: ssr.SsrRead("unknown", "SSR unknown (the test)."))
    paper.market.ask = None
    runner.submit(trigger(paper))
    assert tick(paper) is None
    [row] = skipped()
    assert row["inputs"]["code"] == BOT_SKIP_SHORT_PRICE or BOT_SKIP_SHORT_PRICE in row["inputs"]["codes"]
    assert "the book shows no ask" in row["reason"]


# -- Auto-entry and Approve ------------------------------------------------------------------
def _stock_mode(p, buy: str, sell: str) -> None:
    from stock_mode import actions

    asyncio.run(actions.set_mode(SYM, buy, sell))


def _stock_tick(p, at: float | None = None) -> dict | None:
    from stock_mode import runner as sm_runner
    from stock_mode import store as sm_store

    if at is not None:
        p.market.now = at
    asyncio.run(sm_runner.tick(at if at is not None else p.now))
    return sm_store.trade("paper", SYM)


def test_auto_entry_shorts_with_its_buy_stop_resting_and_the_cover_is_yours(paper):
    from stock_mode import runner as sm_runner

    sm_runner.reset_for_tests(lambda: paper.now)
    _stock_mode(paper, "nova", "you")                  # Auto-entry: the bot's list loses FADE, the exit is yours
    assert admit.taker(SYM, SETUP) == "auto_entry"
    sm_runner.submit(trigger(paper))
    trade = _stock_tick(paper)
    assert trade["kind"] == "auto_entry" and trade["side"] == "short" and trade["stop_order_id"] is not None
    trade = _stock_tick(paper, paper.now + 1)
    assert trade["state"] == "holding" and paper.broker.ledger.held_qty(SYM) == -1.0
    stop = leg(paper, trade["stop_order_id"])
    assert stop["side"] == "BUY" and stop["order_type"] == "STP" and stop["status"] == "Submitted"

    cover = ExecutionCommand(operation="place", idempotency_key="cover-1", source="manual", symbol=SYM, side="BUY",
                             qty=1, order_type="LMT", limit_price=4.01, skip_risk=True)
    assert asyncio.run(service.execute(cover, wait_ack=False)).ok
    trade = _stock_tick(paper, paper.now + 2)          # you covered: Nova notices and pulls the buy stop
    assert trade["state"] == "closed" and trade["exit_reason"] == "outside"
    assert leg(paper, stop["order_id"])["status"] == "Cancelled"


def test_an_approved_short_goes_out_as_a_short_bracket_at_its_trigger(paper):
    from stock_mode import runner as sm_runner
    from stock_mode import store as sm_store

    sm_runner.reset_for_tests(lambda: paper.now)
    _stock_mode(paper, "you", "nova")                  # Approve
    sm_store.set_approval(SYM, {"setup_id": trigger(paper)["setup_id"], "setup_type": SETUP, "side": "short",
                                "entry": 3.99, "stop": 4.13, "target": 3.71, "qty": 2, "approved_at": paper.now,
                                "state": "waiting", "reason": None})
    sm_runner.submit(trigger(paper))
    trade = _stock_tick(paper)
    assert trade["kind"] == "approve" and trade["side"] == "short" and trade["entry"] == 3.99
    target, stop = leg(paper, trade["target_order_id"]), leg(paper, trade["stop_order_id"])
    assert (target["side"], target["limit_price"]) == ("BUY", 3.71) and (stop["side"], stop["stop_price"]) == ("BUY", 4.13)
    assert sm_store.approval(SYM)["state"] == "sent"


# -- the localhost bot API's short kinds -------------------------------------------------------------
def test_the_bot_api_shorts_with_its_buy_stop_and_covers_never_past_flat(paper):
    from bot import actions
    from bot.arming import record_heartbeat
    from bot.errors import BotError
    from bot.session import require_l2_brain

    require_l2_brain("brain-1", claim=True)
    record_heartbeat("brain-1")
    out = asyncio.run(actions.fire({"kind": "short_limit_bid_offset", "symbol": SYM}, brain_session_id="brain-1"))
    assert out["ok"] is True
    entry = leg(paper, out["order_id"])
    assert entry["side"] == "SELL" and entry["limit_price"] == 4.00 and entry["position_side"] == "short"
    stops = [r for r in paper.broker.ledger.working_orders() if r["order_type"] == "STP"]
    assert [(r["side"], r["stop_price"]) for r in stops] == [("BUY", 4.10)]     # its buy stop rides with it
    paper.broker.try_fill_working(SYM, [(paper.now + 1, 4.01)])
    assert paper.broker.ledger.held_qty(SYM) == -1.0

    with pytest.raises(BotError) as refused:                     # the short took the day's one entry
        asyncio.run(actions.fire({"kind": "short_limit_bid_offset", "symbol": SYM}, brain_session_id="brain-1"))
    assert refused.value.status_code == 409 and "1 already sent today" in refused.value.message

    covered = asyncio.run(actions.fire({"kind": "cover_limit_ask_offset", "symbol": SYM}, brain_session_id="brain-1"))
    assert covered["ok"] is True and leg(paper, covered["order_id"])["side"] == "BUY"
    assert paper.broker.ledger.held_qty(SYM) == 0.0
    with pytest.raises(BotError) as flat:
        asyncio.run(actions.fire({"kind": "cover_pos", "symbol": SYM}, brain_session_id="brain-1"))
    assert flat.value.status_code == 409 and "no short position" in flat.value.message


def test_the_session_says_what_a_short_needs_from_the_account_and_the_clock(paper):
    from bot.session import get_session

    shorts = get_session()["shorts"]
    assert shorts["venue"] == "paper"
    assert shorts["margin_account"]["ok"] is True and shorts["equity"]["ok"] is True
    assert shorts["equity"]["value"] == "$5,000"
    assert shorts["hours"] == {"ok": True, "text": "new shorts until 15:50 ET; Nova covers what is left at 15:55",
                               "value": "until 15:50"}
    assert shorts["live"]["ok"] is False and "after the Paper proof" in shorts["live"]["text"]
    # ADR 048 step 6: the Live chip counts the proof; Live's cover is off with the switch; no alarm.
    assert shorts["live"]["value"] == "0/7" and "0 of 7 done" in shorts["live"]["text"]
    assert shorts["live_cover"] is False and shorts["day_cover"] == {"alarms": []}


def test_the_live_margin_chip_takes_ibkrs_word_never_the_override(monkeypatch):
    from bot import shorts_view
    from ibkr import account as account_mod

    summary = {"connected": True, "NetLiquidation": 5_000.0, "account_class": "margin", "ibkr_account_class": "cash",
               "account_class_source": "override"}
    monkeypatch.setattr(account_mod, "get_account_summary", lambda: dict(summary))
    margin, equity = shorts_view._account("live")
    assert margin["ok"] is False and "override" in margin["text"] and equity["ok"] is True
    summary["ibkr_account_class"] = "margin"
    assert shorts_view._account("live")[0]["ok"] is True


def test_a_cover_alarm_reaches_the_session_every_window_polls(paper):
    from bot.session import get_session
    from short_sale import cover_alarm

    cover_alarm.reset_for_tests()
    try:
        cover_alarm.raise_("live", "rdyn", 400, kind="disconnected", text="Nova cannot cover 400 RDYN short on Live.")
        [alarm] = get_session()["shorts"]["day_cover"]["alarms"]
        assert (alarm["id"], alarm["venue"], alarm["symbol"], alarm["qty"], alarm["kind"]) == (
            "live:RDYN", "live", "RDYN", 400.0, "disconnected")
    finally:
        cover_alarm.reset_for_tests()
