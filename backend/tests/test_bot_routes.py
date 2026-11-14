"""Localhost bot HTTP contract -- TestClient, no live IBKR orders.

ADR 072: the bots are retired. The bot API keeps its session read, the session's PATCH for your risk per trade
alone (``bot.caps``), the brain's claim and heartbeat, the watch, the action door (refused until the brain is built)
and the audit stream; the Bot switch, the keys, Activate, the allowlist, proposals, focus, the day P&L meter and the
squares are gone.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from constants_bot import (
    BOT_BRAIN_DOOR_CLOSED_TEXT,
    BOT_LEVEL_EYES,
    BOT_REASON_ARM_REQUIRED,
    BOT_REASON_BRAIN_EXCLUSIVE,
    BOT_REASON_L0_DARK,
    BOT_REASON_LIVE_NOT_BUILT,
    BOT_REASON_NOT_ACTIVE,
)
from main import app
from tests.bot_helpers import headers, hold_depth_line, on_practice, set_level, set_symbols

SHORTS = ("backside_lower_high", "bear_flag", "failed_breakout", "lost_vwap", "ssr_bounce")   # ADR 049

client = TestClient(app)


@pytest.fixture
def bot_iso():
    from bot.persist import reset_for_tests

    reset_for_tests()
    yield
    reset_for_tests()


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("NOVA_API_KEY", "bot-test-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    return "bot-test-key"


@pytest.fixture
def no_send(monkeypatch):
    """Counts every order the bot API would hand the execution door."""
    sent: list = []

    async def fake_execute(cmd, wait_ack=False):
        sent.append(cmd)
        raise AssertionError("the bot API reached the execution door")

    monkeypatch.setattr("bot.actions.execute", fake_execute)
    return sent


def test_session_get_l0_open_without_key(bot_iso):
    res = client.get("/api/bot/session")
    assert res.status_code == 200
    body = res.json()
    assert body["level"] == 0 and body["active"] is False
    assert "desk_arm_token" not in body
    # ADR 027 / 042 / 056 / 072: what left the answer stays gone.
    for gone in ("packs", "active_pack", "llm", "setup", "strategy", "readout", "readout_required", "advise",
                 "breakers", "soft_breaker", "day_lock", "hard_lock_until_date", "gates", "keys", "bot_on",
                 "ready", "ready_reason", "runner", "trade", "entries_today", "shorts", "deactivated", "armed"):
        assert gone not in body
    setups = {row["id"]: row["scanner"] for row in body["setups"]}
    assert setups == {"first_pullback": True, "bull_flag": True, "flat_top_breakout": True, "flat_top_5m": True,
                      "red_to_green": True, "gap_and_go": True, "pullback_dip": True, "abcd": True,
                      **dict.fromkeys(SHORTS, True), "micro_pullback": False}
    # ADR 072: every strategy watches -- each scanner reads Eyes, whatever the file stored.
    levels = {row["id"]: (row["level"], row["effective"]) for row in body["setups"]}
    assert levels == {**{sid: (BOT_LEVEL_EYES, BOT_LEVEL_EYES) for sid, scanner in setups.items() if scanner},
                      "micro_pullback": (None, None)}
    sides = {row["id"]: row["side"] for row in body["setups"]}
    assert {sid for sid, side in sides.items() if side == "short"} == set(SHORTS)
    assert set(body["caps_by_venue"]) == {"live", "paper", "sim"}
    assert client.get("/bot/session").status_code == 200


def test_mutate_requires_configured_key(bot_iso, monkeypatch):
    monkeypatch.delenv("NOVA_API_KEY", raising=False)
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    for path in ("/api/bot/session/claim", "/bot/session/claim"):
        res = client.post(path, json={"brain_session_id": "brain-a"})
        assert res.status_code == 503
        assert "NOVA_API_KEY" in str(res.json()["detail"])


def test_mutate_requires_matching_key(bot_iso, api_key):
    assert client.post("/api/bot/session/claim", json={"brain_session_id": "brain-a"}).status_code == 401
    assert client.post("/bot/session/claim", json={"brain_session_id": "brain-a"}).status_code == 401
    keyed = client.post("/api/bot/session/claim", json={"brain_session_id": "brain-a"}, headers=headers(api_key))
    assert keyed.status_code == 409 and keyed.json()["detail"]["reason"] == BOT_REASON_BRAIN_EXCLUSIVE


@pytest.mark.parametrize("method, path", [
    ("post", "/api/bot/session/arm"), ("post", "/api/bot/session/disarm"),
    ("post", "/api/bot/session/switch"), ("post", "/api/bot/session/keys"), ("post", "/api/bot/allowlist"),
    ("post", "/api/bot/proposals"), ("post", "/api/bot/focus/sync"), ("get", "/api/bot/pnl"),
    ("get", "/api/bot/triggers"), ("post", "/api/bot/advise"),
])
def test_the_retired_routes_are_gone(bot_iso, api_key, method, path):
    res = getattr(client, method)(path, json={}, headers=headers(api_key)) if method != "get" else client.get(path)
    assert res.status_code in (404, 405)


def test_no_brain_can_claim_or_beat_until_the_brain_is_built(bot_iso, api_key):
    set_level(2)
    h = headers(api_key)
    claim = client.post("/api/bot/session/claim", json={"brain_session_id": "brain-a"}, headers=h)
    assert claim.status_code == 409
    assert claim.json()["detail"] == {"reason": BOT_REASON_ARM_REQUIRED, "error": BOT_BRAIN_DOOR_CLOSED_TEXT}
    beat = client.post("/api/bot/session/heartbeat", json={"brain_session_id": "brain-a"}, headers=h)
    assert beat.status_code == 409 and beat.json()["detail"]["reason"] == BOT_REASON_ARM_REQUIRED
    assert client.get("/api/bot/session").json()["brain_session_id"] is None


def test_the_action_door_sends_nothing(bot_iso, api_key, no_send):
    h = headers(api_key)
    body = {"kind": "buy_market", "symbol": "ABCD", "brain_session_id": "brain-a"}
    live = client.post("/api/bot/action", json=body, headers=h)
    assert live.status_code == 409 and live.json()["detail"]["reason"] == BOT_REASON_LIVE_NOT_BUILT
    on_practice()
    dark = client.post("/api/bot/action", json=body, headers=h)
    assert dark.status_code == 409 and dark.json()["detail"]["reason"] == BOT_REASON_L0_DARK
    set_level(2)
    set_symbols("ABCD")
    hold_depth_line("ABCD")
    for kind in ("buy_market", "exit_pos", "cancel_symbol", "short_limit_bid_offset"):
        shut = client.post("/api/bot/action", json={**body, "kind": kind}, headers=h)
        assert shut.status_code == 409
        assert shut.json()["detail"] == {"reason": BOT_REASON_NOT_ACTIVE, "error": BOT_BRAIN_DOOR_CLOSED_TEXT}
    assert no_send == []


def test_session_payload_carries_last_rewind(bot_iso):
    """A polling bot sees the last Sim unwind on the status payload (null until one happens)."""
    from bot import rewind

    assert client.get("/api/bot/session").json()["last_rewind"] is None
    rewind.publish(venue="sim", playhead_ts=1_700_000_000.0, dropped_orders=2, dropped_fills=1)
    seen = client.get("/api/bot/session").json()["last_rewind"]
    assert {k: seen[k] for k in ("venue", "playhead_ts", "dropped_orders", "dropped_fills")} == {
        "venue": "sim", "playhead_ts": 1_700_000_000.0, "dropped_orders": 2, "dropped_fills": 1,
    }
    audit = client.get("/api/bot/audit").json()["entries"]
    assert audit[-1]["action"] == "practice_rewind" and audit[-1]["inputs"]["dropped_orders"] == 2


def test_watch_and_audit(bot_iso):
    watch = client.get("/api/bot/watch")
    assert watch.status_code == 200 and "symbols" in watch.json() and "setup" not in watch.json()
    audit = client.get("/api/bot/audit")
    assert audit.status_code == 200 and "entries" in audit.json()


def test_openapi_keeps_the_brains_door_and_drops_activate(bot_iso):
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    paths = spec.json()["paths"]
    assert {"/api/bot/session", "/api/bot/action", "/api/bot/session/claim", "/api/bot/session/heartbeat"} <= set(paths)
    assert "/api/bot/session/arm" not in paths and "/api/stock-mode" not in paths
    assert "bot" in {t["name"] for t in spec.json().get("tags") or []}


def test_the_session_patch_sets_your_risk_per_trade_and_nothing_else(bot_iso, api_key):
    """ADR 072: the Trader's plan card and the Setups board size Stage by the sleeve's risk per trade, so
    ``PATCH /api/bot/session {caps}`` stays; a level, a setup's level or the stocks are refused in words."""
    from constants_bot import BOT_REASON_CAPS_DESK_ONLY, BOT_REASON_STRATEGIES_WATCH

    res = client.patch("/api/bot/session", json={"caps": {"venue": "paper", "risk_usd": 45}}, headers=headers(api_key))
    assert res.status_code == 200, res.text
    assert res.json()["caps_by_venue"]["paper"]["risk_usd"] == 45

    refused = client.patch("/api/bot/session", json={"level": 2, "caps": {"venue": "paper", "risk_usd": 50}},
                           headers=headers(api_key))
    assert refused.status_code == 410
    assert refused.json()["detail"]["reason"] == BOT_REASON_STRATEGIES_WATCH
    assert "refused: level" in refused.json()["detail"]["error"]
    assert client.get("/api/bot/session").json()["caps_by_venue"]["paper"]["risk_usd"] == 45

    brain = client.patch("/api/bot/session", json={"caps": {"venue": "paper", "risk_usd": 60}},
                         headers=headers(api_key, brain="brain-1"))
    assert brain.status_code == 403
    assert brain.json()["detail"]["reason"] == BOT_REASON_CAPS_DESK_ONLY

    assert client.patch("/api/bot/session", json={"caps": {"venue": "paper"}}).status_code in (401, 403)
