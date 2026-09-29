"""The grade you can see, and "not a trade" (operator report, 2026-09-29).

"So why does it think this is a good trade when it's obviously not?" -- AVAT's first pullback
triggered at 08:06 on one pillar of five with the tape at WAIT; the scanner scored it stopped out at
08:08, and the Trader's plan still read TRIGGERED at 08:28. The % change pillar was unknown on about
40% of arms, a forming row carried no grade, a filtered setup left its card five minutes after it
armed, and the plan never said the setup was not a trade.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from eyes import journal as eyes_journal
from eyes.journal_day import JournalDay
from eyes.playback import Playback
from setup_scanner import grade as grade_mod
from setup_templates.store import TemplateStore
from stock_read import decisions
from stock_read import plan as plan_mod
from tests.setup_scanner_fixtures import add, base_morning, leg_up
from tests.test_setup_scanner_engine import SYM, bar_msg
from tests.test_setup_scanner_lanes import FP, armed_bars, make, run

LEVELS = {"chosen": FP, "levels": {FP: 1}}


# -- the % change pillar -----------------------------------------------------------------------------
@pytest.fixture
def avat(monkeypatch):
    """AVAT at 08:06 on 2026-09-29: HOD Momo's snapshot had a price and no change."""
    import hod_momo
    from catalysts import live as catalyst_live
    from strategy import symbol_pillars

    snap = SimpleNamespace(price=1.96, change_pct=None, rvol=0.44, float_shares=25_546_730.0,
                           float_contradicted=False, shares_outstanding=37_914_805.0)
    boards = {"gappers": [{"symbol": "AVAT", "prev_close": 1.67}]}
    quote: dict = {}
    monkeypatch.setattr(hod_momo, "get_ticker_snapshot", lambda sym: snap)
    monkeypatch.setattr(catalyst_live, "verdict_for", lambda sym, now=None: {"verdict": "none_found"})
    monkeypatch.setattr(symbol_pillars, "raw_boards", lambda: boards)
    monkeypatch.setattr(symbol_pillars, "live_quote", lambda sym: quote.get(sym))
    return SimpleNamespace(snap=snap, boards=boards, quote=quote)


def test_the_change_pillar_is_measured_from_the_boards_prior_close_when_hod_has_none(avat):
    p = grade_mod.read_pillars("AVAT", 0.0)
    assert p["change_pct"] == pytest.approx((1.96 / 1.67 - 1) * 100)
    g, checks = grade_mod.grade(p)
    assert checks == {"price": False, "change": True, "rvol": False, "news": False, "float": False}
    assert g == "C" and grade_mod.pillar_count(checks) == {"passed": 1, "known": 5, "total": 5}


def test_hod_momos_own_change_wins_and_the_l1_close_is_the_last_resort(avat):
    avat.snap.change_pct = 12.5
    assert grade_mod.read_pillars("AVAT", 0.0)["change_pct"] == 12.5
    avat.snap.change_pct = None
    avat.boards.clear()
    assert grade_mod.read_pillars("AVAT", 0.0)["change_pct"] is None     # nobody knows: unknown, not 0
    avat.quote["AVAT"] = {"prev_close": 1.67}
    assert grade_mod.read_pillars("AVAT", 0.0)["change_pct"] == pytest.approx((1.96 / 1.67 - 1) * 100)


# -- the board and the journal -----------------------------------------------------------------------
def played_back(tmp_path: Path, journal: list[dict], session: str, at: float) -> list[dict]:
    """The rows a Sim playback of the live journal draws at ``at``."""
    path = tmp_path / f"{session}.jsonl"
    path.write_text("".join(eyes_journal.line(e) + "\n" for e in journal), encoding="utf-8")
    pb = Playback(JournalDay(path, session))
    pb.day.refresh()
    pb.advance(at)
    return pb.body(LEVELS)["rows"]


def card(rows: list[dict]) -> dict:
    keys = ("state", "reason", "setup_id", "grade", "graded", "phase", "trigger_tape", "outcome", "outcome_at")
    return {(r["setup_type"], r["symbol"]): tuple(str(r.get(k)) for k in keys) for r in rows}


def test_a_forming_row_carries_the_pillars_read_when_its_leg_made_its_high(tmp_path):
    templates = TemplateStore(tmp_path / "t.json")
    bars = leg_up(base_morning(), [4.08, 4.18, 4.28, 4.38])
    eng, _audits, journal, clock = make(tmp_path, bars, templates)
    run(eng, clock["t"])
    (row,) = eng.board(clock["t"])["rows"]
    # 4.35 ✓, +40% ✓, 8x ✓, a 30M float ✗ (over 20M), news unknown: three of five.
    assert row["state"] == "leg" and row["graded"] == "forming" and row["grade"] == "C"
    assert grade_mod.pillar_count(row["pillars"]["checks"]) == {"passed": 3, "known": 4, "total": 5}
    leg = next(e for e in journal if e["event"] == "leg")
    assert leg["grade"] == "C" and leg["pillars"]["checks"] == row["pillars"]["checks"]
    assert card(played_back(tmp_path, journal, eng.session, clock["t"])) == card([row])

    pb = add(list(bars), 4.38, 4.37, 4.30, 4.32, 30_000)[-1]
    eng.on_l1_minute("bar", SYM, bar_msg(pb))
    clock["t"] = pb.t + 61
    run(eng, clock["t"])
    (row,) = eng.board(clock["t"])["rows"]
    assert row["state"] == "armed" and row["graded"] == "armed" and row["phase"] is None


