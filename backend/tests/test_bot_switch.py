"""The Bot switch (ADR 044): one control per venue in place of the master dial and Activate.

ON is the master at Strategy and Activate in one step, refused with Activate's codes; OFF deactivates
with the master at Eyes, so Eyes keep proposing; a trip leaves it the same way and latches until
04:00 ET. Every change is one ``bot_switch`` audit line, and the session view says why it is off.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bot.audit import list_entries
from bot.autonomy import apply_patch
from bot.persist import load_session, save_session
from bot.session import get_session
from constants_bot import (
    BOT_REASON_ARM_DESK_ONLY,
    BOT_REASON_LIVE_NOT_BUILT,
    BOT_REASON_NO_SETUP_AT_STRATEGY,
    BOT_REASON_PADLOCK_LOCKED,
)
from main import app
from tests.bot_helpers import headers, on_practice

client = TestClient(app)


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("NOVA_API_KEY", "bot-test-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    return "bot-test-key"


def _switch(api_key: str, on: bool, **body):
    return client.post("/api/bot/session/switch", json={"on": on, **body}, headers=headers(api_key))


def _lines() -> list[dict]:
    return [r for r in list_entries(limit=100) if r["action"] == "bot_switch"]


def _a_strategy_on() -> None:
    apply_patch({"setup_levels": {"first_pullback": 2}}, desk=True)


# -- ON ----------------------------------------------------------------------------------
def test_on_puts_the_master_at_strategy_and_activates_in_one_step(api_key):
    on_practice()
    _a_strategy_on()                                 # the master is still Off
    res = _switch(api_key, True)
    assert res.status_code == 200
    body = res.json()
    assert body["level"] == 2 and body["active"] is True and body["bot_on"] is True
    assert body["switch"] == {"on": True, "venue": "paper", "why_off": None}
    assert body["desk_arm_token"]                    # Activate's token, as POST /arm answers it
    [line] = _lines()
    assert line["outcome"] == "on" and line["inputs"] == {"on": True, "from_level": 0, "to_level": 2}
    assert line["venue"] == "paper"


def test_on_twice_changes_nothing_and_writes_nothing(api_key):
    on_practice()
    _a_strategy_on()
    assert _switch(api_key, True).status_code == 200
    again = _switch(api_key, True)
    assert again.status_code == 200 and again.json()["bot_on"] is True
    assert len(_lines()) == 1


@pytest.mark.parametrize("setup, code, words", [
    (None, BOT_REASON_LIVE_NOT_BUILT, "Live trading by a bot is not built"),
    ("paper", BOT_REASON_NO_SETUP_AT_STRATEGY, "no strategy is On"),
])
def test_on_is_refused_with_activates_codes_and_changes_nothing(api_key, setup, code, words):
    if setup:
        on_practice(setup)                           # no strategy is On
    else:
        _a_strategy_on()                             # the suite's default venue is Live
    res = _switch(api_key, True)
    assert res.status_code == 409
    assert res.json()["detail"]["reason"] == code and words in res.json()["detail"]["error"]
    row = load_session()
    assert row["level"] == 0 and not row.get("armed") and _lines() == []


# -- The padlock is separate (operator decision 2026-10-16) --------------------------------
@pytest.mark.parametrize("venue", ["paper", "sim"])
def test_on_leaves_a_locked_padlock_locked(api_key, monkeypatch, venue):
    from ibkr import safety

    monkeypatch.setattr("sim.mode.is_replay_desk", lambda: False)   # Sim at its live edge
    on_practice(venue)
    _a_strategy_on()
    safety.arm(False, actor="operator")
    assert "padlock" not in (get_session()["switch"]["why_off"] or "")   # ON is not locked by it
    res = _switch(api_key, True)
    assert res.status_code == 200 and res.json()["bot_on"] is True
    assert not safety.armed()                           # the padlock is the operator's alone
    [line] = _lines()
    assert "padlock" not in line["reason"]


def test_on_with_the_padlock_already_unlocked_says_nothing_of_it(api_key):
    on_practice()
    _a_strategy_on()
    assert _switch(api_key, True).status_code == 200
    [line] = _lines()
    assert "padlock" not in line["reason"]


def test_a_refused_on_leaves_the_padlock_locked(api_key):
    from ibkr import safety

    on_practice()                                       # no strategy is On
    safety.arm(False, actor="operator")
    res = _switch(api_key, True)
    assert res.status_code == 409 and res.json()["detail"]["reason"] == BOT_REASON_NO_SETUP_AT_STRATEGY
    assert not safety.armed()


def test_on_over_a_locked_padlock_is_refused_and_changes_nothing(api_key, monkeypatch):
    # Operator decision 2026-10-20 (bot.padlock_gate): no bot turns on over a locked padlock; the desk asks to unlock.
    on_practice()
    _a_strategy_on()
    monkeypatch.setattr("ibkr.trading_allowed.places_allowed", lambda: (False, "Desk is disarmed"))
    res = _switch(api_key, True)
    assert res.status_code == 409 and res.json()["detail"]["reason"] == BOT_REASON_PADLOCK_LOCKED
    assert get_session()["bot_on"] is False and _lines() == []
    assert "padlock is locked" in get_session()["switch"]["why_off"]


def test_locking_the_padlock_leaves_the_switch_on_and_holds_every_bot(api_key, monkeypatch):
    from bot import family_keys
    from ibkr import safety

    on_practice()
    _a_strategy_on()
    monkeypatch.setattr("ibkr.trading_allowed.places_allowed",        # the suite pins it True
                        lambda: (safety.armed(), "" if safety.armed() else "Desk is disarmed"))
    safety.arm(True, actor="operator")
    assert _switch(api_key, True).status_code == 200
    assert family_keys.hold("strategy") is None and family_keys.hold("live_trader") is None
    safety.arm(False, actor="operator")
    assert get_session()["bot_on"] is True              # locking it no longer turns the bot off
    for family in ("strategy", "live_trader"):
        code, why = family_keys.hold(family)
        assert code == BOT_REASON_PADLOCK_LOCKED and "padlock is locked" in why
    safety.arm(True, actor="operator")                  # unlocked: the bots trade again at once
    assert family_keys.hold("strategy") is None


def test_a_brain_cannot_turn_the_bot_on(api_key):
    on_practice()
    _a_strategy_on()
    res = client.post("/api/bot/session/switch", json={"on": True},
                      headers=headers(api_key, brain="brain-1"))
    assert res.status_code == 403 and res.json()["detail"]["reason"] == BOT_REASON_ARM_DESK_ONLY


def test_the_switch_needs_the_desk_key(monkeypatch):
    monkeypatch.delenv("NOVA_API_KEY", raising=False)
    assert client.post("/api/bot/session/switch", json={"on": True}).status_code in (401, 503)


# -- OFF ---------------------------------------------------------------------------------
def test_off_deactivates_with_the_master_at_eyes(api_key):
    on_practice()
    _a_strategy_on()
    _switch(api_key, True)
    res = _switch(api_key, False)
    assert res.status_code == 200
    body = res.json()
    assert body["level"] == 1 and body["active"] is False and body["bot_on"] is False
    assert body["deactivated"]["reason"] == "operator"
    assert body["switch"]["why_off"] == "you turned the bot off"
    assert body["setups"][0]["effective"] == 1          # the first pullback still proposes (Eyes)
    off = _lines()[-1]
    assert off["outcome"] == "off" and off["inputs"] == {"on": False, "from_level": 2, "to_level": 1}


def test_off_from_off_raises_the_master_to_eyes_once(api_key):
    on_practice()
    res = _switch(api_key, False)                       # the master was Off
    assert res.json()["level"] == 1 and _lines()[-1]["inputs"]["from_level"] == 0
    _switch(api_key, False)
    assert len(_lines()) == 1                            # already off at Eyes: nothing changes


def test_off_on_live_works_and_on_live_says_why_it_is_off(api_key):
    _a_strategy_on()                                    # Live
    assert _switch(api_key, False).json()["level"] == 1
    assert get_session()["switch"]["why_off"].startswith("Nova's bot trades Paper and Sim only")


# -- the loss limit and the old controls -----------------------------------------------------
def test_the_daily_loss_limit_leaves_the_switch_on_and_patch_breakers_is_refused(api_key):
    """ADR 056: the limit never turns the bot off; the retired breakers are refused out loud."""
    import time

    from loss_limit import state
    from sim.mode import venue

    on_practice()
    _a_strategy_on()
    _switch(api_key, True)
    state.write(venue(), {"tripped_at": time.time(), "tripped_loss": 451.0, "limit_usd": 405})
    view = get_session()
    assert view["bot_on"] is True and "latched" not in view["switch"]
    refused = client.patch("/api/bot/session", json={"breakers": {"soft_usd": -100}}, headers=headers(api_key))
    assert refused.status_code == 400 and refused.json()["detail"]["reason"] == "BOT_BREAKERS_RETIRED"
    assert "Settings > Loss limits" in refused.json()["detail"]["error"]


def test_patch_level_and_activate_still_work_for_the_localhost_api(api_key):
    on_practice()
    _a_strategy_on()                                 # internal: no cascade (bot.cascade is the routes')
    patched = client.patch("/api/bot/session", json={"level": 2}, headers=headers(api_key))
    assert patched.status_code == 200 and patched.json()["level"] == 2 and patched.json()["bot_on"] is False
    armed = client.post("/api/bot/session/arm", json={}, headers=headers(api_key))
    assert armed.status_code == 200 and armed.json()["bot_on"] is True and armed.json()["switch"]["on"] is True
