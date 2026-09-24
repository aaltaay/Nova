"""Setup templates (ADR 029): the parameter catalogue, the operator's templates
on disk, and their routes -- every number a setup runs on, visible and
changeable, with the pre-registered default locked."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import constants_setups as cs
from setup_scanner.pullback import PullbackParams
from setup_scanner.lane_params import gate_params, grade_rules, pullback_params, stock_filter
from setup_scanner.tape_gate import GateParams
from setup_templates import catalogue
from setup_templates.catalogue import TemplateError
from setup_templates.store import TemplateStore, set_store_for_tests

FP = "first_pullback"
REPO = Path(__file__).resolve().parents[2]


# -- the catalogue ------------------------------------------------------------------
def test_every_playbook_setup_has_a_catalogue_and_defaults_validate():
    for sid in catalogue.setup_ids():
        assert catalogue.validate(sid, {}) == catalogue.defaults(sid)
    assert catalogue.specs("micro_pullback") == ()           # never tested: nothing to vary yet
    assert "never been tested" in catalogue.SOURCES["micro_pullback"]


def test_first_pullback_defaults_are_exactly_what_the_scanner_ran():
    """The default template converts to the scanner's own default parameters, field for field."""
    v = catalogue.defaults(FP)
    assert pullback_params(v) == PullbackParams()
    assert gate_params(v) == GateParams()
    g = grade_rules(v)
    assert (g.min_price, g.max_price, g.min_change_pct, g.min_rvol, g.max_float) == (
        cs.SETUPS_PILLAR_MIN_PRICE, cs.SETUPS_PILLAR_MAX_PRICE, cs.SETUPS_PILLAR_MIN_CHANGE_PCT,
        cs.SETUPS_PILLAR_MIN_RVOL, cs.SETUPS_PILLAR_MAX_FLOAT)
    assert stock_filter(v).active is False                    # no filter: every name the scanner follows
    assert (v["bot_window_start"], v["bot_window_end"], v["bot_entries_per_day"]) == ("07:00", "10:00", 1)


def _research_defaults(path: Path, cls: str) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    return {s.target.id: ast.literal_eval(s.value) for s in node.body
            if isinstance(s, ast.AnnAssign) and s.value is not None and isinstance(s.target, ast.Name)}


def test_research_setups_mirror_the_harness_defaults():
    p = _research_defaults(REPO / "research/momentum/backtest_setups.py", "Params")
    ft, r2g = catalogue.defaults("flat_top_breakout"), catalogue.defaults("red_to_green")
    assert ft["ft_impulse_pct"] == p["ft_impulse_pct"] * 100 and ft["ft_band"] == p["ft_band"] * 100
    assert (ft["ft_min_consol"], ft["ft_max_consol"], ft["ft_entry"], ft["ft_hold_bars"]) == (
        p["ft_min_consol"], p["ft_max_consol"], p["ft_entry"], p["ft_hold_bars"])
    assert (r2g["r2g_min_red_bars"], r2g["r2g_cutoff"], r2g["r2g_target_hod"]) == (
        p["r2g_min_red_bars"], p["r2g_cutoff"], p["r2g_target_hod"])
    for key in ("stop_cap", "min_stop", "target_r", "bailout_bars"):
        assert ft[key] == r2g[key] == p[key]
    g = _research_defaults(REPO / "research/orb/backtest_gng.py", "GParams")
    gng = catalogue.defaults("gap_and_go")
    assert (gng["top"], gng["entry_end"], gng["stop_cents"], gng["t1_r"], gng["t2_r"], gng["time_stop"]) == (
        g["top"], g["entry_end"], g["stop_cents"], g["t1_r"], g["t2_r"], g["time_stop"])
    assert gng["stop_pct"] == g["stop_pct"] * 100


