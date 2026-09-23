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


# ── practice venues (ADR 020): the ledger is local and closes at the last mark ──

@pytest.fixture
def practice_venue():
    from sim.mode import reset_for_tests, set_venue

    reset_for_tests()
    set_venue("paper")
    yield
    reset_for_tests()


@pytest.mark.asyncio
async def test_flatten_on_a_practice_venue_proceeds_with_the_gateway_dark(monkeypatch, practice_venue):
    from bot import flatten as flatten_mod

    order: list[str] = []

    async def fake_cancel() -> list[dict]:
        order.append("cancel")
        return []

    async def fake_place(symbol: str, qty: float, side: str) -> dict:
        order.append(f"place:{symbol}:{side}:{qty}")
        return {"ok": True, "order_id": 3}

    monkeypatch.setattr(flatten_mod, "_cancel_working", fake_cancel)
    monkeypatch.setattr(flatten_mod, "_place_close", fake_place)
    monkeypatch.setattr("ibkr.client.is_connected", lambda: False)
    # The practice broker fills a protective close at placement: held before, flat after.
    reads = iter([[{"symbol": "IMCC", "qty": 7}], []])
    monkeypatch.setattr("ibkr.account.get_positions", lambda: next(reads))

    result = await flatten_mod.flatten_account_once()

    assert result["ok"] is True
    assert order == ["cancel", "place:IMCC:SELL:7.0"]


@pytest.mark.asyncio
async def test_flatten_on_live_still_refuses_with_the_gateway_dark(monkeypatch):
    from bot import flatten as flatten_mod
    from sim.mode import reset_for_tests, set_venue

    reset_for_tests()
    set_venue("live")
    monkeypatch.setattr("ibkr.client.is_connected", lambda: False)
    try:
        result = await flatten_mod.flatten_account_once()
    finally:
        reset_for_tests()
    assert result["ok"] is False and "not connected" in result["error"]


@pytest.mark.asyncio
async def test_place_close_on_a_practice_venue_is_a_market_close_at_any_hour(monkeypatch, practice_venue):
    from bot import flatten as flatten_mod
    from execution import flatten_exit as fe

    captured: dict = {}

    async def fake_execute(cmd, wait_ack=False):
        captured["cmd"] = cmd
        return _Receipt()

    def no_marks(_symbol):
        raise AssertionError("a practice close never asks the live feed for a mark")

    monkeypatch.setattr(fe, "flatten_needs_extended_hours", lambda now=None: True)  # a weekend
    monkeypatch.setattr(fe, "resolve_flatten_marks", no_marks)
    monkeypatch.setattr("execution.service.execute", fake_execute)

    result = await flatten_mod._place_close("IMCC", 7, "SELL")
    assert result["ok"] is True
    cmd = captured["cmd"]
    assert (cmd.order_type, cmd.outside_rth, cmd.limit_price, cmd.source) == ("MKT", False, None, "flatten")


@pytest.mark.asyncio
async def test_a_close_that_sent_less_than_the_position_is_a_failure(monkeypatch):
    """QA R6: a KILL must never report success while shares remain."""
    from bot import flatten as flatten_mod

    async def fake_cancel() -> list[dict]:
        return []

    async def short_place(symbol: str, qty: float, side: str) -> dict:
        return {"ok": True, "order_id": 8, "sent_qty": 1.0}

    monkeypatch.setattr(flatten_mod, "_cancel_working", fake_cancel)
    monkeypatch.setattr(flatten_mod, "_place_close", short_place)
    monkeypatch.setattr("ibkr.client.is_connected", lambda: True)
    monkeypatch.setattr("sim.mode.is_practice_venue", lambda: False)
    monkeypatch.setattr("ibkr.account.get_positions", lambda: [{"symbol": "GRML", "qty": 2}])

    result = await flatten_mod.flatten_account_once()

    assert result["ok"] is False
    close = result["results"][0]["close"]
    assert close["reason_code"] == "FLATTEN_PARTIAL"
    assert "sent 1 of 2 shares" in close["error"]


@pytest.mark.asyncio
async def test_practice_flatten_rereads_positions_and_fails_when_shares_remain(monkeypatch):
    from bot import flatten as flatten_mod

    async def fake_cancel() -> list[dict]:
        return []

    async def whole_place(symbol: str, qty: float, side: str) -> dict:
        return {"ok": True, "order_id": 9, "sent_qty": qty}

    reads = iter([[{"symbol": "GRML", "qty": 2}], [{"symbol": "GRML", "qty": 1}]])
    monkeypatch.setattr(flatten_mod, "_cancel_working", fake_cancel)
    monkeypatch.setattr(flatten_mod, "_place_close", whole_place)
    monkeypatch.setattr("sim.mode.is_practice_venue", lambda: True)
    monkeypatch.setattr("ibkr.account.get_positions", lambda: next(reads))

    result = await flatten_mod.flatten_account_once()

    assert result["ok"] is False
    assert result["left_open"] == ["GRML 1"]
    assert "still open" in result["error"]


@pytest.mark.asyncio
async def test_practice_flatten_that_leaves_nothing_open_succeeds(monkeypatch):
    from bot import flatten as flatten_mod

    async def fake_cancel() -> list[dict]:
        return []

    async def whole_place(symbol: str, qty: float, side: str) -> dict:
        return {"ok": True, "order_id": 10, "sent_qty": qty}

    reads = iter([[{"symbol": "GRML", "qty": 2}], []])
    monkeypatch.setattr(flatten_mod, "_cancel_working", fake_cancel)
    monkeypatch.setattr(flatten_mod, "_place_close", whole_place)
    monkeypatch.setattr("sim.mode.is_practice_venue", lambda: True)
    monkeypatch.setattr("ibkr.account.get_positions", lambda: next(reads))

    result = await flatten_mod.flatten_account_once()

    assert result["ok"] is True
    assert "left_open" not in result


@pytest.mark.asyncio
async def test_practice_flatten_that_cannot_reread_positions_is_not_reported_flat(monkeypatch):
    """The re-read is the proof: when it fails, the closes were sent but flat
    is unproven -- never ``ok`` (it used to read as "nothing left open")."""
    from bot import flatten as flatten_mod
    from ibkr.errors import IbkrAccountError

    async def fake_cancel() -> list[dict]:
        return []

    async def whole_place(symbol: str, qty: float, side: str) -> dict:
        return {"ok": True, "order_id": 11, "sent_qty": qty}

    reads = iter([[{"symbol": "GRML", "qty": 2}], IbkrAccountError("ledger unreadable")])

    def get_positions():
        item = next(reads)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(flatten_mod, "_cancel_working", fake_cancel)
    monkeypatch.setattr(flatten_mod, "_place_close", whole_place)
    monkeypatch.setattr("sim.mode.is_practice_venue", lambda: True)
    monkeypatch.setattr("ibkr.account.get_positions", get_positions)

    result = await flatten_mod.flatten_account_once()

    assert result["ok"] is False
    assert "could not be re-read" in result["error"]
    assert "left_open" not in result
