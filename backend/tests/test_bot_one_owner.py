"""One owner for Nova's buys (ADR 042): the pure rules and what the lanes tell the rest of Nova.

- NOT A TRADE is one rule (``setup_scanner.trade_verdict``) -- H;
- one size for every Nova automatic buy (``bot.sizing``) -- E;
- the session file's schema 4 -> 5 migration (``bot.persist``) -- A, E, F;
- the shared daily count folded from the audit stream (``bot.entry_rules``) -- E;
- proposals and triggers carry the grade, pillars, filter and spread, and who takes them -- H.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from bot.sizing import size
from setup_scanner.trade_verdict import of_event, verdict


# -- NOT A TRADE -------------------------------------------------------------------------
def test_a_clean_setup_is_a_trade():
    assert verdict(grade="A", pillars={"passed": 5, "known": 5, "total": 5}, spread=0.02, risk=0.13) == {
        "ok": True, "reasons": []}


def test_every_reason_it_is_not_a_trade_is_said():
    out = verdict(grade="C", pillars={"passed": 2, "known": 4, "total": 5}, filtered="filtered: float over 10M",
                  triggered=True, tape={"verdict": "wait", "reasons": ["a seller at 4.40"]},
                  played_out="the stop printed first at 09:41", spread=0.15, risk=0.13)
    assert out["ok"] is False and out["reasons"] == [
        "grade C: 2 of 5 pillars",
        "the template's stock filter keeps it out: float over 10M",
        "it triggered with the tape at WAIT: a seller at 4.40",
        "it already played out: the stop printed first at 09:41",
        "the spread 0.15 is at least the 0.13 risk: a buy at the ask sits at or under its stop on the bid",
    ]


def test_the_tape_counts_only_at_a_trigger_and_an_unknown_spread_never_kills():
    assert verdict(grade="B", tape={"verdict": "wait"}, spread=None, risk=0.1)["ok"] is True
    assert of_event({"grade": "A", "setup": {"risk": 0.1}, "tape": {"verdict": "go"}, "spread": None})["ok"] is True
    assert of_event({"grade": "A", "setup": {"risk": 0.1}, "tape": {"verdict": "veto"}})["ok"] is False


def test_the_plan_reads_the_same_rule():
    from stock_read.plan import trade_verdict

    plan = {"source": "setup", "grade": "C", "pillars": {"passed": 1, "known": 5, "total": 5}, "state": "armed",
            "tape": None, "result": None, "risk": 0.1}
    assert trade_verdict(plan, {"state": "armed"}, 0.02) == {"ok": False, "reasons": ["grade C: 1 of 5 pillars"]}
    assert trade_verdict({**plan, "source": "manual"}, None) is None


# -- one size -------------------------------------------------------------------------------
@pytest.mark.parametrize("args, qty, capped, words", [
    ((20, 10.02, 9.89, 10, 1000), 10, "max_shares", "capped at the sleeve's 10 max shares"),
    ((20, 10.02, 9.89, 10, 35), 3, "budget", "cut to what the $35.00 budget buys at 10.02"),
    ((1, 10.02, 9.89, 10, 1000), 7, None, "7 shares: $1 risk / $0.13 a share = 7"),
    ((20, 10.02, 9.89, None, None), 153, None, "153 shares"),
    ((0.05, 10.02, 9.89, 10, 1000), 0, None, "under one share"),
    ((20, 10.02, 10.10, 10, 1000), 0, None, "not under the entry"),
    ((20, 10.02, 9.89, 10, 5), 0, "budget", "buys no share"),
    ((None, 10.02, 9.89, 10, 1000), 0, None, "no risk per trade"),
])
def test_one_size_for_every_nova_automatic_buy(args, qty, capped, words):
    out = size(*args)
    assert out["qty"] == qty and out["capped_by"] == capped and words in out["text"]


# -- the schema 4 -> 5 migration ------------------------------------------------------------------
def _write_v4(row: dict) -> None:
    from bot import persist

    persist._session_path().write_text(json.dumps(row), encoding="utf-8")
    persist._session = None


def test_a_v4_session_migrates_its_chosen_setup_sleeve_list_and_lock_into_every_venue():
    from bot.persist import load_session
    from bot.venue_levels import dial_of
    from sim.mode import set_venue

    set_venue("paper", persist=False)
    _write_v4({"schema_version": 4, "level": 2, "level_venue": "paper", "setup": "bull_flag", "strategy": "small-cap",
               "setup_levels": {"first_pullback": 1}, "symbol_allowlist": ["GRML", "IMCC"],
               "caps": {"max_shares": 4, "bp_budget_usd": 40, "working_ttl_sec": 5, "extended_hours": True,
                        "allowlist": ["buy_market", "exit_pos"]},
               "advise": {"enabled": True}, "hard_lock_until_date": "2026-09-30",
               "venue_levels": {"live": {"level": 1, "setup_levels": {"red_to_green": 1}}}})
    row = load_session()
    for gone in ("setup", "strategy", "advise"):
        assert gone not in row
    assert row["schema_version"] == 5 and row["level_venue"] == "paper"
    assert row["setup_levels"] == {"first_pullback": 1, "bull_flag": 2, "flat_top_breakout": 0, "flat_top_5m": 0,
                                   "red_to_green": 0, "gap_and_go": 0}
    live = dial_of(row, "live")
    assert live["level"] == 1 and live["setup_levels"]["bull_flag"] == 1 and live["setup_levels"]["red_to_green"] == 1
    assert row["symbol_allowlist"] == ["GRML", "IMCC"]
    assert dial_of(row, "sim")["symbol_allowlist"] == ["GRML", "IMCC"] and live["symbol_allowlist"] == []
    for venue in ("paper", "live", "sim"):
        caps = dial_of(row, venue)["caps"]
        assert (caps["max_shares"], caps["bp_budget_usd"], caps["api_kinds"]) == (4, 40.0, ["buy_market", "exit_pos"])
        assert caps["risk_usd"] == 20.0 and caps["entries_per_day"] == 1
        assert dial_of(row, venue)["hard_lock_until_date"] == "2026-09-30"


def test_an_unknown_version_still_refuses_loudly():
    from bot.persist import load_session

    _write_v4({"schema_version": 6, "level": 0})
    with pytest.raises(ValueError, match="schema_version=6"):
        load_session()


# -- the shared daily count -------------------------------------------------------------------------
def test_the_daily_count_folds_the_bot_and_auto_entry_and_gives_a_miss_back():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from bot.entry_rules import today

    now = datetime(2026, 9, 22, 9, 0, tzinfo=ZoneInfo("America/New_York"))
    day = {"venue_day": "2026-09-22"}
    rows = [
        {"action": "buy_setup_limit", "outcome": "ok", "order_id": 1, "venue": "paper", "timestamp": 1,
         "inputs": {**day, "symbol": "AAA", "setup_type": "bull_flag", "setup_id": "A"}},
        {"action": "bot_trade", "outcome": "missed", "order_id": 1, "venue": "paper", "timestamp": 2,
         "inputs": {**day, "setup_id": "A"}},
        {"action": "stock_mode", "outcome": "sent", "order_id": 7, "venue": "paper", "timestamp": 3,
         "inputs": {**day, "symbol": "BBB", "kind": "auto_entry", "setup_type": "first_pullback"}},
        {"action": "stock_mode", "outcome": "filled", "order_id": 7, "venue": "paper", "timestamp": 4,
         "inputs": {**day, "kind": "auto_entry"}},
        {"action": "stock_mode", "outcome": "sent", "order_id": 9, "venue": "paper", "timestamp": 5,
         "inputs": {**day, "symbol": "CCC", "kind": "approve"}},
        {"action": "buy_market", "outcome": "ok", "venue": "live", "timestamp": 6, "inputs": {**day}},
        {"action": "buy_market", "outcome": "ok", "venue": "paper", "timestamp": 7,
         "inputs": {"venue_day": "2026-09-21"}},
    ]
    out = today("paper", now, cap=2, rows=rows)
    assert out["count"] == 1 and out["cap"] == 2 and out["approved"] == 1 and out["venue_day"] == "2026-09-22"
    assert [(e["symbol"], e["by"], e["outcome"]) for e in out["entries"]] == [
        ("AAA", "bot", "missed"), ("BBB", "auto_entry", "filled")]


# -- proposals and triggers carry the facts --------------------------------------------------------
class _Host:
    source = "live"

    def __init__(self, taker=None):
        self.saved, self.audits, self.events = [], [], []
        self._taker = taker

    def save(self, row):
        self.saved.append(dict(row))

    def audit(self, **kw):
        self.audits.append(kw)

    def clock(self):
        return 1_790_000_000.0

    def on_trigger(self, event):
        self.events.append(event)

    def taker(self, sym, setup_type):
        return self._taker


def _lane(host, grade="A", checks=None):
    from setup_scanner import lane_announce

    sid = "IMCC-2026-09-30-1"
    lane = SimpleNamespace(
        host=host, playing=True, proposals={}, alerts=[], journal=lambda *a, **k: None,
        p=SimpleNamespace(setup="bull_flag", template_id="default", template_rev=1, name="Default"),
        rows={sid: {"kind": "bull_flag", "trigger": 4.37, "entry_planned": 4.38, "stop": 4.30, "target1": 4.54,
                    "risk": 0.08, "grade": grade,
                    "pillars": {"checks": checks or {"a": True, "b": True, "c": True, "d": True, "e": True}}}})
    return lane, sid, lane_announce


def test_a_proposal_says_who_takes_it():
    host = _Host(taker="bot")
    lane, sid, announce = _lane(host)
    prop = announce.propose(lane, "IMCC", sid, {"verdict": "go", "reasons": ["green"], "metrics": {"spread": 0.02}},
                            1_790_000_000.0)
    assert prop["taken_by"] == "bot" and prop["not_a_trade"] is None
    assert prop["grade"] == "A" and prop["pillars"] == {"passed": 5, "known": 5, "total": 5} and prop["spread"] == 0.02
    assert "the bot is taking it" in host.audits[0]["reason"]


def test_a_proposal_that_is_not_a_trade_says_so_and_nobody_takes_it():
    host = _Host(taker="auto_entry")
    lane, sid, announce = _lane(host, grade="C", checks={"a": True, "b": False, "c": False, "d": None, "e": True})
    prop = announce.propose(lane, "IMCC", sid, {"verdict": "go", "reasons": [], "metrics": {"spread": 0.01}},
                            1_790_000_000.0)
    assert prop["not_a_trade"] == {"reasons": ["grade C: 2 of 5 pillars"]} and prop["taken_by"] is None
    assert "not a trade: grade C" in host.audits[0]["reason"]


def test_a_trigger_carries_the_grade_pillars_filter_and_spread():
    host = _Host()
    lane, sid, announce = _lane(host)
    announce.trigger(lane, "IMCC", sid, {"entry": 4.38, "risk": 0.08}, {"verdict": "go", "reasons": [],
                                                                        "metrics": {"spread": 0.03}}, 1.0)
    announce.trigger(lane, "IMCC", sid, {"entry": 4.38, "risk": 0.08}, None, 2.0, filtered="price over 20")
    first, second = host.events
    assert first["grade"] == "A" and first["pillars"]["passed"] == 5 and first["spread"] == 0.03
    assert first["filtered"] is None and first["setup_type"] == "bull_flag"
    assert second["filtered"] == "price over 20" and second["tape"] is None


def test_the_live_taker_follows_activate_the_level_and_the_stocks_mode():
    from bot.arming import issue_arm_token
    from bot.autonomy import apply_patch
    from bot.first_pullback.admit import taker
    from constants_hot_list import HOT_LIST_FILE
    from paths import cache_dir
    from stock_mode import store
    from tests.bot_helpers import list_hot, on_practice, set_symbols

    on_practice()
    apply_patch({"level": 2, "setup_levels": {"bull_flag": 2, "first_pullback": 1}}, desk=True)
    set_symbols("AAA")
    assert taker("AAA", "bull_flag") is None                         # not active
    issue_arm_token()
    assert taker("AAA", "bull_flag") == "bot"
    assert taker("AAA", "first_pullback") is None                    # at Eyes: the bot does not take it
    store.set_switch("BBB", {"buy": "nova", "sell": "you"})
    assert taker("BBB", "bull_flag") == "auto_entry"                 # off the hot list: the list is no rule
    assert taker("CCC", "bull_flag") is None
    (cache_dir() / HOT_LIST_FILE).unlink()                           # today's 04:00 reset not known to have run
    assert taker("AAA", "bull_flag") is None and taker("BBB", "bull_flag") is None
    list_hot()
    assert taker("AAA", "bull_flag") == "bot" and taker("BBB", "bull_flag") == "auto_entry"


def test_a_filtered_trigger_reaches_the_listeners_marked(tmp_path):
    """The bot and Auto-entry say they skipped a setup the filter kept out instead of saying nothing."""
    events: list[dict] = []
    host = _Host()
    host.on_trigger = events.append
    lane, sid, announce = _lane(host)
    asyncio.run(asyncio.sleep(0))
    announce.trigger(lane, "IMCC", sid, {"entry": 4.38, "risk": 0.08}, None, 1.0, filtered="float over 10M")
    assert events[0]["filtered"] == "float over 10M"
    assert of_event(events[0]) == {"ok": False, "reasons": ["the template's stock filter keeps it out: float over 10M"]}
