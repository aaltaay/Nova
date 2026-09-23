"""Localhost bot HTTP contract -- TestClient, no live IBKR orders."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bot.autonomy import apply_patch
from constants_bot import (
    BOT_REASON_ARM_DESK_ONLY,
    BOT_REASON_ARM_REQUIRED,
    BOT_REASON_BRAIN_EXCLUSIVE,
    BOT_REASON_HEARTBEAT_STALE,
    BOT_REASON_L0_DARK,
    BOT_REASON_L1_NO_FIRE,
    BOT_REASON_L3_PARKED,
    BOT_REASON_NOT_ACTIVE,
)
from main import app
from tests.bot_helpers import headers, ready_l2

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


def test_session_get_l0_open_without_key(bot_iso):
    res = client.get("/api/bot/session")
    assert res.status_code == 200
    body = res.json()
    assert body["level"] == 0
    assert body["armed"] is False
    assert body["live_fire_ready"] is False
    assert "desk_arm_token" not in body
    # ADR 027: the playbook replaces the packs.
    assert "packs" not in body and "active_pack" not in body and "llm" not in body
    assert body["setup"] == "first_pullback"
    setups = {row["id"]: row["scanner"] for row in body["setups"]}
    assert setups == {"first_pullback": True, "gap_and_go": False, "flat_top_breakout": False,
                      "red_to_green": False, "micro_pullback": False}
    assert {g["id"] for g in body["gates"]} == {
        "level", "allowlist", "desk_armed", "depth_lines", "readout", "bot_trip", "day_lock",
        "kill_switch", "window"}
    assert body["readout"]["passed"] is True  # the test baseline (conftest)
    alias = client.get("/bot/session")
    assert alias.status_code == 200


def test_mutate_requires_configured_key(bot_iso, monkeypatch):
    monkeypatch.delenv("NOVA_API_KEY", raising=False)
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    for path in ("/api/bot/session", "/bot/session"):
        res = client.patch(path, json={"level": 1})
        assert res.status_code == 503
        assert "NOVA_API_KEY" in str(res.json()["detail"])


def test_mutate_requires_matching_key(bot_iso, api_key):
    missing = client.patch("/api/bot/session", json={"level": 1})
    assert missing.status_code == 401
    alias = client.patch("/bot/session", json={"level": 1})
    assert alias.status_code == 401
    ok = client.patch("/api/bot/session", json={"level": 1}, headers=headers(api_key))
    assert ok.status_code == 200
    assert ok.json()["level"] == 1


def test_patch_l3_parked(bot_iso, api_key):
    res = client.patch("/api/bot/session", json={"level": 3}, headers=headers(api_key))
    assert res.status_code == 409
    assert res.json()["detail"]["reason"] == BOT_REASON_L3_PARKED


def test_l2_not_active_action_rejected(bot_iso, api_key):
    from bot.arming import disarm_session

    ready_l2(brain="brain-1", heartbeat=True)
    disarm_session()
    res = client.post(
        "/api/bot/action",
        json={"kind": "buy_market", "symbol": "ABCD", "brain_session_id": "brain-1"},
        headers=headers(api_key),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["reason"] == BOT_REASON_NOT_ACTIVE


def test_l2_active_action_reaches_execute(bot_iso, api_key, monkeypatch):
    from execution.models import ExecutionReceipt

    ready_l2(brain="brain-1", heartbeat=True)
    seen = {}

    async def fake_execute(cmd, wait_ack=False):
        seen["source"] = cmd.source
        return ExecutionReceipt(
            ok=True,
            execution_id="exec-bot",
            operation="place",
            source="bot",
            idempotency_key="k",
            order_id=88,
        )

    monkeypatch.setattr("bot.actions.execute", fake_execute)
    monkeypatch.setattr("bot.risk.last_quote", lambda _s: {"price": 2.0})
    res = client.post(
        "/api/bot/action",
        json={"kind": "buy_market", "symbol": "ABCD", "brain_session_id": "brain-1"},
        headers=headers(api_key),
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert res.json()["order_id"] == 88
    assert seen["source"] == "bot"


def test_l2_action_without_a_depth_line_is_409_bot_no_depth_line(bot_iso, api_key, monkeypatch):
    """HTTP contract for the ADR 020 fire gate: allowlisted, live-reported, no held line."""
    from constants_bot import BOT_REASON_NO_DEPTH_LINE

    ready_l2(brain="brain-1", heartbeat=True, depth_line=False)
    called = {"n": 0}

    async def fake_execute(cmd, wait_ack=False):
        called["n"] += 1
        raise AssertionError("execution door must not be reached")

    monkeypatch.setattr("bot.actions.execute", fake_execute)
    res = client.post(
        "/api/bot/action",
        json={"kind": "buy_market", "symbol": "ABCD", "brain_session_id": "brain-1"},
        headers=headers(api_key),
    )
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["reason"] == BOT_REASON_NO_DEPTH_LINE == "BOT_NO_DEPTH_LINE"
    assert "open its Level 2 or record it" in detail["error"]
    assert called["n"] == 0


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


def test_l0_action_dark(bot_iso, api_key):
    res = client.post(
        "/api/bot/action",
        json={"kind": "buy_market", "symbol": "ABCD"},
        headers=headers(api_key),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["reason"] == BOT_REASON_L0_DARK


def test_l2_without_desk_token_refused(bot_iso, api_key):
    res = client.patch("/api/bot/session", json={"level": 2}, headers=headers(api_key))
    assert res.status_code == 403
    assert res.json()["detail"]["reason"] == BOT_REASON_ARM_REQUIRED


def test_brain_cannot_arm_or_raise(bot_iso, api_key):
    arm = client.post(
        "/api/bot/session/arm",
        json={},
        headers=headers(api_key, brain="nova-brain"),
    )
    assert arm.status_code == 403
    assert arm.json()["detail"]["reason"] == BOT_REASON_ARM_DESK_ONLY
    alias = client.post(
        "/bot/session/arm",
        json={"brain_session_id": "nova-brain"},
        headers=headers(api_key),
    )
    assert alias.status_code == 403
    token = client.post("/api/bot/session/arm", headers=headers(api_key)).json()["desk_arm_token"]
    sneak = client.patch(
        "/api/bot/session",
        json={"level": 2},
        headers=headers(api_key, brain="nova-brain"),
    )
    assert sneak.status_code == 403
    assert sneak.json()["detail"]["reason"] == BOT_REASON_ARM_REQUIRED
    ok = client.patch(
        "/bot/session",
        json={"level": 2},
        headers=headers(api_key, arm=token),
    )
    assert ok.status_code == 200
    assert ok.json()["level"] == 2
    assert ok.json()["armed"] is True
    assert "desk_arm_token" not in ok.json()


def test_l1_proposal_schema_and_no_fire(bot_iso, api_key):
    h = headers(api_key)
    assert client.patch("/api/bot/session", json={"level": 1}, headers=h).status_code == 200
    apply_patch({"symbol_allowlist": ["ABCD"]}, desk=True)
    client.post("/api/bot/focus/sync", json={"live": ["ABCD"]}, headers=h)
    fire = client.post(
        "/api/bot/action",
        json={"kind": "buy_market", "symbol": "ABCD"},
        headers=h,
    )
    assert fire.status_code == 409
    assert fire.json()["detail"]["reason"] == BOT_REASON_L1_NO_FIRE
    bad = client.post(
        "/api/bot/proposals",
        json={"symbol": "ABCD", "side": "BUY", "kind": "buy_market", "reason": ""},
        headers=h,
    )
    assert bad.status_code == 400
    qty = client.post(
        "/api/bot/proposals",
        json={"symbol": "ABCD", "side": "BUY", "kind": "buy_market", "reason": "gap", "qty": 3},
        headers=h,
    )
    assert qty.status_code == 400
    blocked = client.post(
        "/api/bot/proposals",
        json={"symbol": "ZZZZ", "side": "BUY", "kind": "buy_market", "reason": "gap and news"},
        headers=h,
    )
    assert blocked.status_code == 409
    ok = client.post(
        "/api/bot/proposals",
        json={
            "symbol": "abcd",
            "side": "BUY",
            "kind": "buy_market",
            "reason": "gap and news",
            "confidence": 0.7,
        },
        headers=h,
    )
    assert ok.status_code == 200
    item = ok.json()
    assert item["symbol"] == "ABCD"
    assert item["preset_qty"] == 1
    assert item["status"] == "pending"
    listed = client.get("/api/bot/proposals").json()["proposals"]
    assert listed[0]["id"] == item["id"]
    acc = client.post(f"/api/bot/proposals/{item['id']}/accept", headers=h)
    assert acc.status_code == 200
    assert acc.json()["status"] == "accepted"
    assert "order_id" not in acc.json() or acc.json().get("order_id") is None


def test_l2_claim_heartbeat_and_alias_parity(bot_iso, api_key):
    token = ready_l2(brain=None, heartbeat=False)
    h = headers(api_key, arm=token)
    missing = client.post(
        "/api/bot/action",
        json={"kind": "buy_market", "symbol": "ABCD"},
        headers=h,
    )
    assert missing.status_code == 409
    assert missing.json()["detail"]["reason"] == BOT_REASON_HEARTBEAT_STALE
    claim = client.post(
        "/bot/session/claim",
        json={"brain_session_id": "brain-a"},
        headers=h,
    )
    assert claim.status_code == 200
    stale = client.post(
        "/bot/action",
        json={"kind": "buy_market", "symbol": "ABCD", "brain_session_id": "brain-a"},
        headers=h,
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["reason"] == BOT_REASON_HEARTBEAT_STALE
    beat = client.post(
        "/api/bot/session/heartbeat",
        json={"brain_session_id": "brain-a"},
        headers=h,
    )
    assert beat.status_code == 200
    assert beat.json()["brain_alive"] is True
    other = client.post(
        "/api/bot/action",
        json={"kind": "buy_market", "symbol": "ABCD", "brain_session_id": "brain-b"},
        headers=h,
    )
    assert other.status_code == 409
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    paths = spec.json()["paths"]
    assert "/api/bot/session" in paths
    assert "/api/bot/action" in paths
    assert "/api/bot/session/arm" in paths
    tags = {t["name"] for t in spec.json().get("tags") or []}
    assert "bot" in tags


def test_allowlist_and_watch(bot_iso, api_key):
    h = headers(api_key)
    add = client.post("/api/bot/allowlist", json={"symbol": "abcd", "op": "add"}, headers=h)
    assert add.status_code == 200
    assert "ABCD" in add.json()["symbol_allowlist"]
    alias = client.post("/bot/allowlist", json={"symbol": "ABCD", "op": "remove"}, headers=h)
    assert alias.status_code == 200
    assert "ABCD" not in alias.json()["symbol_allowlist"]
    watch = client.get("/api/bot/watch")
    assert watch.status_code == 200
    assert "symbols" in watch.json()
    assert watch.json()["setup"] == "first_pullback"


def test_focus_sync_and_pnl(bot_iso, api_key, monkeypatch):
    apply_patch({"level": 1}, desk=True)
    sync = client.post(
        "/api/bot/focus/sync",
        json={"live": ["aaa", "bbb", "ccc", "ddd"]},
        headers=headers(api_key),
    )
    assert sync.status_code == 200
    assert sync.json()["trader_live"] == ["AAA", "BBB", "CCC"]
    monkeypatch.setattr(
        "routes.bot.read_account_day_pnl",
        lambda: (-12.0, {"day_pnl": -12.0, "commissions": 1.0}),
    )
    pnl = client.get("/api/bot/pnl")
    assert pnl.status_code == 200
    assert pnl.json()["day_pnl"] == -12.0


def test_audit_and_advise_off(bot_iso, api_key):
    apply_patch({"level": 1}, desk=True)
    off = client.post("/api/bot/advise", json={"symbol": "AAPL"}, headers=headers(api_key))
    assert off.status_code == 409
    assert off.json()["detail"]["reason"] == "BOT_ADVISE_OFF"
    audit = client.get("/api/bot/audit")
    assert audit.status_code == 200
    assert "entries" in audit.json()
