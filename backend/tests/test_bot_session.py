"""Bot session persist, autonomy ladder, exclusive L2 brain (ADR 016, ADR 042)."""
from __future__ import annotations

import pytest

from bot.autonomy import apply_desk_level, apply_patch, assert_can_fire, assert_not_dark
from bot.errors import BotError
from bot.persist import default_session, load_session
from bot.session import get_session, require_l2_brain
from constants_bot import (
    BOT_LEVEL_OFF,
    BOT_MAX_SHARES_CAP,
    BOT_REASON_BRAIN_EXCLUSIVE,
    BOT_REASON_CAPS_INVALID,
    BOT_REASON_L0_DARK,
    BOT_REASON_L1_NO_FIRE,
    BOT_REASON_L3_PARKED,
    BOT_REASON_NOT_ACTIVE,
    BOT_REASON_TRADING_LOCKED,
    BOT_SCHEMA_VERSION,
)
from tests.bot_helpers import on_practice, ready_l2


def test_default_session_is_l0_dark():
    row = default_session()
    assert row["schema_version"] == BOT_SCHEMA_VERSION == 5
    assert row["level"] == BOT_LEVEL_OFF
    assert row["armed"] is False
    view = get_session()
    assert view["level"] == 0 and view["active"] is False and view["deactivated"] is None
    assert view["brain_session_id"] is None
    assert view["caps"]["risk_usd"] == 20.0 and view["caps"]["entries_per_day"] == 1
    assert view["caps"]["api_kinds"] == view["caps"]["allowlist"]


def test_l0_refuses_fire_and_focus_writes():
    on_practice()
    with pytest.raises(BotError) as exc:
        assert_not_dark()
    assert exc.value.reason == BOT_REASON_L0_DARK
    with pytest.raises(BotError) as exc:
        assert_can_fire()
    assert exc.value.reason == BOT_REASON_L0_DARK


def test_l3_is_parked():
    with pytest.raises(BotError) as exc:
        apply_patch({"level": 3}, desk=True)
    assert exc.value.reason == BOT_REASON_L3_PARKED
    assert load_session()["level"] == BOT_LEVEL_OFF


def test_l3_is_parked_through_the_desk_shortcut():
    # apply_desk_level is the internal/test shortcut -- it must not bypass the park.
    with pytest.raises(BotError) as exc:
        apply_desk_level(3)
    assert exc.value.reason == BOT_REASON_L3_PARKED
    assert load_session()["level"] == BOT_LEVEL_OFF


def _seed_session_file(level: int) -> None:
    """Write a session file straight to disk and drop the in-memory copy."""
    import json

    from bot import persist
    from constants_bot import BOT_SESSION_FILENAME
    from paths import cache_dir

    row = default_session()
    row["level"] = level
    row["armed"] = True
    (cache_dir() / BOT_SESSION_FILENAME).write_text(json.dumps(row), encoding="utf-8")
    persist._session = None


@pytest.mark.parametrize("level", [3, 4, 99])
def test_persisted_parked_level_loads_dark(level):
    # The park must hold on the read door too, not only on apply_patch (#216).
    _seed_session_file(level)
    row = load_session()
    assert row["level"] == BOT_LEVEL_OFF
    assert row["armed"] is False
    with pytest.raises(BotError) as exc:
        assert_not_dark()
    assert exc.value.reason == BOT_REASON_L0_DARK


def test_persisted_l2_still_loads_l2():
    # The clamp is surgical: proven levels survive a reload untouched (Activate does not: ADR 042).
    _seed_session_file(2)
    row = load_session()
    assert row["level"] == 2 and row["armed"] is False


def test_l1_eyes_cannot_fire():
    on_practice()
    apply_patch({"level": 1}, desk=True)
    row = assert_not_dark()
    assert row["level"] == 1
    with pytest.raises(BotError) as exc:
        assert_can_fire()
    assert exc.value.reason == BOT_REASON_L1_NO_FIRE


def test_strategy_needs_no_activate_token_and_never_activates():
    apply_patch({"level": 2}, desk=True)
    view = get_session()
    assert view["level"] == 2 and view["active"] is False


def test_the_sleeve_takes_values_inside_its_bounds_and_refuses_the_rest():
    view = get_session()
    assert view["caps_bounds"] == {"risk_usd": [1.0, 10000.0], "max_shares": [1, 10], "bp_budget_usd": [0.01, 50.0],
                                   "working_ttl_sec": [1, 10], "entries_per_day": [1, 3]}
    apply_patch({"caps": {"max_shares": BOT_MAX_SHARES_CAP, "bp_budget_usd": 50, "working_ttl_sec": 10,
                          "extended_hours": True, "risk_usd": 35, "entries_per_day": 2}}, desk=True)
    caps = get_session()["caps"]
    assert caps["max_shares"] == BOT_MAX_SHARES_CAP and caps["bp_budget_usd"] == 50.0
    assert caps["working_ttl_sec"] == 10 and caps["extended_hours"] is True
    assert caps["risk_usd"] == 35.0 and caps["entries_per_day"] == 2
    for bad in ({"max_shares": 99}, {"bp_budget_usd": 500}, {"working_ttl_sec": 0}, {"entries_per_day": 4},
                {"risk_usd": 0}, {"api_kinds": ["buy_everything"]}, {"no_such": 1}):
        with pytest.raises(BotError) as refused:
            apply_patch({"caps": bad}, desk=True)
        assert refused.value.reason == BOT_REASON_CAPS_INVALID and refused.value.status_code == 400
    assert get_session()["caps"]["max_shares"] == BOT_MAX_SHARES_CAP     # nothing changed in silence


