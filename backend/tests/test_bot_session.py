"""Bot session persist, autonomy ladder, exclusive L2 brain."""
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
    BOT_REASON_ARM_REQUIRED,
    BOT_REASON_L0_DARK,
    BOT_REASON_L1_NO_FIRE,
    BOT_REASON_L3_PARKED,
    BOT_SCHEMA_VERSION,
)


def test_default_session_is_l0_dark():
    row = default_session()
    assert row["schema_version"] == BOT_SCHEMA_VERSION
    assert row["level"] == BOT_LEVEL_OFF
    assert row["armed"] is False
    view = get_session()
    assert view["level"] == 0
    assert view["strategy"] is None
    assert view["brain_session_id"] is None
    assert view["advise"]["enabled"] is False


def test_l0_refuses_fire_and_focus_writes():
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


def test_l1_eyes_cannot_fire():
    apply_patch({"level": 1}, desk=True)
    row = assert_not_dark()
    assert row["level"] == 1
    with pytest.raises(BotError) as exc:
        assert_can_fire()
    assert exc.value.reason == BOT_REASON_L1_NO_FIRE


def test_l2_without_arm_token_is_refused():
    with pytest.raises(BotError) as exc:
        apply_patch({"level": 2}, desk=True)
    assert exc.value.reason == BOT_REASON_ARM_REQUIRED


def test_l2_arms_small_cap_and_clamps_caps():
    apply_desk_level(
        2,
        caps={
            "max_shares": 99,
            "bp_budget_usd": 500,
            "working_ttl_sec": 99,
            "extended_hours": True,
        },
    )
    view = get_session()
    assert view["level"] == 2
    assert view["armed"] is True
    assert view["strategy"] == "small-cap"
    assert view["active_pack"] == "halt-luld"
    assert view["has_desk_arm"] is True
    assert view["caps"]["max_shares"] == BOT_MAX_SHARES_CAP
    assert view["caps"]["bp_budget_usd"] == 50.0
    assert view["caps"]["working_ttl_sec"] == 10
    assert view["caps"]["extended_hours"] is True


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
    assert view["strategy"] is None
    assert view["armed"] is False


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
