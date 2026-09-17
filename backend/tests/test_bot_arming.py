"""Desk Activate token + heartbeat fail-closed."""
from __future__ import annotations

import pytest

from bot.arming import (
    assert_desk_activate,
    assert_fresh_heartbeat,
    disarm_session,
    heartbeat_is_fresh,
    issue_arm_token,
    record_heartbeat,
    require_matching_arm_token,
)
from bot.autonomy import apply_desk_level, apply_patch, assert_can_fire
from bot.errors import BotError
from bot.persist import load_session
from bot.session import get_session, require_l2_brain
from constants_bot import (
    BOT_REASON_ARM_DESK_ONLY,
    BOT_REASON_ARM_REQUIRED,
    BOT_REASON_HEARTBEAT_STALE,
)


def test_issue_arm_token_clears_prior_claim():
    apply_desk_level(2)
    require_l2_brain("brain-a", claim=True)
    record_heartbeat("brain-a")
    token = issue_arm_token()
    row = load_session()
    assert row["armed"] is True
    assert row["desk_arm_token"] == token
    assert row["brain_session_id"] is None
    assert row["brain_heartbeat_ts"] is None
    assert get_session()["has_desk_arm"] is True
    assert get_session()["brain_alive"] is False


def test_disarm_drops_claim_and_token():
    apply_desk_level(2)
    require_l2_brain("brain-a", claim=True)
    disarm_session()
    view = get_session()
    assert view["armed"] is False
    assert view["has_desk_arm"] is False
    assert view["brain_session_id"] is None


def test_raise_l2_needs_matching_token():
    row = load_session()
    with pytest.raises(BotError) as exc:
        require_matching_arm_token(row, "nope")
    assert exc.value.reason == BOT_REASON_ARM_REQUIRED
    token = issue_arm_token()
    apply_patch({"level": 2}, desk=True, arm_token=token)
    assert get_session()["level"] == 2


def test_brains_cannot_activate():
    with pytest.raises(BotError) as exc:
        assert_desk_activate("nova-brain")
    assert exc.value.reason == BOT_REASON_ARM_DESK_ONLY
    assert_desk_activate(None)


def test_heartbeat_fail_closed_without_claim():
    apply_desk_level(2)
    with pytest.raises(BotError):
        record_heartbeat("brain-a")
    with pytest.raises(BotError) as exc:
        assert_can_fire()
    assert exc.value.reason == BOT_REASON_HEARTBEAT_STALE


def test_stale_heartbeat_is_not_fresh():
    apply_desk_level(2)
    require_l2_brain("brain-a", claim=True)
    row = load_session()
    row["brain_heartbeat_ts"] = 1.0
    assert heartbeat_is_fresh(row, now=100.0) is False
    with pytest.raises(BotError) as exc:
        assert_fresh_heartbeat(row)
    assert exc.value.reason == BOT_REASON_HEARTBEAT_STALE


def test_rearm_invalidates_old_claim():
    apply_desk_level(2)
    require_l2_brain("brain-a", claim=True)
    issue_arm_token()
    assert require_l2_brain("brain-b", claim=True) == "brain-b"
    with pytest.raises(BotError):
        require_l2_brain("brain-a", claim=True)
