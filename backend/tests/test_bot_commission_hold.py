"""A Live commission read that fails holds new bot entries, never reads as $0 (#564).

Operator decision 2026-09-24: while the breakers' commission read fails on Live,
the day P&L is unknown and the bot sends no new entry until a read succeeds
again. Exits, cancels, flatten and kill are never held; Paper and Sim read no
commissions and are never held.
"""
from __future__ import annotations

import logging
import sqlite3

import pytest

from bot import day_pnl
from bot.actions import fire
from bot.breakers import poll_once
from bot.entry_rules import assert_entry_allowed
from bot.errors import BotError
from bot.session import get_session
from constants_bot import (
    BOT_COMMISSIONS_WARN_EVERY_SEC,
    BOT_KIND_SETUP_ENTRY,
    BOT_REASON_COMMISSIONS_UNKNOWN,
)
from execution.models import ExecutionReceipt
from sim.mode import reset_for_tests as reset_venue, set_venue
from tests.bot_helpers import ready_l2

LIVE_SUMMARY = {"RealizedPnL": -40.0, "UnrealizedPnL": -5.0}


def _ok(order_id: int = 42) -> ExecutionReceipt:
    return ExecutionReceipt(ok=True, execution_id="exec-1", operation="place", source="bot",
                            idempotency_key="k", order_id=order_id)


@pytest.fixture
def ledger(monkeypatch):
    """The execution ledger's commission read, switchable between a lock error and $1.50."""
    state = {"broken": True, "calls": 0}

    def read(*, since_ts: float) -> dict[str, float]:
        state["calls"] += 1
        if state["broken"]:
            raise sqlite3.OperationalError("database is locked")
        return {"ABCD": 1.5}

    monkeypatch.setattr("execution.store_facts.session_commission_by_symbol", read)
    monkeypatch.setattr("execution.closed_blotter.session_start_ts", lambda: 0.0)
    monkeypatch.setattr("ibkr.account.get_account_summary", lambda: dict(LIVE_SUMMARY))
    return state


@pytest.fixture
def clock():
    now = {"t": 1_790_000_000.0}
    day_pnl.reset_for_tests(lambda: now["t"])
    return now


@pytest.fixture
def places(monkeypatch):
    seen: list = []

    async def fake_execute(cmd, wait_ack=False):
        seen.append(cmd)
        return _ok(len(seen))

    monkeypatch.setattr("bot.actions.execute", fake_execute)
    monkeypatch.setattr("bot.risk.last_quote", lambda _s: {"price": 2.0})
    monkeypatch.setattr("bot.risk.top_of_book", lambda _s: (1.9, 2.1))
    return seen


def _warnings(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "bot.day_pnl" and r.levelno == logging.WARNING]


# -- the failure is stated, not $0 ----------------------------------------------
def test_a_failed_read_is_logged_and_the_day_pnl_is_unknown(ledger, clock, caplog):
    caplog.set_level(logging.INFO, logger="bot.day_pnl")
    pnl, meter = day_pnl.read_account_day_pnl()
    assert pnl is None
    assert meter["commissions_unknown"] is True and meter["commissions"] is None
    assert "database is locked" in meter["commissions_error"]
    assert meter["day_pnl"] is None and meter["day_pnl_before_commissions"] == -45.0
    assert day_pnl.session_commission_total() is None
    assert day_pnl.day_pnl_usd(dict(LIVE_SUMMARY)) is None     # never raw P&L with commissions as 0
    assert len(_warnings(caplog)) == 1

    # The breaker polls every second: the log does not flood.
    for _ in range(5):
        day_pnl.read_account_day_pnl()
    assert len(_warnings(caplog)) == 1
    clock["t"] += BOT_COMMISSIONS_WARN_EVERY_SEC
    day_pnl.read_account_day_pnl()
    assert len(_warnings(caplog)) == 2
    assert day_pnl.commission_hold()["since"] == 1_790_000_000.0   # held since the first failure


def test_a_successful_read_reports_commissions_known(ledger):
    ledger["broken"] = False
    pnl, meter = day_pnl.read_account_day_pnl()
    assert pnl == pytest.approx(-46.5)
    assert meter["commissions"] == 1.5 and meter["commissions_unknown"] is False
    assert meter["commissions_error"] is None and "day_pnl_before_commissions" not in meter
    assert day_pnl.commission_hold() is None


