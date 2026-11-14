"""Bot session persist, the level the file holds, and the bot API's door (ADR 016, ADR 042, ADR 072).

ADR 072 retired the Bot switch, Activate and the session's PATCH: the levels and the sleeve are read as the file
holds them, every strategy reads Eyes, and the brain's claim and every send are refused until the brain is built.
"""
from __future__ import annotations

import pytest

from bot.arming import heartbeat_is_fresh, is_desk_active
from bot.door import assert_can_fire, assert_not_dark
from bot.errors import BotError
from bot.persist import default_session, load_session, save_session
from bot.session import get_session, require_l2_brain
from constants_bot import (
    BOT_BRAIN_DOOR_CLOSED_TEXT,
    BOT_HEARTBEAT_STALE_SEC,
    BOT_LEVEL_EYES,
    BOT_LEVEL_OFF,
    BOT_REASON_ARM_REQUIRED,
    BOT_REASON_BRAIN_EXCLUSIVE,
    BOT_REASON_L0_DARK,
    BOT_REASON_L1_NO_FIRE,
    BOT_REASON_LIVE_NOT_BUILT,
    BOT_REASON_NOT_ACTIVE,
    BOT_SCANNER_SETUPS,
    BOT_SCHEMA_VERSION,
)
from tests.bot_helpers import on_practice, set_level


def test_default_session_is_l0_dark():
    row = default_session()
    assert row["schema_version"] == BOT_SCHEMA_VERSION == 5
    assert row["level"] == BOT_LEVEL_OFF
    assert row["armed"] is False
    view = get_session()
    assert view["level"] == 0 and view["active"] is False
    assert view["brain_session_id"] is None
    assert view["caps"]["risk_usd"] == 20.0 and "entries_per_day" not in view["caps"]
    assert view["caps"]["api_kinds"] == view["caps"]["allowlist"]


def test_the_retired_fields_left_the_answer_and_every_strategy_reads_eyes():
    view = get_session()
    for gone in ("bot_on", "keys", "gates", "ready", "ready_reason", "runner", "trade", "entries_today",
                 "deactivated", "has_desk_arm", "armed", "live_fire_ready"):
        assert gone not in view
    # The short chips went with the Bots page; the day cover's alarms stay (``DayCoverAlarms`` polls them).
    assert set(view["shorts"]) == {"day_cover"}
    assert view["setup_levels"] == {sid: BOT_LEVEL_EYES for sid in BOT_SCANNER_SETUPS}
    scanners = [s for s in view["setups"] if s["scanner"]]
    assert scanners and all(s["level"] == s["effective"] == BOT_LEVEL_EYES for s in scanners)


def test_l0_refuses_fire():
    on_practice()
    with pytest.raises(BotError) as exc:
        assert_not_dark()
    assert exc.value.reason == BOT_REASON_L0_DARK
    with pytest.raises(BotError) as exc:
        assert_can_fire()
    assert exc.value.reason == BOT_REASON_L0_DARK


def test_the_bot_api_never_fires_on_live():
    set_level(2)
    with pytest.raises(BotError) as exc:
        assert_can_fire()
    assert exc.value.reason == BOT_REASON_LIVE_NOT_BUILT


def _seed_session_file(level: int, **fields) -> None:
    """Write a session file straight to disk and drop the in-memory copy."""
    import json

    from bot import persist
    from constants_bot import BOT_SESSION_FILENAME
    from paths import cache_dir

    row = default_session()
    row["level"] = level
    row["armed"] = True
    row.update(fields)
    (cache_dir() / BOT_SESSION_FILENAME).write_text(json.dumps(row), encoding="utf-8")
    persist._session = None


@pytest.mark.parametrize("level", [3, 4, 99])
def test_persisted_parked_level_loads_dark(level):
    # The park holds on the read door (#216).
    _seed_session_file(level)
    row = load_session()
    assert row["level"] == BOT_LEVEL_OFF
    assert row["armed"] is False
    with pytest.raises(BotError) as exc:
        assert_not_dark()
    assert exc.value.reason == BOT_REASON_L0_DARK


def test_persisted_l2_still_loads_l2_and_activate_never_survives_a_start():
    # The clamp is surgical: the level survives a reload; Activate and the brain's claim do not (ADR 042, ADR 072).
    _seed_session_file(2, desk_arm_token="tok", brain_session_id="brain-a", claim_arm_token="tok")
    row = load_session()
    assert row["level"] == 2 and row["armed"] is False and is_desk_active(row) is False
    assert row["desk_arm_token"] is None and row["brain_session_id"] is None


