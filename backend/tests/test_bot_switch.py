"""The Bot switch (ADR 043): one control per venue in place of the master dial and Activate.

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
    BOT_REASON_TRIP_LATCHED,
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


def _latch() -> None:
    from bot.clock import lock_until_date

    row = load_session()
    row.update(soft_breaker_fired=True, soft_breaker_until=lock_until_date(), soft_breaker_at=1_790_000_000.0,
               soft_breaker_pnl=-55.0)
    save_session(row)


# -- ON ----------------------------------------------------------------------------------
def test_on_puts_the_master_at_strategy_and_activates_in_one_step(api_key):
    on_practice()
    _a_strategy_on()                                 # the master is still Off
    res = _switch(api_key, True)
    assert res.status_code == 200
    body = res.json()
    assert body["level"] == 2 and body["active"] is True and body["bot_on"] is True
    assert body["switch"] == {"on": True, "venue": "paper", "why_off": None, "latched": None}
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


def test_on_with_the_padlock_locked_is_refused_in_the_switchs_words(api_key, monkeypatch):
    on_practice()
    _a_strategy_on()
    monkeypatch.setattr("ibkr.trading_allowed.places_allowed", lambda: (False, "desk disarmed"))
    res = _switch(api_key, True)
    assert res.status_code == 409 and res.json()["detail"]["reason"] == BOT_REASON_PADLOCK_LOCKED
    assert "unlock it, then turn the bot on" in res.json()["detail"]["error"]


def test_a_bot_trip_needs_reenable_which_clears_the_latch(api_key):
    on_practice()
    _a_strategy_on()
    _latch()
    view = get_session()
    assert view["switch"]["latched"] == {"at": 1_790_000_000.0, "pnl": -55.0,
                                         "until": load_session()["soft_breaker_until"]}
    assert "Turn the bot on with re-enable" in view["switch"]["why_off"]
    refused = _switch(api_key, True)
    assert refused.status_code == 409 and refused.json()["detail"]["reason"] == BOT_REASON_TRIP_LATCHED
    assert "(P&L -$55.00)" in refused.json()["detail"]["error"]
    ok = _switch(api_key, True, reenable=True)
    assert ok.status_code == 200 and ok.json()["bot_on"] is True
    assert ok.json()["switch"]["latched"] is None and ok.json()["soft_breaker"]["fired"] is False
    [line] = _lines()
    assert "re-enabled" in line["reason"]


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


# -- the trip and the old controls -----------------------------------------------------------
@pytest.mark.asyncio
async def test_a_bot_trip_leaves_the_switch_off_at_eyes_and_latched(api_key, monkeypatch):
    from bot.breakers import trip_soft

    async def flat(*, origin=None):
        return {"ok": True, "attempt": 1}

    monkeypatch.setattr("bot.breakers.flatten_account_with_retry", flat)
    on_practice()
    _a_strategy_on()
    _switch(api_key, True)
    await trip_soft(pnl=-61.5)
    view = get_session()
    assert view["level"] == 1 and view["bot_on"] is False
    assert view["switch"]["latched"]["pnl"] == -61.5
    assert view["setups"][0]["effective"] == 1          # Eyes keep proposing


def test_patch_level_and_activate_still_work_for_the_localhost_api(api_key):
    on_practice()
    patched = client.patch("/api/bot/session", json={"level": 2, "setup_levels": {"first_pullback": 2}},
                           headers=headers(api_key))
    assert patched.status_code == 200 and patched.json()["level"] == 2 and patched.json()["bot_on"] is False
    armed = client.post("/api/bot/session/arm", json={}, headers=headers(api_key))
    assert armed.status_code == 200 and armed.json()["bot_on"] is True and armed.json()["switch"]["on"] is True
