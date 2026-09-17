"""Localhost bot HTTP contract -- TestClient, no live IBKR orders."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bot.autonomy import apply_patch
from bot.session import require_l2_brain
from main import app

client = TestClient(app)


@pytest.fixture
def bot_iso():
    from bot.persist import reset_for_tests

    reset_for_tests()
    yield
    reset_for_tests()


def test_session_get_l0(bot_iso):
    res = client.get("/api/bot/session")
    assert res.status_code == 200
    body = res.json()
    assert body["level"] == 0
    assert body["advise"]["enabled"] is False
    alias = client.get("/bot/session")
    assert alias.status_code == 200


def test_patch_l3_parked(bot_iso):
    res = client.patch("/api/bot/session", json={"level": 3})
    assert res.status_code == 409
    assert res.json()["detail"]["reason"] == "BOT_L3_PARKED"


def test_l0_action_dark(bot_iso):
    res = client.post("/api/bot/action", json={"kind": "buy_market", "symbol": "ABCD"})
    assert res.status_code == 409
    assert res.json()["detail"]["reason"] == "BOT_L0_DARK"


def test_l1_proposal_schema_and_no_fire(bot_iso):
    assert client.patch("/api/bot/session", json={"level": 1}).status_code == 200
    fire = client.post("/api/bot/action", json={"kind": "buy_market", "symbol": "ABCD"})
    assert fire.status_code == 409
    assert fire.json()["detail"]["reason"] == "BOT_L1_NO_FIRE"
    bad = client.post(
        "/api/bot/proposals",
        json={"symbol": "ABCD", "side": "BUY", "kind": "buy_market", "reason": ""},
    )
    assert bad.status_code == 400
    qty = client.post(
        "/api/bot/proposals",
        json={"symbol": "ABCD", "side": "BUY", "kind": "buy_market", "reason": "gap", "qty": 3},
    )
    assert qty.status_code == 400
    ok = client.post(
        "/api/bot/proposals",
        json={
            "symbol": "abcd",
            "side": "BUY",
            "kind": "buy_market",
            "reason": "gap and news",
            "confidence": 0.7,
        },
    )
    assert ok.status_code == 200
    item = ok.json()
    assert item["symbol"] == "ABCD"
    assert item["preset_qty"] == 1
    assert item["status"] == "pending"
    listed = client.get("/api/bot/proposals").json()["proposals"]
    assert listed[0]["id"] == item["id"]
    acc = client.post(f"/api/bot/proposals/{item['id']}/accept")
    assert acc.status_code == 200
    assert acc.json()["status"] == "accepted"
    assert "order_id" not in acc.json() or acc.json().get("order_id") is None


def test_l2_exclusive_brain_and_openapi(bot_iso):
    assert client.patch("/api/bot/session", json={"level": 2}).status_code == 200
    missing = client.post("/api/bot/action", json={"kind": "buy_market", "symbol": "ABCD"})
    assert missing.status_code == 409
    assert missing.json()["detail"]["reason"] == "BOT_BRAIN_EXCLUSIVE"
    claim = client.post("/api/bot/session/claim", json={"brain_session_id": "brain-a"})
    assert claim.status_code == 200
    other = client.post(
        "/api/bot/action",
        json={"kind": "buy_market", "symbol": "ABCD", "brain_session_id": "brain-b"},
    )
    assert other.status_code == 409
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    paths = spec.json()["paths"]
    assert "/api/bot/session" in paths
    assert "/api/bot/action" in paths
    tags = {t["name"] for t in spec.json().get("tags") or []}
    assert "bot" in tags


def test_focus_sync_and_pnl(bot_iso, monkeypatch):
    apply_patch({"level": 1}, desk=True)
    sync = client.post("/api/bot/focus/sync", json={"live": ["aaa", "bbb", "ccc", "ddd"]})
    assert sync.status_code == 200
    assert sync.json()["trader_live"] == ["AAA", "BBB", "CCC"]
    monkeypatch.setattr(
        "routes.bot.read_account_day_pnl",
        lambda: (-12.0, {"day_pnl": -12.0, "commissions": 1.0}),
    )
    pnl = client.get("/api/bot/pnl")
    assert pnl.status_code == 200
    assert pnl.json()["day_pnl"] == -12.0


def test_audit_and_advise_off(bot_iso):
    apply_patch({"level": 1}, desk=True)
    off = client.post("/api/bot/advise", json={"symbol": "AAPL"})
    assert off.status_code == 409
    assert off.json()["detail"]["reason"] == "BOT_ADVISE_OFF"
    audit = client.get("/api/bot/audit")
    assert audit.status_code == 200
    assert "entries" in audit.json()
