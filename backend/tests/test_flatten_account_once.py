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
