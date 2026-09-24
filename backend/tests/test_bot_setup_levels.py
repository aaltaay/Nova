"""A level per setup; the bot plays the chosen setup (ADR 031, operator decisions A and B)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bot.arming import issue_arm_token, is_desk_active
from bot.audit import list_entries
from bot.autonomy import apply_patch
from bot.errors import BotError
from bot.gates import readout
from bot.persist import load_session, save_session
from bot.session import get_session
from bot.setup_levels import levels_of
from constants_bot import BOT_REASON_SETUP_LEVEL, BOT_REASON_SETUP_NO_SCANNER
from main import app
from tests.bot_helpers import headers

client = TestClient(app)


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("NOVA_API_KEY", "bot-test-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    return "bot-test-key"


def test_every_setup_with_a_scanner_starts_off_and_the_chosen_one_carries_the_bot_level():
    row = load_session()
    assert levels_of(row) == {"chosen": "first_pullback", "levels": {
        "first_pullback": 0, "bull_flag": 0, "flat_top_breakout": 0, "red_to_green": 0}}
    apply_patch({"level": 1}, desk=True)
    assert levels_of(load_session())["levels"]["first_pullback"] == 1


def test_another_setup_goes_to_eyes_and_back_off():
    apply_patch({"setup_levels": {"bull_flag": 1, "red_to_green": 1}}, desk=True)
    view = get_session()
    assert view["setup_levels"] == {"bull_flag": 1, "flat_top_breakout": 0, "red_to_green": 1}
    assert {s["id"]: s["level"] for s in view["setups"]}["bull_flag"] == 1
    apply_patch({"setup_levels": {"bull_flag": 0}}, desk=True)
    assert get_session()["setup_levels"]["bull_flag"] == 0


@pytest.mark.parametrize("patch, words", [
    ({"first_pullback": 1}, "chosen setup"),
    ({"bull_flag": 2}, "only the chosen setup can be at Strategy"),
    ({"gap_and_go": 1}, "no scanner"),
    ({"micro_pullback": 1}, "no scanner"),
    ({"bull_flag": "eyes"}, "0 (Off) or 1 (Eyes)"),
])
def test_a_level_nothing_can_hold_is_refused_by_name(patch, words):
    with pytest.raises(BotError) as refused:
        apply_patch({"setup_levels": patch}, desk=True)
    assert refused.value.reason == BOT_REASON_SETUP_LEVEL and words in refused.value.message


def test_choosing_another_setup_moves_the_level_and_stops_an_active_bot():
    token = issue_arm_token()
    apply_patch({"level": 2}, desk=True, arm_token=token)
    assert is_desk_active(load_session())
    apply_patch({"setup": "flat_top_breakout"}, desk=True)
    row = load_session()
    assert row["setup"] == "flat_top_breakout" and not is_desk_active(row)
    assert levels_of(row)["levels"] == {"first_pullback": 1, "bull_flag": 0, "flat_top_breakout": 2,
                                        "red_to_green": 0}
    [line] = [r for r in list_entries(limit=20) if r["action"] == "setup"]
    assert line["outcome"] == "first_pullback->flat_top_breakout" and "Activate again" in line["reason"]


def test_a_setup_without_a_scanner_cannot_be_chosen():
    with pytest.raises(BotError) as refused:
        apply_patch({"setup": "gap_and_go"}, desk=True)
    assert refused.value.reason == BOT_REASON_SETUP_NO_SCANNER


def test_the_readout_gate_reads_the_chosen_setups_own(monkeypatch):
    seen: list[str | None] = []

    def fake_current(**kw):
        seen.append(kw.get("setup"))
        return {"state": "collecting", "passed": False, "reason": "0 of 50", "go": {}, "control": {}, "rules": {}}

    from bot.gates import set_readout_for_tests

    set_readout_for_tests(None)                      # the conftest pins a passed read-out
    monkeypatch.setattr("setup_scanner.readout.current", fake_current)
    row = load_session()
    row["setup"] = "red_to_green"
    save_session(row)
    readout()
    assert seen == ["red_to_green"]


def test_the_session_route_takes_setup_levels(api_key):
    res = client.patch("/api/bot/session", json={"setup_levels": {"flat_top_breakout": 1}},
                       headers=headers(api_key))
    assert res.status_code == 200 and res.json()["setup_levels"]["flat_top_breakout"] == 1
    bad = client.patch("/api/bot/session", json={"setup_levels": {"first_pullback": 1}}, headers=headers(api_key))
    assert bad.status_code == 400 and bad.json()["detail"]["reason"] == BOT_REASON_SETUP_LEVEL


def test_the_engine_proposes_only_for_a_setup_at_eyes():
    from setup_scanner.engine import SetupEngine

    eng = SetupEngine(levels=lambda: {"chosen": "first_pullback",
                                      "levels": {"first_pullback": 0, "bull_flag": 1}},
                      replay_desk=lambda: False)
    assert eng.can_propose("bull_flag") is True
    assert eng.can_propose("first_pullback") is False            # Off: watches and scores in silence
    assert eng.can_propose("red_to_green") is False              # no level said: Off
    replay = SetupEngine(levels=lambda: {"chosen": None, "levels": {"bull_flag": 1}}, replay_desk=lambda: True)
    assert replay.can_propose("bull_flag") is False              # a replay desk proposes nothing live


def test_an_unreadable_level_proposes_nothing():
    from setup_scanner.engine import SetupEngine

    def broken():
        raise RuntimeError("session unreadable")

    eng = SetupEngine(levels=broken, replay_desk=lambda: False)
    assert eng.can_propose("first_pullback") is False


def test_a_setup_level_change_is_on_the_audit():
    apply_patch({"setup_levels": {"bull_flag": 1}}, desk=True)
    [line] = [r for r in list_entries(limit=20) if r["action"] == "setup_level"]
    assert line["outcome"] == "bull_flag:0->1" and line["inputs"] == {"setup": "bull_flag", "from": 0, "to": 1}
    apply_patch({"setup_levels": {"bull_flag": 1}}, desk=True)        # no change, no line
    assert len([r for r in list_entries(limit=20) if r["action"] == "setup_level"]) == 1