def test_l1_eyes_cannot_fire():
    on_practice()
    set_level(1)
    row = assert_not_dark()
    assert row["level"] == 1
    with pytest.raises(BotError) as exc:
        assert_can_fire()
    assert exc.value.reason == BOT_REASON_L1_NO_FIRE


def test_at_strategy_the_door_stays_shut_until_the_brain_is_built():
    on_practice()
    set_level(2)
    with pytest.raises(BotError) as exc:
        assert_can_fire()
    assert exc.value.reason == BOT_REASON_NOT_ACTIVE and exc.value.message == BOT_BRAIN_DOOR_CLOSED_TEXT


def test_no_brain_can_claim_the_session():
    with pytest.raises(BotError) as exc:
        require_l2_brain("brain-a", claim=True)
    assert exc.value.reason == BOT_REASON_BRAIN_EXCLUSIVE           # below Strategy
    set_level(2)
    with pytest.raises(BotError) as exc:
        require_l2_brain("brain-a", claim=True)
    assert exc.value.reason == BOT_REASON_ARM_REQUIRED and exc.value.message == BOT_BRAIN_DOOR_CLOSED_TEXT
    assert get_session()["brain_session_id"] is None


def test_the_sleeve_bounds_and_its_rules():
    from bot import sleeve
    from constants_bot import BOT_REASON_CAPS_INVALID

    view = get_session()
    assert view["caps_bounds"] == {"risk_usd": [1.0, 10000.0], "max_shares": [1, 10], "bp_budget_usd": [0.01, 50.0],
                                   "working_ttl_sec": [1, 10]}
    after, changed = sleeve.apply(view["caps"], {"max_shares": 10, "risk_usd": 35})
    assert after["max_shares"] == 10 and after["risk_usd"] == 35.0 and set(changed) == {"max_shares", "risk_usd"}
    for bad in ({"max_shares": 99}, {"bp_budget_usd": 500}, {"working_ttl_sec": 0},
                {"risk_usd": 0}, {"api_kinds": ["buy_everything"]}, {"no_such": 1}):
        with pytest.raises(BotError) as refused:
            sleeve.apply(view["caps"], bad)
        assert refused.value.reason == BOT_REASON_CAPS_INVALID and refused.value.status_code == 400


def test_a_stored_sleeve_with_the_retired_daily_cap_loads_and_drops_it():
    """No daily cap (operator, 2026-10-27): a sleeve written before it loads without ``entries_per_day``."""
    from bot import sleeve

    old = {**sleeve.defaults(), "risk_usd": 30, "entries_per_day": 3}
    assert "entries_per_day" not in sleeve.normalize(old) and sleeve.normalize(old)["risk_usd"] == 30.0
    after, changed = sleeve.apply(old, {"entries_per_day": 1})
    assert "entries_per_day" not in after and changed == {}
    assert "entries_per_day" not in sleeve.bounds()


def test_each_venue_keeps_its_own_sleeve():
    from bot.venue_levels import put
    from sim.mode import set_venue

    on_practice()
    row = load_session()
    row["caps"] = {**row["caps"], "max_shares": 5}                    # the desk's: Paper
    put(row, "sim", "caps", {**row["caps"], "max_shares": 7})
    save_session(row)
    view = get_session()
    assert view["caps"]["venue"] == "paper" and view["caps"]["max_shares"] == 5
    assert view["caps_by_venue"]["sim"]["max_shares"] == 7 and view["caps_by_venue"]["live"]["max_shares"] == 1
    set_venue("sim", persist=False)
    assert get_session()["caps"]["max_shares"] == 7
    set_venue("paper", persist=False)
    assert get_session()["caps"]["max_shares"] == 5


def test_a_heartbeat_is_fresh_only_inside_its_window():
    assert heartbeat_is_fresh({"brain_heartbeat_ts": 1000.0}, now=1000.0 + BOT_HEARTBEAT_STALE_SEC) is True
    assert heartbeat_is_fresh({"brain_heartbeat_ts": 1000.0}, now=1001.0 + BOT_HEARTBEAT_STALE_SEC) is False
    assert heartbeat_is_fresh({}, now=1000.0) is False


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