@pytest.mark.parametrize("values, field", [
    ({"leg_window": 2.5}, "leg_window"),
    ({"leg_pct": 0}, "leg_pct"),
    ({"session_start": "7:00"}, "session_start"),
    ({"session_start": "12:00"}, "entry_cutoff"),
    ({"min_price": 10, "max_price": 3}, "max_price"),
    ({"wall": 200_000}, "big_seller"),
    ({"macd_fast": 26}, "macd_slow"),
    ({"require_hod": "yes"}, "require_hod"),
    ({"target_mode": "moon"}, "target_mode"),
    ({"bot_entries_per_day": 4}, "bot_entries_per_day"),
    ({"not_a_param": 1}, "not_a_param"),
])
def test_validation_names_the_field(values, field):
    with pytest.raises(TemplateError) as err:
        catalogue.validate(FP, values)
    assert err.value.field == field


def test_nullable_filters_switch_off_with_none_and_fingerprints_are_stable():
    v = catalogue.validate(FP, {"min_price": 3, "max_price": 10, "max_float_m": 10})
    assert (v["min_price"], v["max_price"], v["max_float_m"]) == (3.0, 10.0, 10.0)
    assert catalogue.validate(FP, {"min_price": None}, base=v)["min_price"] is None
    assert catalogue.fingerprint(v) == catalogue.fingerprint(dict(reversed(list(v.items()))))
    assert catalogue.fingerprint(v) != catalogue.fingerprint(catalogue.defaults(FP))


def test_wire_groups_in_order_with_units_and_the_source():
    w = catalogue.wire(FP)
    assert [g["id"] for g in w["groups"]] == ["stock", "setup", "entry", "risk", "tape", "flow", "grade", "bot"]
    assert w["scanner"] is True and "live scanner" in w["source"]
    leg = next(p for g in w["groups"] for p in g["params"] if p["key"] == "leg_pct")
    assert leg["unit"] == "%" and leg["default"] == 5.0 and leg["live"] is True
    assert catalogue.wire("gap_and_go")["scanner"] is False


# -- the store ------------------------------------------------------------------------
@pytest.fixture()
def store(tmp_path):
    s = TemplateStore(tmp_path / "setup-templates.json")
    set_store_for_tests(s)
    yield s
    set_store_for_tests(None)


def test_default_is_in_play_and_locked(store):
    t = store.in_play(FP)
    assert t.builtin and t.id == "default" and t.rev == cs.SETUP_TEMPLATE_DEFAULT_REV
    with pytest.raises(TemplateError) as err:
        store.update(FP, "default", values={"leg_pct": 6})
    assert err.value.code == "TEMPLATE_BUILTIN" and "duplicate" in str(err.value)
    with pytest.raises(TemplateError):
        store.delete(FP, "default")


