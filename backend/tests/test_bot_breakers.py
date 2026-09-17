"""-$50 / -$200 breakers -- flatten mocked, no live IBKR."""
from __future__ import annotations

import pytest

from bot.autonomy import apply_patch
from bot.breakers import poll_once, trip_hard, trip_soft
from bot.buy_lock import buy_blocked, day_lock_active
from bot.persist import load_session


@pytest.mark.asyncio
async def test_soft_breaker_flattens_and_latches(monkeypatch):
    apply_patch({"level": 2}, desk=True)
    from bot.persist import save_session

    row = load_session()
    row["bot_qty"] = {"ABCD": 1}
    row["working"] = [{"order_id": 1, "side": "BUY", "qty": 1, "price": 2.0}]
    save_session(row)
    flatten_calls = {"n": 0}

    async def fake_flatten():
        flatten_calls["n"] += 1
        return {"ok": True, "attempt": 1}

    monkeypatch.setattr("bot.breakers.flatten_account_with_retry", fake_flatten)
    result = await trip_soft()
    assert result["tripped"] == "soft"
    assert flatten_calls["n"] == 1
    row = load_session()
    assert row["level"] == 0
    assert row["soft_breaker_fired"] is True
    assert row["hard_lock_until_date"] is None
    assert row["bot_qty"] == {}
    assert row["working"] == []
    assert await poll_once(pnl=-60.0) is None


@pytest.mark.asyncio
async def test_hard_breaker_sets_day_lock(monkeypatch):
    apply_patch({"level": 2}, desk=True)

    async def fake_flatten():
        return {"ok": True, "attempt": 1}

    monkeypatch.setattr("bot.breakers.flatten_account_with_retry", fake_flatten)
    monkeypatch.setattr("bot.breakers.lock_until_date", lambda: "2026-09-18")
    result = await trip_hard()
    assert result["tripped"] == "hard"
    row = load_session()
    assert row["level"] == 0
    assert row["hard_lock_until_date"] == "2026-09-18"
    monkeypatch.setattr("bot.buy_lock.lock_is_active", lambda _d: True)
    assert day_lock_active() is True
    blocked, reason = buy_blocked("BUY", "manual")
    assert blocked is True
    assert reason == "BOT_DAY_LOCK"
    assert buy_blocked("BUY", "flatten")[0] is False
    assert buy_blocked("SELL", "manual")[0] is False


@pytest.mark.asyncio
async def test_poll_prefers_hard_when_both(monkeypatch):
    apply_patch({"level": 2}, desk=True)
    seen = []

    async def fake_hard():
        seen.append("hard")
        return {"tripped": "hard"}

    async def fake_soft():
        seen.append("soft")
        return {"tripped": "soft"}

    monkeypatch.setattr("bot.breakers.trip_hard", fake_hard)
    monkeypatch.setattr("bot.breakers.trip_soft", fake_soft)
    out = await poll_once(pnl=-250.0)
    assert out["tripped"] == "hard"
    assert seen == ["hard"]


@pytest.mark.asyncio
async def test_soft_reenable_allows_l2_again(monkeypatch):
    apply_patch({"level": 2}, desk=True)

    async def fake_flatten():
        return {"ok": True, "attempt": 1}

    monkeypatch.setattr("bot.breakers.flatten_account_with_retry", fake_flatten)
    await trip_soft()
    apply_patch({"reenable": True, "level": 2}, desk=True)
    row = load_session()
    assert row["soft_breaker_fired"] is False
    assert row["level"] == 2
    again = await poll_once(pnl=-60.0)
    assert again is not None
    assert again["tripped"] == "soft"


@pytest.mark.asyncio
async def test_flatten_retry_then_alert(monkeypatch):
    from bot.flatten import alert_flatten_failed, flatten_account_with_retry

    calls = {"n": 0}

    async def once():
        calls["n"] += 1
        return {"ok": False, "error": "nope", "results": []}

    monkeypatch.setattr("bot.flatten.flatten_account_once", once)
    last = await flatten_account_with_retry()
    assert last["ok"] is False
    assert calls["n"] == 2
    alerts = []
    monkeypatch.setattr("alerts.dispatch.dispatch_alert", lambda payload: alerts.append(payload))
    alert_flatten_failed({"error": "nope"})
    assert alerts
    assert "flatten failed" in alerts[0]["text"].lower()