def test_each_venue_keeps_its_own_sleeve():
    on_practice()
    apply_patch({"caps": {"max_shares": 5}}, desk=True)                      # the desk's: Paper
    apply_patch({"caps": {"venue": "sim", "max_shares": 7}}, desk=True)
    view = get_session()
    assert view["caps"]["venue"] == "paper" and view["caps"]["max_shares"] == 5
    assert view["caps_by_venue"]["sim"]["max_shares"] == 7 and view["caps_by_venue"]["live"]["max_shares"] == 1
    from sim.mode import set_venue

    set_venue("sim", persist=False)
    assert get_session()["caps"]["max_shares"] == 7
    set_venue("paper", persist=False)
    assert get_session()["caps"]["max_shares"] == 5


def test_exclusive_l2_brain():
    apply_desk_level(2)
    with pytest.raises(BotError) as exc:
        require_l2_brain(None, claim=True)
    assert exc.value.reason == BOT_REASON_BRAIN_EXCLUSIVE
    assert require_l2_brain("brain-a", claim=True) == "brain-a"
    assert get_session()["brain_session_id"] == "brain-a"
    with pytest.raises(BotError) as exc:
        require_l2_brain("brain-b", claim=True)
    assert exc.value.reason == BOT_REASON_BRAIN_EXCLUSIVE
    assert require_l2_brain("brain-a", claim=True) == "brain-a"


def test_drop_to_l0_clears_brain():
    apply_desk_level(2)
    require_l2_brain("brain-a", claim=True)
    apply_patch({"level": 0}, desk=True)
    view = get_session()
    assert view["level"] == 0
    assert view["brain_session_id"] is None
    assert view["active"] is False and view["armed"] is False
    assert view["has_desk_arm"] is False
    assert view["ready"] is False and view["live_fire_ready"] is False
    assert view["deactivated"]["reason"] == "level"


def test_l2_to_eyes_deactivates():
    ready_l2(brain="brain-a", heartbeat=True)
    assert get_session()["ready"] is True
    apply_patch({"level": 1}, desk=True)
    view = get_session()
    assert view["level"] == 1
    assert view["active"] is False and view["has_desk_arm"] is False
    assert view["brain_session_id"] is None
    assert view["ready"] is False
    with pytest.raises(BotError) as exc:
        assert_can_fire()
    assert exc.value.reason == BOT_REASON_L1_NO_FIRE


def test_l2_not_active_assert_can_fire():
    from bot.arming import disarm_session

    ready_l2(brain="brain-a", heartbeat=True)
    disarm_session()
    view = get_session()
    assert view["level"] == 2
    assert view["active"] is False and view["has_desk_arm"] is False
    assert view["ready"] is False and view["ready_reason"].startswith("the bot is not active")
    with pytest.raises(BotError) as exc:
        assert_can_fire()
    assert exc.value.reason == BOT_REASON_NOT_ACTIVE


def test_a_token_issued_outside_the_rules_is_cleared_by_the_next_level_below_strategy():
    from bot.arming import issue_arm_token

    issue_arm_token()                                   # a legacy session: Active at Off
    apply_patch({"level": 1}, desk=True)
    view = get_session()
    assert view["level"] == 1 and view["active"] is False and view["deactivated"]["reason"] == "level"


def test_places_blocked_clears_ready_and_assert_can_fire(monkeypatch):
    from ibkr import trading_allowed as ta

    ready_l2(brain="brain-a", heartbeat=True)
    assert get_session()["ready"] is True
    monkeypatch.setattr(ta, "places_allowed", lambda: (False, "orders locked"))
    view = get_session()
    assert view["trading_allowed"] is False
    assert view["trading_allowed_reason"] == "orders locked"
    assert view["active"] is True
    assert view["ready"] is False and "padlock" in view["ready_reason"]
    with pytest.raises(BotError) as exc:
        assert_can_fire()
    assert exc.value.reason == BOT_REASON_TRADING_LOCKED


def test_persist_reset_survives_windows_os_name(monkeypatch):
    """Gateway tests set os.name = nt. Teardown must not build WindowsPath."""
    import os

    from bot.persist import reset_for_tests
    from paths import cache_dir

    monkeypatch.setattr(os, "name", "nt")
    reset_for_tests()
    path = cache_dir()
    assert path.exists()
    reset_for_tests()