def test_create_edit_play_delete_round_trip_on_disk(store, tmp_path):
    t = store.create(FP, name="Low float $3-10", values={"min_price": 3, "max_price": 10, "max_float_m": 10})
    assert t.rev == 1 and t.values["max_float_m"] == 10.0 and not t.builtin
    same, changed = store.update(FP, t.id, name="Low float  $3-10 ")      # spaces fold: no change of rules
    assert changed is False and same.rev == 1
    edited, changed = store.update(FP, t.id, values={"leg_pct": 6})
    assert changed is True and edited.rev == 2 and edited.values["leg_pct"] == 6.0
    renamed, changed = store.update(FP, t.id, name="LF")
    assert changed is False and renamed.rev == 2 and renamed.name == "LF"
    store.play(FP, t.id)
    assert store.in_play(FP).id == t.id
    raw = json.loads((tmp_path / "setup-templates.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1 and raw["setups"][FP]["in_play"] == t.id
    fresh = TemplateStore(tmp_path / "setup-templates.json")
    assert fresh.in_play(FP).values == edited.values and fresh.in_play(FP).rev == 2
    store.delete(FP, t.id)
    assert store.in_play(FP).id == "default"


def test_duplicate_from_a_template_and_limits(store):
    a = store.create(FP, name="A", values={"leg_pct": 7})
    b = store.create(FP, name="B", from_id=a.id)
    assert b.values["leg_pct"] == 7.0
    with pytest.raises(TemplateError) as err:
        store.create(FP, name="a")
    assert err.value.code == "TEMPLATE_NAME_TAKEN"
    for i in range(cs.SETUP_TEMPLATES_MAX_PER_SETUP - 3):
        store.create(FP, name=f"T{i}")
    with pytest.raises(TemplateError) as err:
        store.create(FP, name="one too many")
    assert err.value.code == "TEMPLATE_LIMIT"
    with pytest.raises(TemplateError) as err:
        store.create("micro_pullback", name="x")
    assert err.value.code == "TEMPLATE_NO_PARAMS"


def test_unknown_schema_is_refused_loudly_and_never_overwritten(tmp_path):
    path = tmp_path / "setup-templates.json"
    path.write_text(json.dumps({"schema_version": 99, "setups": {}}), encoding="utf-8")
    s = TemplateStore(path)
    assert "schema version 99" in s.error()
    assert [t.id for t in s.templates(FP)] == ["default"]
    with pytest.raises(TemplateError) as err:
        s.create(FP, name="x")
    assert err.value.code == "TEMPLATES_UNREADABLE"
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 99


def test_a_parameter_added_later_takes_its_default_and_a_broken_template_never_plays(tmp_path):
    path = tmp_path / "setup-templates.json"
    values = catalogue.defaults(FP)
    values.pop("target_fixed")
    broken = {**values, "leg_window": 999}
    path.write_text(json.dumps({"schema_version": 1, "setups": {FP: {"in_play": "t-bad", "templates": [
        {"id": "t-old", "name": "Old", "rev": 3, "values": values},
        {"id": "t-bad", "name": "Bad", "rev": 1, "values": broken}]}}}), encoding="utf-8")
    s = TemplateStore(path)
    old = s.get(FP, "t-old")
    assert old.error is None and old.values["target_fixed"] == cs.SETUPS_TARGET_FIXED_DOLLARS and old.rev == 3
    assert s.get(FP, "t-bad").error and s.in_play(FP).id == "default"
    fixed, changed = s.update(FP, "t-bad", values={"leg_window": 10})
    assert changed and fixed.error is None and fixed.rev == 2


# -- the routes ---------------------------------------------------------------------------
@pytest.fixture()
def client(store, monkeypatch):
    import setup_scanner.readout as readout_mod
    from setup_templates import routes

    monkeypatch.setattr(readout_mod, "current", lambda template=None, **kw: {
        "state": "collecting", "passed": False, "reason": "0 of 50", "go": {"triggered": 0, "avg_net_r": None},
        "rules": {"min_go": 50}})
    app = FastAPI()
    app.include_router(routes.router)
    routes.install(app)
    return TestClient(app)


def test_routes_list_create_edit_play_delete(client):
    body = client.get("/api/setups/templates").json()
    assert body["schema_version"] == 1 and body["error"] is None
    fp = next(s for s in body["setups"] if s["id"] == FP)
    assert fp["in_play"] == "default" and fp["templates"][0]["builtin"] is True
    assert fp["templates"][0]["readout"]["state"] == "collecting"
    assert len(fp["catalogue"]["groups"]) == 8
    created = client.post(f"/api/setups/templates/{FP}", json={"name": "Tight", "values": {"stop_cap": 0.15}})
    assert created.status_code == 201
    tid = created.json()["template"]["id"]
    patched = client.patch(f"/api/setups/templates/{FP}/{tid}", json={"values": {"stop_cap": 0.12}}).json()
    assert patched["rules_changed"] is True and patched["template"]["rev"] == 2
    assert client.post(f"/api/setups/templates/{FP}/{tid}/play").json()["setup"]["in_play"] == tid
    assert client.delete(f"/api/setups/templates/{FP}/{tid}").json()["setup"]["in_play"] == "default"


def test_a_saved_template_that_no_longer_validates_says_why_and_never_runs(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps({"schema_version": 1, "setups": {FP: {"in_play": "t-old", "templates": [
        {"id": "t-old", "name": "Old", "rev": 3, "values": {"leg_pct": 500}}]}}}), encoding="utf-8")
    store = TemplateStore(path)
    old = next(t for t in store.templates(FP) if t.id == "t-old")
    assert old.error is not None and "leg_pct" in old.error
    assert old.values["leg_pct"] == 500
    assert store.in_play(FP).id == "default"


def test_an_unreadable_templates_file_is_named_without_its_exception_text(tmp_path):
    path = tmp_path / "t.json"
    path.write_text("{not json", encoding="utf-8")
    store = TemplateStore(path)
    assert store.error() is not None and store.error().startswith("t.json could not be read")
    assert "Expecting" not in store.error()


def test_routes_refuse_with_a_code_and_the_field(client):
    bad = client.post(f"/api/setups/templates/{FP}", json={"name": "X", "values": {"leg_pct": 500}})
    assert bad.status_code == 400
    assert bad.json()["detail"] == {"reason": "TEMPLATE_INVALID", "error": bad.json()["detail"]["error"],
                                    "field": "leg_pct"}
    locked = client.patch(f"/api/setups/templates/{FP}/default", json={"values": {"leg_pct": 6}})
    assert locked.status_code == 409 and locked.json()["detail"]["reason"] == "TEMPLATE_BUILTIN"
    assert client.delete(f"/api/setups/templates/{FP}/t-nope").status_code == 404
    assert client.post("/api/setups/templates/no_such_setup", json={"name": "x"}).status_code == 404


def test_template_writes_need_a_configured_key_like_bot_routes(monkeypatch):
    from auth import MutatingApiKeyMiddleware
    from setup_templates import routes

    monkeypatch.delenv("NOVA_API_KEY", raising=False)
    app = FastAPI()
    app.add_middleware(MutatingApiKeyMiddleware)
    app.include_router(routes.router)
    routes.install(app)
    c = TestClient(app)
    assert c.get("/api/setups/templates").status_code == 200
    refused = c.post(f"/api/setups/templates/{FP}", json={"name": "x"})
    assert refused.status_code == 503
    monkeypatch.setenv("NOVA_API_KEY", "k")
    assert c.post(f"/api/setups/templates/{FP}", json={"name": "x"}).status_code == 401
    ok = c.post(f"/api/setups/templates/{FP}", json={"name": "x"}, headers={"X-Nova-Api-Key": "k"})
    assert ok.status_code == 201


FIXTURE = REPO / "frontend/src/bot/setupTemplatesFixture.json"


def test_the_frontend_fixture_is_the_backends_own_catalogue():
    """The Bots page tests draw from this fixture; it must be what the backend serves.
    Regenerate: NOVA_WRITE_FIXTURES=1 py -3 -m pytest tests/test_setup_templates.py -k fixture"""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if os.environ.get("NOVA_WRITE_FIXTURES") == "1":
        for s in fixture["setups"]:
            s["catalogue"] = catalogue.wire(s["id"])
            s["templates"][0]["values"] = catalogue.defaults(s["id"])
            s["templates"][0]["fingerprint"] = catalogue.fingerprint(catalogue.defaults(s["id"]))
        FIXTURE.write_text(json.dumps(fixture, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    assert [s["id"] for s in fixture["setups"]] == list(catalogue.setup_ids())
    for s in fixture["setups"]:
        assert s["catalogue"] == json.loads(json.dumps(catalogue.wire(s["id"]))), s["id"]
        assert s["templates"][0]["values"] == catalogue.defaults(s["id"]), s["id"]
