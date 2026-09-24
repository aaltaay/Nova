"""The tape flow on the record (ADR 034): a replayed lane reads it after the trigger,
a template's flush exit acts on the scoring, a backtest sweeps variants against a
base, and the study measures what an onset was followed by."""
from __future__ import annotations

import json

import pytest

from eyes import backtest, flow_study
from eyes.recording import Recording, _sample_books, _ticks
from eyes.replay import EyesReplay
from setup_scanner.bars import Bar
from setup_scanner.lane_params import flow_params, flush_policy, lane_params
from setup_scanner.tape_flow import DEFAULT_FLOW, FlowParams
from setup_templates import catalogue
from setup_templates.catalogue import TemplateError
from setup_templates.store import TemplateStore, default_template, set_store_for_tests
from tests.test_eyes import DAY, SYM, _pillars, bars


def flush_recording() -> Recording:
    """The fixture morning (``tests/test_eyes``): green into the trigger at 4.38, then the tape flushes
    -- every print at the bid, the price stepping down to 4.33, the bids thin -- and sits there."""
    b = bars()
    armed_at = b[-1].t + 60
    after = [Bar(t=armed_at + k * 60, o=4.36, h=4.39 if k == 0 else 4.36, lo=4.32, c=4.33, v=5000) for k in range(8)]
    prints, books = [], []
    for i in range(0, 240):
        ts = armed_at + i * 0.5
        px = round(max(4.33, 4.37 - 0.001 * (i - 30)), 3) if i >= 30 else 4.38
        if i < 30:
            books.append({"ts": ts, "bids": [{"price": 4.34, "size": 4000}], "asks": [{"price": 4.37, "size": 3000}]})
        else:     # the bid follows the price down, thin; sellers stack the ask
            books.append({"ts": ts, "bids": [{"price": round(px - 0.01, 3), "size": 100}],
                          "asks": [{"price": round(px + 0.01, 3), "size": 6000}]})
        if i < 20 and i % 2 == 0:
            prints.append({"ts": ts, "price": 4.35, "size": 100, "side": "ask", "exchange": "NSDQ", "conditions": ""})
        elif 20 <= i < 30:
            prints.append({"ts": ts, "price": 4.38, "size": 300, "side": "ask", "exchange": "NSDQ", "conditions": ""})
        elif 30 <= i < 80:
            prints.append({"ts": ts, "price": px, "size": 500, "side": "bid", "exchange": "NSDQ", "conditions": ""})
        elif i % 4 == 0:
            prints.append({"ts": ts, "price": 4.33, "size": 100, "side": "bid", "exchange": "NSDQ", "conditions": ""})
    sampled = _sample_books(books, 0.5)
    return Recording(date=DAY, symbol=SYM, prints=prints, print_ts=[p["ts"] for p in prints],
                     ticks=_ticks(prints, 1.0), books=sampled, book_ts=[t for t, _ in sampled], bars=b + after,
                     bars_source="archive", spans=[(armed_at, armed_at + 120)], prev_close=3.0)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_EYES_DIR", str(tmp_path))
    s = TemplateStore(tmp_path / "t.json")
    set_store_for_tests(s)
    return s


# -- the catalogue and the lane's numbers ---------------------------------------------------------
def test_the_default_template_keeps_the_pre_registered_rules():
    p = lane_params(default_template("first_pullback"))
    assert p.gate.entry_mode == "gate" and p.flush.mode == "off" and p.flow == DEFAULT_FLOW
    for setup in ("first_pullback", "bull_flag", "flat_top_breakout", "red_to_green"):
        assert catalogue.defaults(setup)["flush_exit"] == "off"


def test_a_template_saved_before_the_flow_existed_reads_the_defaults():
    old = {k: v for k, v in catalogue.defaults("first_pullback").items() if not k.startswith(("flow_", "flush_"))}
    old.pop("tape_entry")
    assert flow_params(old) == DEFAULT_FLOW and flush_policy(old).mode == "off"


def test_values_convert_to_the_flows_own_units_and_nonsense_is_refused():
    v = catalogue.validate("first_pullback", {"flow_drift_full_pct": 1.0, "flush_exit": "tighten", "flush_min_r": 0.5})
    assert flow_params(v).drift_full == pytest.approx(0.01)
    assert flush_policy(v).mode == "tighten" and flush_policy(v).min_r == 0.5
    with pytest.raises(TemplateError, match="flow weight"):
        catalogue.validate("first_pullback", {"flow_w_imbalance": 0, "flow_w_pace": 0, "flow_w_drift": 0,
                                              "flow_w_book": 0})
    with pytest.raises(TemplateError, match="baseline"):
        catalogue.validate("first_pullback", {"flow_window_sec": 30, "flow_baseline_sec": 20})


def test_command_line_words_read_in_the_parameters_own_kind():
    assert catalogue.parse_text("first_pullback", "flush_exit", "off") == "off"      # a choice, not "none"
    assert catalogue.parse_text("first_pullback", "flush_min_r", "off") is None     # a nullable number
    assert catalogue.parse_text("first_pullback", "flow_window_sec", "5") == 5.0
    assert catalogue.parse_text("first_pullback", "require_catalyst", "yes") is True
    with pytest.raises(TemplateError):
        catalogue.parse_text("first_pullback", "nope", "1")


