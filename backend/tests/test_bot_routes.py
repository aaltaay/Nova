"""Localhost bot HTTP contract -- TestClient, no live IBKR orders."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bot.autonomy import apply_patch
from constants_bot import (
    BOT_REASON_ALLOWLIST_FULL,
    BOT_REASON_ARM_DESK_ONLY,
    BOT_REASON_HEARTBEAT_STALE,
    BOT_REASON_L0_DARK,
    BOT_REASON_L1_NO_FIRE,
    BOT_REASON_L3_PARKED,
    BOT_REASON_LIVE_NOT_BUILT,
    BOT_REASON_NOT_ACTIVE,
)
from main import app
from tests.bot_helpers import headers, list_hot, on_practice, ready_l2, set_symbols

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
    assert body["active"] is False and body["armed"] is False and body["deactivated"] is None
    assert body["ready"] is False and body["live_fire_ready"] is False and body["ready_reason"]
    assert "desk_arm_token" not in body
    # ADR 027: the playbook replaces the packs; ADR 042: no chosen setup, strategy, read-out or advise budget.
    for gone in ("packs", "active_pack", "llm", "setup", "strategy", "readout", "readout_required", "advise"):
        assert gone not in body
    setups = {row["id"]: row["scanner"] for row in body["setups"]}
    # ADR 031: the bull flag joins; it, the flat-top breakout, red to green, (2026-10-02) Gap and Go and
    # (2026-10-06) the 5-minute flat top have scanners.
    assert setups == {"first_pullback": True, "bull_flag": True, "flat_top_breakout": True, "flat_top_5m": True,
                      "red_to_green": True, "gap_and_go": True, "micro_pullback": False}
    levels = {row["id"]: (row["level"], row["effective"]) for row in body["setups"]}
    assert levels == {"first_pullback": (0, 0), "bull_flag": (0, 0), "flat_top_breakout": (0, 0),
                      "flat_top_5m": (0, 0), "red_to_green": (0, 0), "gap_and_go": (0, 0),
                      "micro_pullback": (None, None)}
    assert body["setup_levels"] == {"first_pullback": 0, "bull_flag": 0, "flat_top_breakout": 0, "flat_top_5m": 0,
                                    "red_to_green": 0, "gap_and_go": 0}
    assert body["breakers"]["soft_usd"] == -50.0 and body["breakers"]["hard_usd"] == -200.0
    assert [g["id"] for g in body["gates"]] == [
        "venue", "level", "setups", "padlock", "allowlist", "depth_lines", "bot_trip", "day_lock",
        "kill_switch", "window", "daily_cap", "extended_hours", "commissions"]
    assert set(body["caps_by_venue"]) == {"live", "paper", "sim"}
    assert body["entries_today"]["count"] == 0 and body["entries_today"]["cap"] == 1
    assert body["day_lock"]["active"] is False and set(body["day_locks"]) == {"live", "paper", "sim"}
    assert body["soft_breaker"] == {"fired": False, "at": None, "pnl": None, "until": None}
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
    live = client.post("/api/bot/action", json={"kind": "buy_market", "symbol": "ABCD"}, headers=headers(api_key))
    assert live.status_code == 409 and live.json()["detail"]["reason"] == BOT_REASON_LIVE_NOT_BUILT
    on_practice()
    res = client.post(
        "/api/bot/action",
        json={"kind": "buy_market", "symbol": "ABCD"},
        headers=headers(api_key),
    )
    assert res.status_code == 409
    assert res.json()["detail"]["reason"] == BOT_REASON_L0_DARK


def test_strategy_needs_no_desk_token_and_lands_not_active(bot_iso, api_key):
    res = client.patch("/api/bot/session", json={"level": 2}, headers=headers(api_key))
    assert res.status_code == 200
    assert res.json()["level"] == 2 and res.json()["active"] is False


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
    sneak = client.patch(
        "/api/bot/session",
        json={"level": 2},
        headers=headers(api_key, brain="nova-brain"),
    )
    assert sneak.status_code == 403
    assert sneak.json()["detail"]["reason"] == BOT_REASON_ARM_DESK_ONLY
    assert client.get("/api/bot/session").json()["level"] == 0
    on_practice()
    ok = client.patch("/bot/session", json={"level": 2, "setup_levels": {"first_pullback": 2}},
                      headers=headers(api_key))
    assert ok.status_code == 200 and ok.json()["level"] == 2 and ok.json()["active"] is False
    armed = client.post("/api/bot/session/arm", headers=headers(api_key))
    assert armed.status_code == 200 and armed.json()["active"] is True and armed.json()["desk_arm_token"]
    assert "desk_arm_token" not in client.get("/api/bot/session").json()


def test_l1_proposal_schema_and_no_fire(bot_iso, api_key):
    h = headers(api_key)
    on_practice()
    assert client.patch("/api/bot/session", json={"level": 1}, headers=h).status_code == 200
    set_symbols("ABCD")
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
    live = client.post("/api/bot/allowlist", json={"symbol": "abcd", "op": "add"}, headers=h)
    assert live.status_code == 409 and live.json()["detail"]["reason"] == "STOCK_MODE_LIVE"   # never Nova's on Live
    on_practice()
    add = client.post("/api/bot/allowlist", json={"symbol": "abcd", "op": "add"}, headers=h)
    assert add.status_code == 200
    assert "ABCD" in add.json()["symbol_allowlist"]
    alias = client.post("/bot/allowlist", json={"symbol": "ABCD", "op": "remove"}, headers=h)
    assert alias.status_code == 200
    assert "ABCD" not in alias.json()["symbol_allowlist"]
    watch = client.get("/api/bot/watch")
    assert watch.status_code == 200
    assert "symbols" in watch.json() and watch.json()["ready"] is False and "setup" not in watch.json()


def test_the_list_goes_through_stock_mode_and_says_what_it_refused(bot_iso, api_key):
    from bot.audit import list_entries

    on_practice()
    res = client.patch("/api/bot/session", json={"symbol_allowlist": ["aaa", "bbb"]}, headers=headers(api_key))
    assert res.status_code == 200 and res.json()["symbol_allowlist"] == ["AAA", "BBB"] and res.json()["refused"] == []
    assert [r["outcome"] for r in list_entries(limit=20) if r["action"] == "stock_mode"] == ["set", "set"]
    res = client.patch("/api/bot/session", json={"symbol_allowlist": ["bbb", "!!!!!!!!!!!!!!!!"]},
                       headers=headers(api_key))
    body = res.json()
    assert body["symbol_allowlist"] == ["BBB"]
    [refused] = body["refused"]
    assert refused["symbol"] == "!!!!!!!!!!!!!!!!" and refused["reason"] == "STOCK_MODE_INVALID"


def test_a_full_list_is_refused_and_nothing_is_audited_as_done(bot_iso, api_key):
    from bot.audit import list_entries

    on_practice()
    set_symbols(*[f"S{i:02d}" for i in range(50)])
    list_hot("FULL")                    # a starred stock: the bot list's own cap still refuses it
    res = client.post("/api/bot/allowlist", json={"symbol": "FULL", "op": "add"}, headers=headers(api_key))
    assert res.status_code == 409 and res.json()["detail"]["reason"] == BOT_REASON_ALLOWLIST_FULL
    assert "full" in res.json()["detail"]["error"]
    assert "FULL" not in client.get("/api/bot/session").json()["symbol_allowlist"]
    assert [r for r in list_entries(limit=20) if r["action"] == "stock_mode"] == []


def test_a_full_hot_list_never_refuses_a_stock_the_bot_buys(bot_iso, api_key):
    """ADR 044, amended 2026-10-06: Buy = Nova never stars the stock, so a full list (20) refuses nothing and
    the stock stays off it."""
    import hot_list
    from bot.audit import list_entries
    from constants_hot_list import HOT_LIST_CAP

    on_practice()
    list_hot(*[f"H{i:02d}" for i in range(HOT_LIST_CAP)])
    res = client.post("/api/bot/allowlist", json={"symbol": "MORE", "op": "add"}, headers=headers(api_key))
    assert res.status_code == 200 and "MORE" in client.get("/api/bot/session").json()["symbol_allowlist"]
    assert not hot_list.is_listed("MORE") and len(hot_list.listed_symbols()) == HOT_LIST_CAP
    assert [r["outcome"] for r in list_entries(limit=20) if r["action"] == "stock_mode"] == ["set"]
    assert [r for r in list_entries(limit=20) if r["action"] == "hot_list"] == []


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


def test_audit_and_no_advise_route(bot_iso, api_key):
    apply_patch({"level": 1}, desk=True)
    off = client.post("/api/bot/advise", json={"symbol": "AAPL"}, headers=headers(api_key))
    assert off.status_code in (404, 405)                 # ADR 042 K: the bot's advise budget is gone
    audit = client.get("/api/bot/audit")
    assert audit.status_code == 200
    assert "entries" in audit.json()
