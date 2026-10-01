"""The bot's parameters on a setup template (operator ask 2026-09-30, "make everything visible"):
they never start the read-out over, the bot's daily cap left the template, the bot's window sits
inside the arming window (a write outside is refused, a saved one outside is clipped and says so),
and a setup without a scanner gets no template."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import constants_setups as cs
from setup_scanner.detectors import window as scanner_window
from setup_scanner.lane_params import PATTERNS, lane_params
from setup_templates import catalogue, windows
from setup_templates.catalogue import TemplateError
from setup_templates.store import TemplateStore, default_template, set_store_for_tests

FP, R2G = "first_pullback", "red_to_green"


@pytest.fixture()
def store(tmp_path):
    s = TemplateStore(tmp_path / "setup-templates.json")
    set_store_for_tests(s)
    yield s
    set_store_for_tests(None)


def _write(path, setup, templates, in_play=None):
    path.write_text(json.dumps({"schema_version": 1, "setups": {setup: {"in_play": in_play, "templates": templates}}}),
                    encoding="utf-8")


# -- the bot's parameters are not the scanner's rules -----------------------------------------
def test_the_bot_window_is_not_in_the_fingerprint_or_the_params_hash():
    v = catalogue.defaults(FP)
    moved = {**v, "bot_window_start": "08:00", "bot_window_end": "09:00"}
    assert catalogue.fingerprint(moved) == catalogue.fingerprint(v)
    assert catalogue.fingerprint({**v, "leg_pct": 6.0}) != catalogue.fingerprint(v)
    assert catalogue.scanner_values(moved) == catalogue.scanner_values(v)
    assert catalogue.BOT_KEYS == {"bot_window_start", "bot_window_end"}


def test_the_wire_says_which_parameters_restart_the_read_out():
    for sid in cs.SETUPS_READOUT_KINDS:          # every setup with a scanner
        params = [p for g in catalogue.wire(sid)["groups"] for p in g["params"]]
        assert {p["key"] for p in params if p["affects_readout"] is False} == {"bot_window_start", "bot_window_end"}
        assert all(p["affects_readout"] is True for p in params if p["group"] != "bot")
    gng = [p for g in catalogue.wire("gap_and_go")["groups"] for p in g["params"]]
    assert gng and not any(p["affects_readout"] for p in gng)    # no scanner, no read-out to restart


def test_a_bot_only_edit_keeps_the_revision_and_is_saved(store, tmp_path):
    t = store.create(FP, name="Mine", values={"stop_cap": 0.3})
    edited, rules_changed = store.update(FP, t.id, values={"bot_window_start": "08:00", "bot_window_end": "09:30"})
    assert rules_changed is False and edited.rev == 1
    assert (edited.values["bot_window_start"], edited.values["bot_window_end"]) == ("08:00", "09:30")
    assert edited.fingerprint == t.fingerprint and lane_params(edited).params_hash == lane_params(t).params_hash
    fresh = TemplateStore(tmp_path / "setup-templates.json").get(FP, t.id)
    assert fresh.rev == 1 and fresh.values["bot_window_end"] == "09:30"
    both, rules_changed = store.update(FP, t.id, values={"bot_window_end": "10:00", "leg_pct": 6})
    assert rules_changed is True and both.rev == 2


def test_a_bot_window_edit_keeps_the_scanners_lane(tmp_path):
    from tests.test_setup_scanner_lanes import armed_bars, make, run

    templates = TemplateStore(tmp_path / "t.json")
    t = templates.create(FP, name="Mine")
    eng, _audits, _journal, clock = make(tmp_path, armed_bars(), templates)
    run(eng, clock["t"])
    lane = eng.lanes[1]
    templates.update(FP, t.id, values={"bot_window_end": "09:00"})
    run(eng, clock["t"] + 1)
    assert eng.lanes[1] is lane and (lane.p.template_id, lane.p.template_rev) == (t.id, 1)


# -- bot_entries_per_day left the template -----------------------------------------------------
def test_a_write_that_sends_the_retired_daily_cap_is_refused_with_where_it_went(store):
    for call in (lambda: store.create(FP, name="X", values={"bot_entries_per_day": 2}),
                 lambda: catalogue.validate(FP, {"bot_entries_per_day": 1})):
        with pytest.raises(TemplateError) as err:
            call()
        assert err.value.code == "TEMPLATE_INVALID" and err.value.field == "bot_entries_per_day"
        assert "sleeve" in err.value.message and "entries_per_day" in err.value.message
    assert "bot_entries_per_day" not in {p["key"] for g in catalogue.wire(FP)["groups"] for p in g["params"]}


def test_a_saved_template_with_the_daily_cap_loads_without_it_and_says_so(tmp_path):
    path = tmp_path / "t.json"
    values = {**catalogue.defaults(FP), "bot_entries_per_day": 2}
    _write(path, FP, [{"id": "t-old", "name": "Old", "rev": 3, "values": values},
                      {"id": "t-two", "name": "Two", "rev": 1, "values": catalogue.defaults(FP)}], in_play="t-old")
    s = TemplateStore(path)
    old = s.get(FP, "t-old")
    assert old.error is None and old.rev == 3 and s.in_play(FP).id == "t-old"
    assert "bot_entries_per_day" not in old.values and old.retired == {"bot_entries_per_day": 2}
    wired = old.wire(in_play=True)
    assert wired["retired"] == [{"key": "bot_entries_per_day", "value": 2, "text": catalogue.RETIRED["bot_entries_per_day"]}]
    assert "bot_entries_per_day" not in wired["values"]
    # Another template's write and a rename keep what was saved; saving its values drops it.
    s.update(FP, "t-two", values={"leg_pct": 7})
    s.update(FP, "t-old", name="Old one")
    assert json.loads(path.read_text(encoding="utf-8"))["setups"][FP]["templates"][0]["values"]["bot_entries_per_day"] == 2
    saved, rules_changed = s.update(FP, "t-old", values={})
    assert rules_changed is False and saved.rev == 3 and saved.retired == {}
    assert "bot_entries_per_day" not in json.loads(path.read_text(encoding="utf-8"))["setups"][FP]["templates"][0]["values"]


# -- the bot's window sits inside the arming window -------------------------------------------
def test_every_default_bot_window_sits_inside_its_arming_window_and_red_to_green_opens_at_the_open():
    for sid in cs.SETUPS_READOUT_KINDS:
        t = default_template(sid)
        assert t.bot_window["clipped"] is False and t.bot_window["empty"] is False
        assert windows.problem(sid, t.values) is None
    r2g = default_template(R2G)
    assert (r2g.values["bot_window_start"], r2g.values["bot_window_end"]) == ("09:30", "10:00")
    assert r2g.bot_window["arming"] == {"start": "09:30", "end": "10:30"}
    assert r2g.rev == cs.SETUP_TEMPLATE_DEFAULT_REV       # a bot parameter: the read-out keeps its evidence


def test_the_arming_window_is_the_scanners_own():
    for sid in cs.SETUPS_READOUT_KINDS:
        v = catalogue.defaults(sid)
        assert windows.arming_window(sid, v) == scanner_window(sid, PATTERNS[sid](v))
    assert windows.arming_window("gap_and_go", catalogue.defaults("gap_and_go")) is None


@pytest.mark.parametrize("values, field, words", [
    ({"bot_window_start": "08:00"}, "bot_window_start", "before the setup arms at 09:30"),
    ({"bot_window_end": "11:00"}, "bot_window_end", "after the setup stops arming at 10:30"),
    ({"r2g_cutoff": "09:45"}, "bot_window_end", "the arming window 09:30-09:45"),
])
def test_a_write_outside_the_arming_window_is_refused_naming_the_field_and_both_windows(store, values, field, words):
    with pytest.raises(TemplateError) as err:
        store.create(R2G, name="X", values=values)
    assert err.value.code == "TEMPLATE_INVALID" and err.value.field == field
    assert words in err.value.message and "must sit inside the arming window" in err.value.message
    t = store.create(R2G, name="Inside", values={"bot_window_start": "09:45", "bot_window_end": "10:30"})
    with pytest.raises(TemplateError) as err:
        store.update(R2G, t.id, values=values)
    assert err.value.field == field


def test_a_saved_window_outside_is_clipped_when_read_and_says_so(tmp_path):
    path = tmp_path / "t.json"
    wide = {**catalogue.defaults(R2G), "bot_window_start": "07:00", "bot_window_end": "10:00"}
    early = {**catalogue.defaults(R2G), "bot_window_start": "07:00", "bot_window_end": "09:00"}
    _write(path, R2G, [{"id": "t-wide", "name": "Wide", "rev": 4, "values": wide},
                       {"id": "t-early", "name": "Early", "rev": 1, "values": early}], in_play="t-wide")
    s = TemplateStore(path)
    t = s.in_play(R2G)
    assert t.id == "t-wide" and t.error is None and t.rev == 4
    assert (t.values["bot_window_start"], t.values["bot_window_end"]) == ("09:30", "10:00")
    assert t.bot_window["clipped"] is True and t.bot_window["stored"] == {"start": "07:00", "end": "10:00"}
    assert "07:00-10:00" in t.bot_window["note"] and "09:30-10:00" in t.bot_window["note"]
    assert t.wire(in_play=True)["bot_window"] == t.bot_window
    gone = s.get(R2G, "t-early")
    assert gone.bot_window["empty"] is True and gone.values["bot_window_start"] == gone.values["bot_window_end"]
    assert "never enters" in gone.bot_window["note"]
    # A read, a rename, or another template's write never rewrites the saved window...
    s.update(R2G, "t-wide", name="Wide one")
    s.create(R2G, name="New")
    assert json.loads(path.read_text(encoding="utf-8"))["setups"][R2G]["templates"][0]["values"]["bot_window_start"] == "07:00"
    # ...saving the template's values keeps what it runs: the clip, at the same revision.
    kept, rules_changed = s.update(R2G, "t-wide", values={})
    assert rules_changed is False and kept.rev == 4 and kept.bot_window["clipped"] is False
    assert json.loads(path.read_text(encoding="utf-8"))["setups"][R2G]["templates"][0]["values"]["bot_window_start"] == "09:30"


# -- a setup without a scanner gets no template --------------------------------------------------
def test_no_scanner_no_template_but_reading_works(store):
    from setup_templates import routes

    app = FastAPI()
    app.include_router(routes.router)
    routes.install(app)
    c = TestClient(app)
    created = c.post("/api/setups/templates/gap_and_go", json={"name": "Mine"})
    assert created.status_code == 409 and created.json()["detail"]["reason"] == "TEMPLATE_NO_SCANNER"
    assert "no scanner yet" in created.json()["detail"]["error"]
    assert c.post("/api/setups/templates/micro_pullback", json={"name": "Mine"}).status_code == 409
    assert c.post("/api/setups/templates/gap_and_go/default/play").json()["detail"]["reason"] == "TEMPLATE_NO_SCANNER"
    gng = next(s for s in c.get("/api/setups/templates").json()["setups"] if s["id"] == "gap_and_go")
    assert gng["scanner"] is False and [t["id"] for t in gng["templates"]] == ["default"]
    assert gng["templates"][0]["bot_window"] is None


def test_the_patch_answer_says_a_bot_only_edit_kept_the_read_out(store, monkeypatch):
    import setup_scanner.readout as readout_mod
    from setup_templates import routes

    monkeypatch.setattr(readout_mod, "current", lambda template=None, **kw: {
        "state": "collecting", "passed": False, "reason": "0 of 50", "go": {"triggered": 0, "avg_net_r": None},
        "rules": {"min_go": 50}, "bot_window": {"start": "07:00", "end": "09:00", "clipped": False, "triggered": 4,
                                                 "triggered_inside": 1, "go_triggered": 0, "go_triggered_inside": 0}})
    app = FastAPI()
    app.include_router(routes.router)
    routes.install(app)
    c = TestClient(app)
    tid = c.post(f"/api/setups/templates/{FP}", json={"name": "Tight"}).json()["template"]["id"]
    body = c.patch(f"/api/setups/templates/{FP}/{tid}", json={"values": {"bot_window_end": "09:00"}}).json()
    assert body["rules_changed"] is False and body["template"]["rev"] == 1
    assert body["template"]["bot_window"]["end"] == "09:00" and body["template"]["readout"]["bot_window"]["triggered_inside"] == 1
    bad = c.patch(f"/api/setups/templates/{FP}/{tid}", json={"values": {"bot_window_end": "12:00"}})
    assert bad.status_code == 400 and bad.json()["detail"]["field"] == "bot_window_end"