def test_a_filtered_setup_stays_on_its_card_through_its_trigger_and_a_playback_draws_it(tmp_path):
    templates = TemplateStore(tmp_path / "t.json")
    lf = templates.create(FP, name="Low float", values={"max_float_m": 10})
    templates.play(FP, lf.id)
    eng, audits, journal, clock = make(tmp_path, armed_bars(), templates)
    t0 = clock["t"]
    drawn: list[tuple[float, dict]] = []

    def step(to: float) -> None:
        while clock["t"] < to:                        # the engine beats every minute, as it does live
            clock["t"] = min(to, clock["t"] + 30)
            run(eng, clock["t"])
        drawn.append((clock["t"], card(eng.board(clock["t"])["rows"])))

    run(eng, t0)
    step(t0 + 600)                                    # ten minutes armed: it used to drop after five
    (row,) = eng.board(clock["t"])["rows"]
    assert row["state"] == "filtered" and row["phase"] == "armed"
    assert "float 30.0M over 10.0M" in row["reason"] and row["graded"] == "armed" and row["grade"] == "C"

    eng.on_l1_minute("last", SYM, {"price": 4.35, "ts": clock["t"], "bar_open": 4.32})
    step(clock["t"] + 1)
    (row,) = eng.board(clock["t"])["rows"]
    assert row["phase"] == "near" and row["distance"] == pytest.approx(0.02) and row["tape"] is None
    assert eng.playing.tape_view == {}                # a filtered setup reads no tape

    eng.on_l1_minute("last", SYM, {"price": 4.38, "ts": clock["t"], "bar_open": 4.32})
    step(clock["t"] + 1)
    triggered_at = clock["t"]
    (row,) = eng.board(clock["t"])["rows"]
    assert row["state"] == "filtered" and row["phase"] == "triggered"
    assert eng.proposals == {} and audits == []       # nothing proposed, nothing announced to the bot
    assert [r["template_id"] for r in eng.store.rows()] == ["default"]     # and it is never scored
    said = [e for e in journal if e["event"] == "state" and e.get("state") == "triggered"]
    assert said and said[-1]["triggered_at"] is not None

    step(triggered_at + 29 * 60)
    assert [r["phase"] for r in eng.board(clock["t"])["rows"]] == ["triggered"]
    step(triggered_at + 31 * 60)                      # the triggered rows' window, then off the card
    assert eng.board(clock["t"])["rows"] == []

    for at, rows in drawn:
        assert card(played_back(tmp_path, journal, eng.session, at)) == rows, at


def test_a_filtered_rearm_is_on_the_record_and_the_decisions_say_it_stays_out():
    line = {"event": "rearmed", "setup_type": FP, "ts": 1_790_683_560.0, "reason": "trigger 1.97, stop 1.94",
            "filtered": True, "setup": {"trigger": 1.97}}
    ev = decisions._journal_event(line)
    assert ev is not None and ev["title"].startswith("Re-armed, still kept out by the filter")


def test_a_trigger_carries_its_tape_and_the_first_touch_its_time(tmp_path):
    templates = TemplateStore(tmp_path / "t.json")
    eng, _audits, journal, clock = make(tmp_path, armed_bars(), templates)
    run(eng, clock["t"])
    eng.on_l1_minute("last", SYM, {"price": 4.35, "ts": clock["t"], "bar_open": 4.32})
    run(eng, clock["t"])
    clock["t"] += 2
    eng.on_l1_minute("last", SYM, {"price": 4.38, "ts": clock["t"], "bar_open": 4.32})
    run(eng, clock["t"])
    (row,) = eng.board(clock["t"])["rows"]
    assert row["state"] == "triggered" and row["trigger_tape"]["verdict"] == "go"
    assert row["outcome"] == "open" and row["outcome_at"] is None
    clock["t"] += 5
    eng.on_l1_minute("last", SYM, {"price": 4.55, "ts": clock["t"], "bar_open": 4.32})
    run(eng, clock["t"])
    (row,) = eng.board(clock["t"])["rows"]
    assert row["outcome"] == "target_first" and row["outcome_at"] == clock["t"]
    scored = [e for e in journal if e["event"] == "scored"]
    assert scored[-1]["outcome_at"] == clock["t"]
    assert card(played_back(tmp_path, journal, eng.session, clock["t"])) == card([row])