# -- the hold -------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_next_entry_is_refused_while_commissions_are_unknown(ledger, places):
    ready_l2(brain="brain-1", heartbeat=True)
    day_pnl.read_account_day_pnl()
    for kind in ("buy_market", "buy_limit_ask_offset"):
        with pytest.raises(BotError) as exc:
            await fire({"kind": kind, "symbol": "ABCD"}, brain_session_id="brain-1")
        assert exc.value.status_code == 409
        assert exc.value.reason == BOT_REASON_COMMISSIONS_UNKNOWN
        assert "database is locked" in exc.value.message
    assert places == []
    # The first-pullback bot's entry passes the same gate.
    with pytest.raises(BotError) as exc:
        assert_entry_allowed(BOT_KIND_SETUP_ENTRY)
    assert exc.value.reason == BOT_REASON_COMMISSIONS_UNKNOWN
    gate = {g["id"]: g for g in get_session()["gates"]}["commissions"]
    assert gate["ok"] is False and gate["stage"] == "fire"
    assert "database is locked" in gate["detail"]["error"]


@pytest.mark.asyncio
async def test_exits_cancels_and_flatten_are_never_held(ledger, places, monkeypatch):
    ready_l2(brain="brain-1", heartbeat=True)
    day_pnl.read_account_day_pnl()
    assert day_pnl.commission_hold() is not None
    monkeypatch.setattr("bot.actions._position_qty", lambda _s: 4.0)
    monkeypatch.setattr("ibkr.orders.open_orders", lambda: [{"symbol": "ABCD", "order_id": 9}])
    for kind in ("exit_pos", "exit_pos_pct", "sell_limit_bid_offset", "sell_pos_pct_ask", "cancel_symbol"):
        await fire({"kind": kind, "symbol": "ABCD"}, brain_session_id="brain-1")
    assert [c.side for c in places if c.operation == "place"] == ["SELL"] * 4
    assert [c.order_id for c in places if c.operation == "cancel"] == [9]

    flattens: list = []

    async def fake_door(cmd, wait_ack=False):
        flattens.append(cmd)
        return _ok(77)

    monkeypatch.setattr("execution.service.execute", fake_door)
    monkeypatch.setattr("execution.flatten_exit.resolve_flatten_marks", lambda _s: (1.9, 2.1, 2.0))
    from bot.flatten import place_close

    out = await place_close("ABCD", 4.0, "SELL")
    assert out["ok"] is True and [c.source for c in flattens] == ["flatten"]


@pytest.mark.asyncio
async def test_a_successful_read_releases_the_hold(ledger, places, caplog):
    caplog.set_level(logging.INFO, logger="bot.day_pnl")
    ready_l2(brain="brain-1", heartbeat=True)
    day_pnl.read_account_day_pnl()
    assert day_pnl.commission_hold() is not None
    ledger["broken"] = False
    pnl, _meter = day_pnl.read_account_day_pnl()
    assert pnl == pytest.approx(-46.5)
    assert day_pnl.commission_hold() is None
    assert any("released" in r.getMessage() for r in caplog.records if r.name == "bot.day_pnl")
    result = await fire({"kind": "buy_market", "symbol": "ABCD"}, brain_session_id="brain-1")
    assert result["ok"] is True and len(places) == 1
    assert {g["id"]: g for g in get_session()["gates"]}["commissions"]["ok"] is True


@pytest.mark.parametrize("venue", ["paper", "sim"])
def test_paper_and_sim_are_never_held(ledger, venue, monkeypatch):
    day_pnl.read_account_day_pnl()                 # a Live read failed earlier in the day
    assert day_pnl.commission_hold() is not None
    reset_venue()
    try:
        set_venue(venue)
        assert day_pnl.commission_hold() is None
        assert_entry_allowed(BOT_KIND_SETUP_ENTRY)
        assert_entry_allowed("buy_market")
        assert {g["id"]: g for g in get_session()["gates"]}["commissions"]["ok"] is True

        # The practice ledger's DayPnL has paid its fees: no commission read at all.
        monkeypatch.setattr("ibkr.account.get_account_summary",
                            lambda: {"practice": True, "DayPnL": -12.0, "RealizedPnL": -10.0})
        calls = ledger["calls"]
        pnl, meter = day_pnl.read_account_day_pnl()
        assert pnl == -12.0 and meter["commissions_unknown"] is False
        assert ledger["calls"] == calls
    finally:
        reset_venue()


# -- the breakers ----------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_breaker_still_trips_on_the_day_before_commissions(monkeypatch):
    """Commissions only make the day worse: a bound already past a breaker trips it."""
    tripped: list[str] = []

    async def fake_soft():
        tripped.append("soft")
        return {"tripped": "soft"}

    monkeypatch.setattr("bot.breakers.trip_soft", fake_soft)
    unknown = {"commissions_unknown": True, "day_pnl_before_commissions": -60.0}
    monkeypatch.setattr("bot.breakers.read_account_day_pnl", lambda: (None, dict(unknown)))
    assert (await poll_once())["tripped"] == "soft"

    unknown["day_pnl_before_commissions"] = -10.0
    assert await poll_once() is None
    unknown["day_pnl_before_commissions"] = None
    assert await poll_once() is None
    assert tripped == ["soft"]
