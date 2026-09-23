"""Strategy waits on the first-pullback read-out; entries keep the material's rules (ADR 027)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bot.autonomy import apply_patch
from bot.arming import issue_arm_token
from bot.errors import BotError
from bot.gates import set_readout_for_tests
from bot.session import get_session
from constants_bot import (
    BOT_REASON_READOUT_NOT_PASSED,
    BOT_REASON_SETUP_NO_SCANNER,
)
from main import app
from setup_scanner.readout import evaluate
from tests.bot_helpers import headers

client = TestClient(app)


@pytest.fixture
def closed():
    set_readout_for_tests(evaluate([]))


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("NOVA_API_KEY", "bot-test-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    return "bot-test-key"


def test_strategy_can_be_chosen_but_lands_not_active(closed):
    token = issue_arm_token()
    apply_patch({"level": 2}, desk=True, arm_token=token)
    view = get_session()
    assert view["level"] == 2
    assert view["armed"] is False and view["has_desk_arm"] is False
    assert view["live_fire_ready"] is False
    gate = {g["id"]: g for g in view["gates"]}["readout"]
    assert gate["ok"] is False and gate["stage"] == "activate"
    assert gate["detail"]["go_triggered"] == 0 and gate["detail"]["min_go"] == 50


def test_activate_at_strategy_is_refused_until_the_readout_passes(closed, api_key):
    token = issue_arm_token()
    apply_patch({"level": 2}, desk=True, arm_token=token)
    res = client.post("/api/bot/session/arm", json={}, headers=headers(api_key))
    assert res.status_code == 409
    assert res.json()["detail"]["reason"] == BOT_REASON_READOUT_NOT_PASSED
    assert get_session()["armed"] is False


def test_activate_at_eyes_is_unchanged(closed, api_key):
    apply_patch({"level": 1}, desk=True)
    res = client.post("/api/bot/session/arm", json={}, headers=headers(api_key))
    assert res.status_code == 200
    assert res.json()["armed"] is True


def test_a_pass_opens_activate_at_strategy(api_key):
    token = issue_arm_token()
    apply_patch({"level": 2}, desk=True, arm_token=token)
    view = get_session()
    assert view["armed"] is True  # the conftest baseline read-out passed
    res = client.post("/api/bot/session/arm", json={}, headers=headers(api_key))
    assert res.status_code == 200


def test_only_a_setup_with_a_scanner_can_be_chosen(api_key):
    res = client.patch("/api/bot/session", json={"setup": "gap_and_go"}, headers=headers(api_key))
    assert res.status_code == 400
    assert res.json()["detail"]["reason"] == BOT_REASON_SETUP_NO_SCANNER
    ok = client.patch("/api/bot/session", json={"setup": "first_pullback"}, headers=headers(api_key))
    assert ok.status_code == 200 and ok.json()["setup"] == "first_pullback"
    with pytest.raises(BotError):
        apply_patch({"setup": "no_such_setup"})


def test_a_brain_may_propose_at_strategy_while_the_readout_is_closed(closed, monkeypatch):
    from bot.persist import load_session, save_session
    from bot.proposals import submit

    token = issue_arm_token()
    apply_patch({"level": 2}, desk=True, arm_token=token)
    row = load_session()
    row["symbol_allowlist"] = ["GRML"]
    row["trader_live"] = ["GRML"]
    save_session(row)
    item = submit({"symbol": "GRML", "side": "BUY", "kind": "buy_limit_ask_offset",
                   "reason": "first pullback near 8.72, tape go"}, brain_session_id="ext")
    assert item["status"] == "pending"


def test_the_llm_spend_route_is_gone(api_key):
    res = client.post("/api/bot/llm/spend", json={"usd": 0.02}, headers=headers(api_key))
    assert res.status_code in (404, 405)


def test_entries_today_counts_the_venue_day():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from bot.entry_rules import entries_today

    now = datetime(2026, 9, 22, 9, 0, tzinfo=ZoneInfo("America/New_York"))
    rows = [
        {"action": "buy_market", "outcome": "ok", "inputs": {"venue_day": "2026-09-22"}, "timestamp": 0},
        {"action": "buy_market", "outcome": "failed", "inputs": {"venue_day": "2026-09-22"}, "timestamp": 0},
        {"action": "exit_pos", "outcome": "ok", "inputs": {"venue_day": "2026-09-22"}, "timestamp": 0},
        {"action": "buy_limit_ask_offset", "outcome": "ok", "inputs": {"venue_day": "2026-09-21"}, "timestamp": 0},
    ]
    assert entries_today(now, rows=rows) == 1


def test_level_changes_and_activate_land_on_the_timeline(closed, api_key):
    from bot.audit import list_entries

    apply_patch({"level": 1}, desk=True)
    token = issue_arm_token()
    apply_patch({"level": 2}, desk=True, arm_token=token)
    client.post("/api/bot/session/disarm", json={}, headers=headers(api_key))
    rows = [(r["action"], r["outcome"]) for r in list_entries(limit=50)]
    assert ("level", "0->1") in rows
    assert ("level", "1->2") in rows
    assert ("deactivate", "ok") in rows
    [strategy] = [r for r in list_entries(limit=50) if r["outcome"] == "1->2"]
    assert "read-out" in strategy["reason"]