# -- the plan ---------------------------------------------------------------------------------------
TRIGGERED_AT = 1_790_683_578.0            # 2026-09-29 08:06:18 ET
AVAT_LANE = {
    "symbol": "AVAT", "setup_type": FP, "state": "triggered", "reason": "traded 1.98 over the 1.97 trigger",
    "kind": "second_pullback", "nth": 2, "setup_id": "AVAT-2026-09-29-1790683440",
    "setup": {"trigger": 1.97, "entry": 1.98, "stop": 1.9403, "risk": 0.0397, "target1": 2.0594,
              "triggered_at": TRIGGERED_AT, "trigger_price": 1.9799},
    "grade": "C", "pillars": {"checks": {"price": False, "change": True, "rvol": False, "news": False,
                                         "float": False}},
    "graded": "armed", "phase": None, "tape": None,
    "trigger_tape": {"verdict": "wait", "reasons": ["no green on the tape yet"]},
    "outcome": "stop_first", "outcome_at": TRIGGERED_AT + 102, "bar_r": -1.0, "chosen": False,
    "window": {"start": "07:00", "end": "11:30", "state": "open"},
    "rules": {"stop_cap": 0.2, "min_stop": 0.03, "target_r": 2.0, "target_mode": "leg_or_r"}, "forming": None,
}
CTX = {"price": 1.9946, "levels": {}, "macd_hist": 0.002, "ema9": 1.97, "median_range": 0.01, "asks": [],
       "flow": None, "bid_pulls": 0, "halted": False, "bars": []}


def test_avat_at_0828_is_not_a_trade_and_says_why():
    plan = plan_mod.build([AVAT_LANE], {**CTX, "spread": 0.10}, now=TRIGGERED_AT + 1_340)
    assert plan["state"] == "triggered" and plan["grade"] == "C"
    assert plan["pillars"] == {"passed": 1, "known": 5, "total": 5}
    assert plan["tape"] == {"verdict": "wait", "reasons": ["no green on the tape yet"]}  # the trigger's, not null
    assert plan["result"] == {"outcome": "stop_first", "at": TRIGGERED_AT + 102, "r": -1.0,
                              "text": "the stop printed first at 08:08 (-1.00R)"}
    assert plan["trade"]["ok"] is False
    assert plan["trade"]["reasons"] == [
        "grade C: 1 of 5 pillars",
        "it triggered with the tape at WAIT: no green on the tape yet",
        "it already played out: the stop printed first at 08:08 (-1.00R)",
        "the spread 0.10 is at least the 0.04 risk: a buy at the ask sits at or under its stop on the bid",
    ]
    spread = next(c for c in plan["checks"] if c["id"] == "spread")
    assert spread["state"] == "bad"


def test_a_b_grade_near_its_trigger_on_a_tight_book_is_a_trade():
    lane = {**AVAT_LANE, "state": "near", "grade": "B", "distance": 0.01, "trigger_tape": None,
            "tape": {"verdict": "go", "reasons": []}, "outcome": None, "outcome_at": None, "bar_r": None,
            "pillars": {"checks": {"price": True, "change": True, "rvol": True, "news": False, "float": True}}}
    plan = plan_mod.build([lane], {**CTX, "spread": 0.01}, now=TRIGGERED_AT)
    assert plan["state"] == "near" and plan["result"] is None
    assert plan["trade"] == {"ok": True, "reasons": []}
    assert next(c for c in plan["checks"] if c["id"] == "spread")["state"] == "ok"


def test_a_filtered_setup_is_not_a_trade_and_leaves_the_plan_with_the_triggered_window():
    lane = {**AVAT_LANE, "state": "filtered", "phase": "near", "grade": "B", "trigger_tape": None,
            "outcome": None, "outcome_at": None, "bar_r": None,
            "reason": "filtered: float 25.5M over 10.0M",
            "pillars": {"checks": {"price": True, "change": True, "rvol": True, "news": False, "float": True}}}
    plan = plan_mod.build([lane], CTX, now=TRIGGERED_AT)
    assert plan["state"] == "near"
    assert plan["trade"]["reasons"] == ["the template's stock filter keeps it out: float 25.5M over 10.0M"]
    gone = {**lane, "phase": "triggered"}
    assert plan_mod.build([gone], CTX, now=TRIGGERED_AT + 29 * 60)["state"] == "triggered"
    assert plan_mod.build([gone], CTX, now=TRIGGERED_AT + 31 * 60) is None


def test_the_operators_own_plan_has_no_verdict():
    plan = plan_mod.build([], {**CTX, "spread": 0.02}, now=TRIGGERED_AT, entry=2.00, stop=1.90)
    assert plan["source"] == "manual" and plan["trade"] is None and plan["pillars"] is None
    assert plan["result"] is None