# -- the replay ------------------------------------------------------------------------------------
def test_a_replayed_flush_exits_the_template_that_says_so_and_only_it(store):
    out = store.create("first_pullback", name="Flush out", values={"flush_exit": "exit", "flush_hold_sec": 5})
    events: list[dict] = []
    rep = EyesReplay(flush_recording(), [default_template("first_pullback"), out], source="backtest",
                     all_propose=True, journal=events.append, pillars=_pillars)
    rep.run_to_end()
    rows = {r["template_id"]: r for r in rep.rows.values() if r.get("triggered_at")}
    assert set(rows) == {"default", out.id}
    base, mine = rows["default"], rows[out.id]
    assert base["trigger_tape"]["flow"]["label"] in ("burst", "neutral", "quiet")    # the flow rides on the read
    assert mine["bar_exit_reason"] == "flush" and mine["flush_action"] == "exit"
    assert base["bar_exit_reason"] == "bailout" and base["flush_action"] is None
    assert mine["bar_r"] > base["bar_r"]
    flow_lines = [e for e in events if e["event"] == "flow" and e["label"] == "flush"]
    assert {e["template"] for e in flow_lines} == {"default", out.id}                  # every lane journals it
    [flush_line] = [e for e in events if e["event"] == "flush"]
    assert flush_line["template"] == out.id and flush_line["action"] == "exit"
    lane = next(lane for lane in rep.lanes if lane.p.template_id == out.id)
    # The newest reading comes after the recorded stretch ended: no tape there reads blind, never quiet.
    assert lane.flow_last[mine["id"]]["label"] == "blind"


def test_a_backtest_sweeps_variants_against_the_base_without_storing_them(store):
    variants = [{"name": "base", "values": {}}, {"values": {"flush_exit": "exit", "flush_hold_sec": 5}},
                {"values": {"flush_exit": "tighten", "flush_hold_sec": 5, "flush_trail_r": 0.25}}]
    man = backtest.run(sessions=[(DAY, SYM)], load=lambda d, s: flush_recording(), variants=variants,
                       run_id="20260924-100000-abcdef")
    assert man["status"] == "done" and [t["id"] for t in man["templates"]] == ["var-01", "var-02", "var-03"]
    assert man["templates"][1]["variant"] is True and man["templates"][1]["overrides"]["flush_exit"] == "exit"
    assert [t.id for t in store.templates("first_pullback")] == ["default"]           # nothing stored
    summary = backtest.read_summary(man["run_id"])["templates"]
    assert summary["var-01"]["vs_base"] is None and summary["var-01"]["exits"] == {"bailout": 1}
    assert summary["var-02"]["exits"] == {"flush": 1} and summary["var-02"]["flush"] == {"exit": 1}
    vs = summary["var-02"]["vs_base"]
    assert vs["paired"] == 1 and vs["better"] == 1 and vs["avg_r_delta"] > 0
    assert "flow_at_trigger" in summary["var-02"]["summary"]["by"]


def test_a_variant_of_an_unknown_template_or_too_many_are_refused(store):
    with pytest.raises(TemplateError):
        backtest.variant_templates("first_pullback", [{"base": "t-nope", "values": {}}])
    with pytest.raises(TemplateError):
        backtest.variant_templates("first_pullback", [{"values": {}}] * 60)
    with pytest.raises(TemplateError):
        backtest.variant_templates("first_pullback", [{"values": {"flush_exit": "sometimes"}}])


# -- the study ------------------------------------------------------------------------------------
def test_the_study_measures_what_followed_an_onset_and_never_crosses_a_gap():
    rec = flush_recording()
    a, b = rec.spans[0]
    rows = flow_study.samples(rec, FlowParams(), flow_study.StudyParams(horizons=(10, 60)))
    assert rows and rows[0]["ts"] >= a + 10 and rows[-1]["ts"] <= b
    assert all(r["fwd"][60] is None for r in rows if r["ts"] + 60 > b)               # past the stretch: not measured
    [flush] = [r for r in flow_study.onsets(rows, 30) if r["label"] == "flush"]
    assert flush["fwd"][10] is not None and flush["fwd"][10] <= 0
    ans = flow_study.study([rec], FlowParams(), flow_study.StudyParams(horizons=(10, 60)))
    assert ans["onsets"]["flush"]["10"]["n"] == 1 and ans["recordings"][0]["onsets"]["flush"] == 1
    assert ans["seconds"] == len(rows) and set(ans["onsets_by_context"]) == {"burst", "flush"}
    assert json.dumps(ans)                                                            # plain JSON all the way


def test_context_names_the_minute_before():
    assert flow_study.context(None, 50) == "unknown"
    assert flow_study.context(80, 50) == "after_rise" and flow_study.context(-60, 50) == "after_fall"
    assert flow_study.context(10, 50) == "flat"
