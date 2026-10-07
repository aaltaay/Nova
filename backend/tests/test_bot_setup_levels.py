"""A master ceiling and a level per setup; the chosen setup is retired (ADR 031, ADR 042 A)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bot.arming import issue_arm_token, is_desk_active
from bot.audit import list_entries
from bot.autonomy import apply_patch
from bot.errors import BotError
from bot.persist import load_session
from bot.session import get_session
from bot.setup_levels import at_strategy, effective, levels_of
from constants_bot import BOT_REASON_SETUP_LEVEL, BOT_REASON_SETUP_RETIRED
from main import app
from tests.bot_helpers import headers, on_practice

client = TestClient(app)
SHORTS_OFF = {"backside_lower_high": 0, "bear_flag": 0, "failed_breakout": 0, "lost_vwap": 0, "ssr_bounce": 0}


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("NOVA_API_KEY", "bot-test-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    return "bot-test-key"


def test_every_setup_starts_off_and_its_effective_level_is_under_the_master():
    row = load_session()
    assert levels_of(row) == {"chosen": None, "master": 0,
                              "levels": {"first_pullback": 0, "bull_flag": 0, "flat_top_breakout": 0,
                                         "flat_top_5m": 0, "red_to_green": 0, "gap_and_go": 0, **SHORTS_OFF},
                              "own": {"first_pullback": 0, "bull_flag": 0, "flat_top_breakout": 0,
                                      "flat_top_5m": 0, "red_to_green": 0, "gap_and_go": 0, **SHORTS_OFF}}
    apply_patch({"setup_levels": {"bull_flag": 2, "red_to_green": 1}}, desk=True)
    assert effective(load_session())["bull_flag"] == 0             # the master is Off: a ceiling
    apply_patch({"level": 1}, desk=True)
    assert effective(load_session()) == {"first_pullback": 0, "bull_flag": 1, "flat_top_breakout": 0,
                                         "flat_top_5m": 0, "red_to_green": 1, "gap_and_go": 0, **SHORTS_OFF}
    apply_patch({"level": 2}, desk=True)
    assert effective(load_session())["bull_flag"] == 2 and at_strategy(load_session()) == ["bull_flag"]


def test_the_wire_lists_own_and_effective_levels():
    apply_patch({"level": 1, "setup_levels": {"bull_flag": 2}}, desk=True)
    view = get_session()
    setups = {s["id"]: s for s in view["setups"]}
    assert setups["bull_flag"]["level"] == 2 and setups["bull_flag"]["effective"] == 1
    assert setups["micro_pullback"]["scanner"] is False and setups["micro_pullback"]["level"] is None
    assert setups["gap_and_go"]["scanner"] is True and setups["gap_and_go"]["level"] == 0   # Off until set
    assert setups["flat_top_5m"]["scanner"] is True and setups["flat_top_5m"]["level"] == 0  # a new strategy: Off
    assert view["setup_levels"] == {"first_pullback": 0, "bull_flag": 2, "flat_top_breakout": 0, "flat_top_5m": 0,
                                    "red_to_green": 0, "gap_and_go": 0, **SHORTS_OFF}
    assert "setup" not in view and "strategy" not in view and "readout" not in view and "advise" not in view


@pytest.mark.parametrize("patch, words", [
    ({"micro_pullback": 1}, "no scanner"),
    ({"micro_pullback": 2}, "no scanner"),
    ({"bull_flag": "eyes"}, "0 (Off), 1 (Eyes) or 2 (Strategy)"),
    ({"bull_flag": 3}, "0 (Off), 1 (Eyes) or 2 (Strategy)"),
])
def test_a_level_nothing_can_hold_is_refused_by_name(patch, words):
    with pytest.raises(BotError) as refused:
        apply_patch({"setup_levels": patch}, desk=True)
    assert refused.value.reason == BOT_REASON_SETUP_LEVEL and words in refused.value.message
    assert effective(load_session())["bull_flag"] == 0            # nothing changed


def test_any_setup_may_be_at_strategy_at_once():
    apply_patch({"level": 2, "setup_levels": {"first_pullback": 2, "bull_flag": 2, "red_to_green": 2}}, desk=True)
    assert at_strategy(load_session()) == ["first_pullback", "bull_flag", "red_to_green"]


def test_the_chosen_setup_is_retired(api_key):
    with pytest.raises(BotError) as refused:
        apply_patch({"setup": "bull_flag"}, desk=True)
    assert refused.value.reason == BOT_REASON_SETUP_RETIRED and "set each setup's own level" in refused.value.message
    res = client.patch("/api/bot/session", json={"setup": "first_pullback"}, headers=headers(api_key))
    assert res.status_code == 400 and res.json()["detail"]["reason"] == BOT_REASON_SETUP_RETIRED


def test_raising_the_master_needs_no_activate_token_and_never_activates():
    on_practice()
    apply_patch({"level": 2, "setup_levels": {"first_pullback": 2}}, desk=True)
    row = load_session()
    assert row["level"] == 2 and not is_desk_active(row)


def test_lowering_the_master_below_strategy_deactivates_with_the_reason():
    on_practice()
    apply_patch({"level": 2, "setup_levels": {"first_pullback": 2}}, desk=True)
    issue_arm_token()
    apply_patch({"level": 1}, desk=True)
    row = load_session()
    assert not is_desk_active(row)
    assert row["deactivated"]["reason"] == "level" and "Strategy" in row["deactivated"]["text"]
    [line] = [r for r in list_entries(limit=20) if r["action"] == "deactivate"]
    assert line["inputs"]["reason"] == "level"


def test_leaving_no_setup_at_strategy_deactivates_with_the_reason():
    on_practice()
    apply_patch({"level": 2, "setup_levels": {"first_pullback": 2, "bull_flag": 2}}, desk=True)
    issue_arm_token()
    apply_patch({"setup_levels": {"first_pullback": 1}}, desk=True)
    assert is_desk_active(load_session())                      # the bull flag still plays
    apply_patch({"setup_levels": {"bull_flag": 0}}, desk=True)
    row = load_session()
    assert not is_desk_active(row) and row["deactivated"]["reason"] == "no_setup"


def test_the_session_route_takes_every_level(api_key):
    res = client.patch("/api/bot/session", json={"setup_levels": {"flat_top_breakout": 2}},
                       headers=headers(api_key))
    assert res.status_code == 200 and res.json()["setup_levels"]["flat_top_breakout"] == 2
    bad = client.patch("/api/bot/session", json={"setup_levels": {"micro_pullback": 1}}, headers=headers(api_key))
    assert bad.status_code == 400 and bad.json()["detail"]["reason"] == BOT_REASON_SETUP_LEVEL


def test_the_engine_proposes_for_a_setup_at_eyes_or_strategy():
    from setup_scanner.engine import SetupEngine

    eng = SetupEngine(levels=lambda: {"chosen": None,
                                      "levels": {"first_pullback": 0, "bull_flag": 1, "red_to_green": 2}},
                      replay_desk=lambda: False)
    assert eng.can_propose("bull_flag") is True
    assert eng.can_propose("red_to_green") is True             # Strategy proposes too (the proposal says who takes it)
    assert eng.can_propose("first_pullback") is False          # Off: watches and scores in silence
    assert eng.can_propose("flat_top_breakout") is False       # no level said: Off
    replay = SetupEngine(levels=lambda: {"chosen": None, "levels": {"bull_flag": 1}}, replay_desk=lambda: True)
    assert replay.can_propose("bull_flag") is False            # a replay desk proposes nothing live


def test_an_unreadable_level_proposes_nothing():
    from setup_scanner.engine import SetupEngine

    def broken():
        raise RuntimeError("session unreadable")

    eng = SetupEngine(levels=broken, replay_desk=lambda: False)
    assert eng.can_propose("first_pullback") is False


def test_the_live_hook_feeds_the_engine_effective_levels():
    from setup_scanner.hooks import default_levels, reset_levels_cache

    apply_patch({"level": 1, "setup_levels": {"bull_flag": 2}}, desk=True)
    reset_levels_cache()
    assert default_levels()["levels"]["bull_flag"] == 1        # Strategy under an Eyes master is Eyes
    reset_levels_cache()


def test_a_setup_level_change_is_on_the_audit():
    apply_patch({"setup_levels": {"bull_flag": 2}}, desk=True)
    [line] = [r for r in list_entries(limit=20) if r["action"] == "setup_level"]
    assert line["outcome"] == "bull_flag:0->2" and line["inputs"] == {"setup": "bull_flag", "from": 0, "to": 2}
    assert "Strategy" in line["reason"]
    apply_patch({"setup_levels": {"bull_flag": 2}}, desk=True)        # no change, no line
    assert len([r for r in list_entries(limit=20) if r["action"] == "setup_level"]) == 1
