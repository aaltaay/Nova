"""On flows up (operator ask 2026-10-16, ``bot.cascade``): a host's key, a strategy turned On or a family key turned
on turns the keys above it on -- the family key, then the header's Bot switch. Off never flows, and the padlock is
never touched (bot.md, "The three keys")."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bot import family_keys
from bot.autonomy import apply_patch
from bot.session import get_session
from main import app
from sim.mode import set_venue
from tests.bot_helpers import headers, on_practice

client = TestClient(app)
HOST = "NEAL"


@pytest.fixture(autouse=True)
def _fresh_hosts():
    from bot.live_trader import settings

    settings.reset_for_tests()                                   # the hosts' file is cached per process
    yield
    settings.reset_for_tests()


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("NOVA_API_KEY", "bot-test-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    return "bot-test-key"


def _host_key(api_key: str, on: bool):
    return client.patch(f"/api/bot/live-traders/{HOST}", json={"key": on}, headers=headers(api_key))


def _family_key(api_key: str, family: str, on: bool):
    return client.post("/api/bot/session/keys", json={"family": family, "on": on}, headers=headers(api_key))


def test_a_hosts_key_on_turns_livetrader_bots_and_the_bot_switch_on(api_key):
    from ibkr import safety

    on_practice()
    safety.arm(False, actor="operator")
    family_keys.turn("live_trader", False)
    assert get_session()["bot_on"] is False
    assert _host_key(api_key, True).status_code == 200
    assert family_keys.is_on("live_trader")
    assert get_session()["bot_on"] is True
    assert not safety.armed()                                   # the padlock is never part of it


def test_a_strategy_turned_on_turns_strategy_bots_and_the_bot_switch_on(api_key):
    on_practice()
    family_keys.turn("strategy", False)
    res = client.patch("/api/bot/session", json={"setup_levels": {"first_pullback": 2}}, headers=headers(api_key))
    assert res.status_code == 200
    assert res.json()["bot_on"] is True and res.json()["keys"]["strategy"]["on"] is True


def test_a_strategy_at_eyes_cascades_nothing(api_key):
    on_practice()
    family_keys.turn("strategy", False)
    client.patch("/api/bot/session", json={"setup_levels": {"first_pullback": 1}}, headers=headers(api_key))
    assert not family_keys.is_on("strategy") and get_session()["bot_on"] is False


def test_a_family_key_on_turns_the_bot_switch_on(api_key):
    on_practice()
    apply_patch({"setup_levels": {"first_pullback": 2}}, desk=True)   # internal: no cascade
    family_keys.turn("strategy", False)
    assert get_session()["bot_on"] is False
    res = _family_key(api_key, "strategy", True)
    assert res.status_code == 200 and res.json()["bot_on"] is True and res.json()["desk_arm_token"]


def test_a_family_key_on_with_nothing_under_it_leaves_the_switch_off_and_says_why(api_key):
    on_practice()                                                # no strategy On, no host key on
    family_keys.turn("strategy", False)
    res = _family_key(api_key, "strategy", True)
    assert res.status_code == 200 and res.json()["keys"]["strategy"]["on"] is True
    assert res.json()["bot_on"] is False and "no strategy is On" in res.json()["switch"]["why_off"]


def test_off_never_flows_up(api_key):
    on_practice()
    assert _host_key(api_key, True).status_code == 200
    assert get_session()["bot_on"] is True
    assert _host_key(api_key, False).status_code == 200
    assert family_keys.is_on("live_trader") and get_session()["bot_on"] is True
    _family_key(api_key, "live_trader", False)
    assert get_session()["bot_on"] is True


def test_a_parent_that_cannot_follow_leaves_the_press_standing(api_key, monkeypatch):
    on_practice()
    set_venue("live", persist=False)                             # no family keys and no bot on Live
    res = _host_key(api_key, True)
    assert res.status_code == 200
    card = next(h for h in res.json()["hosts"] if h["name"] == HOST) if res.json().get("hosts") else None
    assert card is None or card["settings"]["key"] is True
    assert get_session()["bot_on"] is False
