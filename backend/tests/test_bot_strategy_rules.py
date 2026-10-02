"""Each strategy's bot rules (ADR 043): the grades Nova buys and its setups a stock a day.

They are template parameters of the bot group (never a new revision or read-out), read from each
setup's template in play -- the built-in's with the operator's own bot rules over it (``default_bot``)
-- by one rule for Nova's bot and Auto-entry (``admit.blockers``: ``BOT_SKIP_GRADE``,
``BOT_SKIP_NOT_FIRST``) and the squares. Nova buys only the stocks on today's hot list
(``BOT_SKIP_NOT_LISTED``).
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import constants_setups as cs
from bot import strategy_rules
from setup_templates import catalogue
from setup_templates.catalogue import TemplateError
from setup_templates.store import TemplateStore, set_store_for_tests

FP, BF = "first_pullback", "bull_flag"
NOW = 1_790_000_000.0


@pytest.fixture()
def store(tmp_path):
    s = TemplateStore(tmp_path / "setup-templates.json")
    set_store_for_tests(s)
    yield s
    set_store_for_tests(None)


# -- the words ------------------------------------------------------------------------------
def test_ordinals_and_the_rules_in_words():
    assert [strategy_rules.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 21, 22, 103)] == \
        ["1st", "2nd", "3rd", "4th", "11th", "12th", "21st", "22nd", "103rd"]
    assert strategy_rules.grade_block("B", "A") == "grade B: this strategy buys grade A only"
    assert strategy_rules.grade_block("A", "A") is None and strategy_rules.grade_block("B", "AB") is None
    assert strategy_rules.grade_block("C", "A") is None             # NOT A TRADE says C, not this rule
    assert strategy_rules.grade_block(None, "AB") == "the grade is unknown: this strategy buys grade A and B"
    assert strategy_rules.nth_block(2, 1, FP) == "a 2nd first pullback: this strategy buys the 1st of the day only"
    assert strategy_rules.nth_block(3, 2, BF) == "a 3rd bull flag: this strategy buys the 1st and 2nd of the day only"
    assert strategy_rules.nth_block(2, 2, FP) is None


def test_a_setups_number_is_its_nth_else_its_kind():
    assert strategy_rules.number_of({"nth": 3, "kind": "first_pullback"}, FP) == 3
    assert strategy_rules.number_of({"kind": "first_pullback"}, FP) == 1
    assert strategy_rules.number_of({"kind": "second_pullback"}, FP) == 2
    assert strategy_rules.number_of({"kind": "red_to_green"}, "red_to_green") == 1


# -- the catalogue ----------------------------------------------------------------------------
def test_every_setup_with_a_scanner_has_the_two_bot_rules_at_their_defaults():
    for sid in cs.SETUPS_READOUT_KINDS:
        defaults = catalogue.defaults(sid)
        assert defaults["bot_grades"] == "AB" and defaults["bot_setups_a_day"] == 1, sid
        specs = {s.key: s for s in catalogue.specs(sid)}
        assert specs["bot_grades"].group == specs["bot_setups_a_day"].group == catalogue.BOT_GROUP
        assert [v for v, _label in specs["bot_grades"].choices] == ["AB", "A"]
    assert "bot_grades" not in catalogue.defaults("gap_and_go")       # no scanner, no bot rules


@pytest.mark.parametrize("values, field", [
    ({"bot_grades": "C"}, "bot_grades"), ({"bot_grades": "ABC"}, "bot_grades"),
    ({"bot_setups_a_day": 0}, "bot_setups_a_day"), ({"bot_setups_a_day": 3}, "bot_setups_a_day"),
    ({"bot_setups_a_day": 1.5}, "bot_setups_a_day"),
])
def test_the_bot_rules_are_validated_like_every_parameter(values, field):
    with pytest.raises(TemplateError) as err:
        catalogue.validate(FP, values)
    assert err.value.field == field and err.value.code == "TEMPLATE_INVALID"


def test_a_template_edit_of_the_bot_rules_keeps_its_revision(store):
    t = store.create(FP, name="Mine")
    edited, changed = store.update(FP, t.id, values={"bot_grades": "A", "bot_setups_a_day": 2})
    assert changed is False and edited.rev == 1 and edited.fingerprint == t.fingerprint
    store.play(FP, t.id)
    assert strategy_rules.rules(FP)["grades"] == "A" and strategy_rules.rules(FP)["setups_a_day"] == 2


# -- the built-in's bot rules (default_bot) -------------------------------------------------------
def test_the_default_takes_its_bot_rules_and_nothing_else(store, tmp_path):
    before = store.in_play(FP)
    t, changed = store.update(FP, "default", values={"bot_grades": "A", "bot_window_end": "09:30"})
    assert changed is False and t.builtin and t.rev == before.rev and t.fingerprint == before.fingerprint
    assert t.values["bot_grades"] == "A" and t.values["bot_window_end"] == "09:30"
    assert store.in_play(FP).values["bot_grades"] == "A"
    saved = json.loads((tmp_path / "setup-templates.json").read_text(encoding="utf-8"))
    assert saved["schema_version"] == 1
    assert saved["setups"][FP]["default_bot"] == {"bot_window_end": "09:30", "bot_grades": "A"}
    reread = TemplateStore(tmp_path / "setup-templates.json")
    assert reread.in_play(FP).values["bot_grades"] == "A"
    assert reread.in_play(BF).values["bot_grades"] == "AB"             # per setup


def test_the_defaults_scanner_rules_name_and_note_stay_locked(store):
    with pytest.raises(TemplateError) as err:
        store.update(FP, "default", values={"bot_grades": "A", "leg_pct": 6})
    assert err.value.code == "TEMPLATE_BUILTIN" and err.value.field == "leg_pct" and "duplicate" in err.value.message
    assert store.in_play(FP).values["bot_grades"] == "AB"              # nothing was saved
    same = store.in_play(FP).values["leg_pct"]
    t, _changed = store.update(FP, "default", values={"leg_pct": same, "bot_setups_a_day": 2})
    assert t.values["bot_setups_a_day"] == 2                           # a value equal to its own is not a change
    for kw in ({"name": "Mine"}, {"note": "edited"}):
        with pytest.raises(TemplateError) as err:
            store.update(FP, "default", **kw)
        assert err.value.code == "TEMPLATE_BUILTIN"


def test_the_defaults_bot_window_stays_inside_its_arming_window(store):
    with pytest.raises(TemplateError) as err:
        store.update(FP, "default", values={"bot_window_start": "06:00"})
    assert err.value.code == "TEMPLATE_INVALID" and err.value.field == "bot_window_start"


def test_back_to_the_pre_registered_values_stores_nothing(store, tmp_path):
    store.update(FP, "default", values={"bot_grades": "A"})
    store.update(FP, "default", values={"bot_grades": "AB"})
    saved = json.loads((tmp_path / "setup-templates.json").read_text(encoding="utf-8"))
    assert "default_bot" not in saved["setups"][FP]


def test_a_file_without_default_bot_and_a_stale_override_read_safely(tmp_path):
    path = tmp_path / "setup-templates.json"
    path.write_text(json.dumps({"schema_version": 1, "setups": {FP: {"in_play": None, "templates": []}}}),
                    encoding="utf-8")
    assert TemplateStore(path).in_play(FP).values["bot_grades"] == "AB"
    path.write_text(json.dumps({"schema_version": 1, "setups": {FP: {
        "in_play": None, "templates": [],
        "default_bot": {"bot_grades": "Z", "bot_setups_a_day": 2, "leg_pct": 9}}}}), encoding="utf-8")
    values = TemplateStore(path).in_play(FP).values
    assert values["bot_grades"] == "AB" and values["bot_setups_a_day"] == 2    # the bad one dropped, logged
    assert values["leg_pct"] == catalogue.defaults(FP)["leg_pct"]               # never a scanner rule


def test_the_route_patches_the_defaults_bot_rules(store, monkeypatch):
    import setup_scanner.readout as readout_mod
    from setup_templates import routes

    monkeypatch.setattr(readout_mod, "current", lambda template=None, **kw: {
        "state": "collecting", "passed": False, "reason": "0 of 50", "go": {}, "rules": {}})
    app = FastAPI()
    app.include_router(routes.router)
    routes.install(app)
    client = TestClient(app)
    res = client.patch(f"/api/setups/templates/{FP}/default", json={"values": {"bot_setups_a_day": 2}})
    assert res.status_code == 200
    body = res.json()
    assert body["rules_changed"] is False and body["template"]["id"] == "default"
    assert body["template"]["values"]["bot_setups_a_day"] == 2 and body["setup"]["in_play"] == "default"
    locked = client.patch(f"/api/setups/templates/{FP}/default", json={"values": {"leg_pct": 6}})
    assert locked.status_code == 409 and locked.json()["detail"]["reason"] == "TEMPLATE_BUILTIN"


def test_the_bot_window_the_entry_rules_read_is_the_defaults_own(store):
    from bot import entry_rules

    store.update(FP, "default", values={"bot_window_start": "08:00", "bot_window_end": "09:15"})
    w = entry_rules.window(FP)
    assert (w["start"], w["end"]) == ("08:00", "09:15")


def test_an_unreadable_template_store_reads_the_strictest_rules(monkeypatch):
    def broken():
        raise RuntimeError("store gone")

    monkeypatch.setattr("setup_templates.store.get_store", broken)
    rules = strategy_rules.rules(FP)
    assert rules["grades"] == "A" and rules["setups_a_day"] == 1 and rules["error"]


# -- the admission ---------------------------------------------------------------------------------
def _event(**over) -> dict:
    setup = {"kind": "first_pullback", "trigger": 10.01, "entry": 10.02, "stop": 9.89, "risk": 0.14,
             "target1": 10.30, "triggered_at": NOW, "nth": 1}
    setup.update(over.pop("setup", {}))
    event = {"symbol": "IMCC", "setup_id": "IMCC-2026-09-24-1", "setup": setup, "setup_type": FP,
             "tape": {"verdict": "go", "reasons": ["green"]}, "grade": "A",
             "pillars": {"passed": 5, "known": 5, "total": 5}, "filtered": None, "spread": 0.02}
    event.update(over)
    return event


def _codes(event: dict) -> dict[str, str]:
    from bot.first_pullback.admit import blockers
    from bot.persist import load_session

    return dict(blockers(event, load_session(), now=NOW))


def test_the_admission_holds_back_each_rule_with_its_code(store):
    from tests.bot_helpers import ready_l2

    ready_l2(brain=None, symbols=("IMCC",))
    assert _codes(_event()) == {}
    store.update(FP, "default", values={"bot_grades": "A"})
    assert _codes(_event(grade="B"))["BOT_SKIP_GRADE"] == "grade B: this strategy buys grade A only"
    second = _codes(_event(setup={"kind": "second_pullback", "nth": 2}))
    assert second["BOT_NOT_FIRST_OF_DAY"] == "a 2nd first pullback: this strategy buys the 1st of the day only"
    store.update(FP, "default", values={"bot_setups_a_day": 2})
    assert "BOT_NOT_FIRST_OF_DAY" not in _codes(_event(setup={"kind": "second_pullback", "nth": 2}))
    third = _codes(_event(setup={"kind": "second_pullback", "nth": 3}))
    assert third["BOT_NOT_FIRST_OF_DAY"] == "a 3rd first pullback: this strategy buys the 1st and 2nd of the day only"
    assert _codes(_event(symbol="AISP"))["BOT_SKIP_NOT_LISTED"] == "AISP is not on today's hot list"


def test_an_unreadable_hot_list_lists_nothing_and_says_why(monkeypatch):
    from tests.bot_helpers import ready_l2

    ready_l2(brain=None, symbols=("IMCC",))

    def broken(path=None):
        return None, "hot-list.json is unreadable: disk gone"

    monkeypatch.setattr("hot_list.store.read_raw", broken)
    said = _codes(_event())["BOT_SKIP_NOT_LISTED"]
    assert said.startswith("today's hot list could not be read") and "disk gone" not in said

    def raising(symbol, now=None):
        raise OSError("disk gone")

    monkeypatch.setattr("hot_list.listed_or_unread", raising)
    said = _codes(_event())["BOT_SKIP_NOT_LISTED"]
    assert said.startswith("today's hot list could not be read") and "disk gone" not in said
