"""No bot turns on while the desk padlock is locked (``bot.padlock_gate``, operator decision 2026-10-20).

Every press that turns a bot on -- the Bot switch, a family key, a strategy set On, a TraderTV host's Bot key,
Activate -- is refused ``BOT_PADLOCK_LOCKED`` over a locked padlock and changes nothing, so the desk can ask "Unlock
the padlock?" instead of showing a bot ON that places nothing. Off is never refused, and on Live (where no bot trades)
it never asks for the padlock at all.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bot import family_keys
from bot.autonomy import apply_patch
from bot.live_trader import settings as lt_settings
from bot.persist import load_session
from bot.session import get_session
from bot.setup_levels import own_levels
from constants_bot import BOT_REASON_PADLOCK_LOCKED
from main import app
from tests.bot_helpers import headers, on_practice

client = TestClient(app)


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("NOVA_API_KEY", "bot-test-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    lt_settings.reset_for_tests()
    yield "bot-test-key"
    lt_settings.reset_for_tests()


@pytest.fixture
def locked(monkeypatch):
    monkeypatch.setattr("ibkr.trading_allowed.places_allowed", lambda: (False, "Desk is disarmed"))


def _refused(res) -> None:
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert detail["reason"] == BOT_REASON_PADLOCK_LOCKED
    assert "unlock it to turn a bot on" in detail["error"]


def test_the_bot_switch_is_refused(api_key, locked):
    on_practice()
    apply_patch({"setup_levels": {"first_pullback": 2}}, desk=True)
    _refused(client.post("/api/bot/session/switch", json={"on": True}, headers=headers(api_key)))
    assert get_session()["bot_on"] is False


def test_activate_is_refused(api_key, locked):
    on_practice()
    apply_patch({"level": 2, "setup_levels": {"first_pullback": 2}}, desk=True)
    _refused(client.post("/api/bot/session/arm", json={}, headers=headers(api_key)))


def test_a_strategy_set_on_is_refused_and_keeps_its_level(api_key, locked):
    on_practice()
    apply_patch({"setup_levels": {"first_pullback": 1}}, desk=True)
    res = client.patch("/api/bot/session", json={"setup_levels": {"first_pullback": 2}}, headers=headers(api_key))
    _refused(res)
    assert own_levels(load_session()).get("first_pullback") == 1


def test_a_strategy_set_to_eyes_or_off_is_never_refused(api_key, locked):
    on_practice()
    res = client.patch("/api/bot/session", json={"setup_levels": {"first_pullback": 1}}, headers=headers(api_key))
    assert res.status_code == 200


def test_a_family_key_turned_on_is_refused_and_off_always_goes(api_key, locked):
    on_practice()
    client.post("/api/bot/session/keys", json={"family": "strategy", "on": False}, headers=headers(api_key))
    assert family_keys.is_on("strategy") is False
    _refused(client.post("/api/bot/session/keys", json={"family": "strategy", "on": True}, headers=headers(api_key)))
    assert family_keys.is_on("strategy") is False


def test_a_tradertv_hosts_key_turned_on_is_refused_and_stays_off(api_key, locked):
    on_practice()
    _refused(client.patch("/api/bot/live-traders/ALPHA", json={"key": True}, headers=headers(api_key)))
    assert lt_settings.of("ALPHA")["key"] is False
    # Other settings still save while it is locked: only turning a bot on asks for the padlock.
    assert client.patch("/api/bot/live-traders/ALPHA", json={"take_open": False}, headers=headers(api_key)).status_code == 200


def test_unlocked_every_bot_turns_on(api_key):
    on_practice()
    assert client.patch("/api/bot/live-traders/ALPHA", json={"key": True}, headers=headers(api_key)).status_code == 200
    assert lt_settings.of("ALPHA")["key"] is True
    assert get_session()["bot_on"] is True              # on flows up (bot.cascade)


def test_on_live_it_never_asks_for_the_padlock(locked):
    from bot.padlock_gate import refusal

    on_practice("live")
    assert refusal() is None                            # the Live rules refuse instead: no PIN prompt for a bot
