"""flatten_account_once -- cancel leftover working, then place closes."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_flatten_cancels_working_before_placing_closes(monkeypatch):
    from bot import flatten as flatten_mod

    order: list[str] = []

    async def fake_cancel() -> list[dict]:
        order.append("cancel")
        return [{"ok": True, "order_id": 1}]

    async def fake_place(symbol: str, qty: float, side: str) -> dict:
        order.append(f"place:{symbol}:{side}:{qty}")
        return {"ok": True, "order_id": 99}

    monkeypatch.setattr(flatten_mod, "_cancel_working", fake_cancel)
    monkeypatch.setattr(flatten_mod, "_place_close", fake_place)

    monkeypatch.setattr("ibkr.client.is_connected", lambda: True)
    monkeypatch.setattr(
        "ibkr.account.get_positions",
        lambda: [{"symbol": "AAPL", "qty": 10}],
    )

    result = await flatten_mod.flatten_account_once()

    assert result["ok"] is True
    assert order == ["cancel", "place:AAPL:SELL:10.0"]
    assert result["cancels"] == [{"ok": True, "order_id": 1}]
    assert result["results"][0]["close"]["order_id"] == 99


@pytest.mark.asyncio
async def test_flatten_still_places_closes_when_cancel_fails(monkeypatch):
    from bot import flatten as flatten_mod

    async def fake_cancel() -> list[dict]:
        return [{"ok": False, "error": "busy"}]

    async def fake_place(symbol: str, qty: float, side: str) -> dict:
        return {"ok": True, "order_id": 7}

    monkeypatch.setattr(flatten_mod, "_cancel_working", fake_cancel)
    monkeypatch.setattr(flatten_mod, "_place_close", fake_place)
    monkeypatch.setattr("ibkr.client.is_connected", lambda: True)
    monkeypatch.setattr(
        "ibkr.account.get_positions",
        lambda: [{"symbol": "MSFT", "qty": -4}],
    )

    result = await flatten_mod.flatten_account_once()

    assert result["ok"] is True
    assert result["results"][0]["side"] == "BUY"
    assert result["cancels"][0]["ok"] is False


class _Receipt:
    def legacy_place_dict(self):
        return {"ok": True, "order_id": 5}


@pytest.mark.asyncio
async def test_place_close_rth_stays_market(monkeypatch):
    from bot import flatten as flatten_mod
    from execution import flatten_exit as fe

    captured: dict = {}

    async def fake_execute(cmd, wait_ack=False):
        captured["cmd"] = cmd
        return _Receipt()

    monkeypatch.setattr(fe, "flatten_needs_extended_hours", lambda now=None: False)
    monkeypatch.setattr(fe, "resolve_flatten_marks", lambda _symbol: (10.0, 10.1, 10.05))
    monkeypatch.setattr("execution.service.execute", fake_execute)

    result = await flatten_mod._place_close("AAPL", 10, "SELL")
    assert result["ok"] is True
    cmd = captured["cmd"]
    assert cmd.order_type == "MKT"
    assert cmd.outside_rth is False
    assert cmd.limit_price is None
    assert cmd.source == "flatten"


@pytest.mark.asyncio
async def test_place_close_after_hours_uses_eh_lmt(monkeypatch):
    from bot import flatten as flatten_mod
    from execution import flatten_exit as fe

    captured: dict = {}

    async def fake_execute(cmd, wait_ack=False):
        captured["cmd"] = cmd
        return _Receipt()

    monkeypatch.setattr(fe, "flatten_needs_extended_hours", lambda now=None: True)
    monkeypatch.setattr(fe, "resolve_flatten_marks", lambda _symbol: (10.0, 10.1, 10.05))
    monkeypatch.setattr("execution.service.execute", fake_execute)

    result = await flatten_mod._place_close("AAPL", 10, "SELL")
    assert result["ok"] is True
    cmd = captured["cmd"]
    assert cmd.order_type == "LMT"
    assert cmd.outside_rth is True
    assert cmd.limit_price == 10.0
    assert cmd.side == "SELL"


@pytest.mark.asyncio
async def test_place_close_after_hours_without_mark_fails_loud(monkeypatch):
    from bot import flatten as flatten_mod
    from execution import flatten_exit as fe

    called = {"execute": False}

    async def fake_execute(_cmd, wait_ack=False):
        called["execute"] = True
        return _Receipt()

    monkeypatch.setattr(fe, "flatten_needs_extended_hours", lambda now=None: True)
    monkeypatch.setattr(fe, "resolve_flatten_marks", lambda _symbol: (None, None, None))
    monkeypatch.setattr("execution.service.execute", fake_execute)

    result = await flatten_mod._place_close("AAPL", 10, "SELL")
    assert result["ok"] is False
    assert result["reason_code"] == "FLATTEN_EH_NO_MARK"
    assert called["execute"] is False
