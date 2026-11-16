"""One owner for Nova's buys (ADR 042): the pure rules and what the lanes tell the rest of Nova.

- NOT A TRADE is one rule (``setup_scanner.trade_verdict``) -- H;
- the session file's schema 4 -> 5 migration (``bot.persist``) -- A, E, F;
- triggers carry the grade, pillars, filter and spread -- H.

ADR 072 retired the automatic buys (the sizing, the shared daily count, proposals and who takes them).
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from constants_bot import BOT_SHORT_SETUPS
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


# -- the schema 4 -> 5 migration ------------------------------------------------------------------
def _write_v4(row: dict) -> None:
    from bot import persist

    persist._session_path().write_text(json.dumps(row), encoding="utf-8")
    persist._session = None


def test_a_v4_session_migrates_its_chosen_setup_sleeve_and_list_into_every_venue():
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
                                   "red_to_green": 0, "gap_and_go": 0, "pullback_dip": 0, "abcd": 0,
                                   **{sid: 0 for sid in BOT_SHORT_SETUPS}}   # every short setup starts Off (ADR 049)
    live = dial_of(row, "live")
    assert live["level"] == 1 and live["setup_levels"]["bull_flag"] == 1 and live["setup_levels"]["red_to_green"] == 1
    assert row["symbol_allowlist"] == ["GRML", "IMCC"]
    assert dial_of(row, "sim")["symbol_allowlist"] == ["GRML", "IMCC"] and live["symbol_allowlist"] == []
    for venue in ("paper", "live", "sim"):
        caps = dial_of(row, venue)["caps"]
        assert (caps["max_shares"], caps["bp_budget_usd"], caps["api_kinds"]) == (4, 40.0, ["buy_market", "exit_pos"])
        assert caps["risk_usd"] == 20.0 and "entries_per_day" not in caps    # retired 2026-10-27, read past
        assert "hard_lock_until_date" not in dial_of(row, venue)    # ADR 056: the day lock is gone
    assert "hard_lock_until_date" not in row


def test_an_unknown_version_still_refuses_loudly():
    from bot.persist import load_session

    _write_v4({"schema_version": 6, "level": 0})
    with pytest.raises(ValueError, match="schema_version=6"):
        load_session()


# -- triggers carry the facts --------------------------------------------------------
class _Host:
    source = "live"

    def __init__(self):
        self.saved, self.audits, self.events = [], [], []

    def save(self, row):
        self.saved.append(dict(row))

    def audit(self, **kw):
        self.audits.append(kw)

    def clock(self):
        return 1_790_000_000.0

    def on_trigger(self, event):
        self.events.append(event)


def _lane(host, grade="A", checks=None):
    from setup_scanner import lane_announce

    sid = "IMCC-2026-09-30-1"
    lane = SimpleNamespace(
        host=host, playing=True, proposals={}, alerts=[], journal=lambda *a, **k: None,
        p=SimpleNamespace(setup="bull_flag", template_id="default", template_rev=1, name="Default", side="long"),
        rows={sid: {"kind": "bull_flag", "trigger": 4.37, "entry_planned": 4.38, "stop": 4.30, "target1": 4.54,
                    "risk": 0.08, "grade": grade,
                    "pillars": {"checks": checks or {"a": True, "b": True, "c": True, "d": True, "e": True}}}})
    return lane, sid, lane_announce


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


def test_a_filtered_trigger_reaches_the_listeners_marked(tmp_path):
    """A trigger the filter kept out still reaches the listeners, marked, instead of saying nothing."""
    events: list[dict] = []
    host = _Host()
    host.on_trigger = events.append
    lane, sid, announce = _lane(host)
    asyncio.run(asyncio.sleep(0))
    announce.trigger(lane, "IMCC", sid, {"entry": 4.38, "risk": 0.08}, None, 1.0, filtered="float over 10M")
    assert events[0]["filtered"] == "float over 10M"
    assert of_event(events[0]) == {"ok": False, "reasons": ["the template's stock filter keeps it out: float over 10M"]}
