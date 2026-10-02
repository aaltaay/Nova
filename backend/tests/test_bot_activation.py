"""Activate: one control, one meaning, never silently carried (ADR 042 B, C).

Activate refuses with a plain reason; the backend clears it on a start, a locked padlock,
a venue change, the master below Strategy, no setup at Strategy, a trip and the operator,
and says why (``deactivated`` and the ``deactivate`` audit line). The gate list is the
contract's, every gate with its text.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from bot.arming import is_desk_active, issue_arm_token
from bot.audit import list_entries
from bot.autonomy import apply_patch
from bot.persist import load_session, save_session
from bot.session import get_session
from constants_bot import (
    BOT_REASON_LEVEL_NOT_STRATEGY,
    BOT_REASON_LIVE_NOT_BUILT,
    BOT_REASON_NO_SETUP_AT_STRATEGY,
    BOT_REASON_PADLOCK_LOCKED,
    BOT_REASON_REPLAY_DESK,
    BOT_REASON_TRIP_LATCHED,
    BOT_REASON_VENUE_UNKNOWN,
)
from main import app
from tests.bot_helpers import headers, on_practice

client = TestClient(app)
GATE_IDS = ["venue", "level", "setups", "padlock", "allowlist", "depth_lines", "bot_trip", "day_lock",
            "kill_switch", "window", "daily_cap", "extended_hours", "commissions"]


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("NOVA_API_KEY", "bot-test-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    return "bot-test-key"


def _strategy() -> None:
    apply_patch({"level": 2, "setup_levels": {"first_pullback": 2}}, desk=True)


def _arm(api_key: str, **body):
    return client.post("/api/bot/session/arm", json=body, headers=headers(api_key))


# -- the refusals ----------------------------------------------------------------------
def test_activate_on_live_is_refused_it_is_not_built(api_key):
    _strategy()                                           # the suite's default venue is Live
    res = _arm(api_key)
    assert res.status_code == 409
    assert res.json()["detail"]["reason"] == BOT_REASON_LIVE_NOT_BUILT
    assert "Live trading by a bot is not built" in res.json()["detail"]["error"]
    assert get_session()["active"] is False


def test_activate_on_a_replay_desk_is_refused(api_key):
    from sim.mode import set_venue

    set_venue("sim", persist=False)                       # the suite pins Sim's live edge off
    _strategy()
    res = _arm(api_key)
    assert res.status_code == 409 and res.json()["detail"]["reason"] == BOT_REASON_REPLAY_DESK


def test_activate_with_the_venue_unreadable_is_refused(api_key, monkeypatch):
    on_practice()
    _strategy()

    def broken():
        raise RuntimeError("venue file unreadable")

    monkeypatch.setattr("sim.mode.venue", broken)
    res = _arm(api_key)
    assert res.status_code == 409 and res.json()["detail"]["reason"] == BOT_REASON_VENUE_UNKNOWN


@pytest.mark.parametrize("patch, reason", [
    ({"level": 1, "setup_levels": {"first_pullback": 2}}, BOT_REASON_LEVEL_NOT_STRATEGY),
    ({"level": 2, "setup_levels": {"first_pullback": 1}}, BOT_REASON_NO_SETUP_AT_STRATEGY),
])
def test_activate_needs_the_master_and_a_setup_at_strategy(api_key, patch, reason):
    on_practice()
    apply_patch(patch, desk=True)
    res = _arm(api_key)
    assert res.status_code == 409 and res.json()["detail"]["reason"] == reason


def test_activate_with_the_padlock_locked_is_refused(api_key, monkeypatch):
    on_practice()
    _strategy()
    monkeypatch.setattr("ibkr.trading_allowed.places_allowed", lambda: (False, "desk disarmed"))
    res = _arm(api_key)
    assert res.status_code == 409 and res.json()["detail"]["reason"] == BOT_REASON_PADLOCK_LOCKED
    assert "unlock it" in res.json()["detail"]["error"]


def test_a_bot_trip_needs_reenable_said_in_words(api_key):
    from bot.clock import lock_until_date

    on_practice()
    _strategy()
    row = load_session()
    row.update(soft_breaker_fired=True, soft_breaker_until=lock_until_date(), soft_breaker_at=1_790_000_000.0,
               soft_breaker_pnl=-55.0)
    save_session(row)
    res = _arm(api_key)
    assert res.status_code == 409 and res.json()["detail"]["reason"] == BOT_REASON_TRIP_LATCHED
    error = res.json()["detail"]["error"]
    assert "The bot trip fired at" in error and "(P&L -$55.00)" in error and "re-enable" in error
    ok = _arm(api_key, reenable=True)
    assert ok.status_code == 200 and ok.json()["active"] is True
    assert ok.json()["soft_breaker"]["fired"] is False


def test_activate_turns_it_on_and_says_so(api_key):
    on_practice()
    _strategy()
    res = _arm(api_key)
    assert res.status_code == 200
    body = res.json()
    assert body["active"] is True and body["armed"] is True and body["deactivated"] is None
    assert body["desk_arm_token"]
    assert ("activate", "ok") in [(r["action"], r["outcome"]) for r in list_entries(limit=20)]


# -- the backend clears it -----------------------------------------------------------------
def test_locking_the_padlock_clears_activate_in_the_backend(api_key):
    from ibkr import safety

    on_practice()
    _strategy()
    assert _arm(api_key).status_code == 200
    safety.arm(False, actor="operator")
    row = load_session()
    assert not is_desk_active(row)
    assert row["deactivated"]["reason"] == "padlock" and "padlock" in row["deactivated"]["text"]
    assert any(r["action"] == "deactivate" and r["inputs"].get("reason") == "padlock" for r in list_entries(limit=20))


def test_a_venue_change_clears_activate_as_the_venues_not_the_padlocks():
    from sim.mode import set_venue

    on_practice()
    _strategy()
    issue_arm_token()
    set_venue("live", persist=False)
    set_venue("paper", persist=False)
    row = load_session()
    assert not is_desk_active(row) and row["deactivated"]["reason"] == "venue"


def test_a_restart_clears_activate_and_says_so():
    from bot import persist
    from bot.activation import note_start

    on_practice()
    _strategy()
    issue_arm_token()
    assert is_desk_active(load_session())
    persist._session = None                           # a new process reads the file
    row = load_session()
    assert not is_desk_active(row)
    assert row["deactivated"]["reason"] == "restart" and "restart" in row["deactivated"]["text"]
    on_disk = json.loads(persist._session_path().read_text(encoding="utf-8"))
    assert on_disk["armed"] is True                   # a reader alone never rewrites the file ...
    note_start()                                      # ... the API's bot does, and says so
    on_disk = json.loads(persist._session_path().read_text(encoding="utf-8"))
    assert on_disk["armed"] is False and on_disk["deactivated"]["reason"] == "restart"
    assert any(r["action"] == "deactivate" and r["inputs"].get("reason") == "restart" for r in list_entries(limit=20))


def test_deactivate_by_the_operator(api_key):
    on_practice()
    _strategy()
    assert _arm(api_key).status_code == 200
    res = client.post("/api/bot/session/disarm", json={}, headers=headers(api_key))
    assert res.status_code == 200 and res.json()["active"] is False
    assert res.json()["deactivated"]["reason"] == "operator"


def test_a_trip_deactivates_with_its_reason():
    from bot.autonomy import drop_to_l0

    on_practice()
    _strategy()
    issue_arm_token()
    drop_to_l0(keep_soft_latch=True, reason="all_stop")
    row = load_session()
    assert row["level"] == 1 and row["deactivated"]["reason"] == "all_stop"     # ADR 044: off at Eyes


# -- ready and the gates -------------------------------------------------------------------
def test_the_gates_are_the_contracts_with_a_reason_each():
    view = get_session()
    assert [g["id"] for g in view["gates"]] == GATE_IDS
    for gate in view["gates"]:
        assert gate["stage"] in ("activate", "fire")
        assert isinstance(gate["detail"]["text"], str) and gate["detail"]["text"]
    venue = view["gates"][0]
    assert venue["ok"] is False and venue["detail"]["venue"] == "live"          # Live: not built


def test_ready_says_why_not(api_key):
    from tests.bot_helpers import hold_depth_line, set_symbols

    on_practice()
    _strategy()
    view = get_session()
    assert view["ready"] is False and view["live_fire_ready"] is False
    assert "not active" in view["ready_reason"]
    assert _arm(api_key).status_code == 200
    view = get_session()
    assert view["ready"] is False and "no stock is set to Bot" in view["ready_reason"]
    set_symbols("ABCD")
    view = get_session()
    assert view["ready"] is False and "Level 2" in view["ready_reason"]
    hold_depth_line("ABCD")
    view = get_session()
    assert view["ready"] is True and view["ready_reason"] is None and view["live_fire_ready"] is True
    gates = {g["id"]: g for g in view["gates"]}
    assert gates["setups"]["detail"]["at_strategy"] == ["first_pullback"]
    assert gates["depth_lines"]["detail"]["held"] == ["ABCD"] and gates["depth_lines"]["detail"]["max_lines"] == 3
    assert gates["daily_cap"]["detail"] == {"count": 0, "cap": 1, "venue_day": gates["daily_cap"]["detail"]["venue_day"],
                                            "text": gates["daily_cap"]["detail"]["text"]}
    window = gates["window"]["detail"]["setups"][0]
    assert window["setup"] == "first_pullback" and window["open"] is True


def test_the_old_routes_are_gone(api_key):
    assert client.post("/api/bot/llm/spend", json={"usd": 0.02}, headers=headers(api_key)).status_code in (404, 405)
    assert client.post("/api/bot/advise", json={"symbol": "AAPL"}, headers=headers(api_key)).status_code in (404, 405)
    assert client.get("/api/bot/advise/latest?symbol=AAPL").status_code in (404, 405)


def test_level_changes_and_activate_land_on_the_timeline(api_key):
    on_practice()
    apply_patch({"level": 1}, desk=True)
    _strategy()
    assert _arm(api_key).status_code == 200
    client.post("/api/bot/session/disarm", json={}, headers=headers(api_key))
    rows = [(r["action"], r["outcome"]) for r in list_entries(limit=50)]
    assert ("level", "0->1") in rows and ("level", "1->2") in rows
    assert ("activate", "ok") in rows and ("deactivate", "ok") in rows
