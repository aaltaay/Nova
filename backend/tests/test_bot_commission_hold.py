"""A Live commission read that fails is a stated hold, never read as $0 (#564).

Operator decision 2026-09-24: while the commission read fails on Live, the bot
sent no new entry until a read succeeded again -- the unreadable file is the
execution ledger every order is written to. Exits, cancels, flatten and kill
are never held; Paper and Sim read no commissions and are never held. ADR 072
retired the strategy bot's entry rules that read the hold; the hold stays current.

Spec D (2026-09-30): the day P&L meter reads IBKR's realized + unrealized P&L,
which already counts every commission, so a failed commission read no longer
makes the day P&L unknown. Since ADR 056 nothing compares it; the commission
loop (``bot.loops.commission_loop``) keeps the hold current.
"""
from __future__ import annotations

import logging
import sqlite3

import pytest

from bot import day_pnl
from bot.actions import fire
from bot.errors import BotError
from constants_bot import (
    BOT_COMMISSIONS_WARN_EVERY_SEC,
    BOT_REASON_LIVE_NOT_BUILT,
)
from execution.models import ExecutionReceipt
from sim.mode import reset_for_tests as reset_venue, set_venue
from tests.bot_helpers import set_level

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
def test_a_failed_read_is_logged_and_held_and_the_day_pnl_stays_ibkrs(ledger, clock, caplog):
    caplog.set_level(logging.INFO, logger="bot.day_pnl")
    pnl, meter = day_pnl.read_account_day_pnl()
    assert pnl == -45.0                                         # IBKR's figure: commissions already inside
    assert meter["commissions_unknown"] is True and meter["commissions"] is None
    assert "database is locked" in meter["commissions_error"]
    assert meter["day_pnl"] == -45.0 and meter["commissions_in_figure"] is True
    assert day_pnl.session_commission_total() is None
    assert day_pnl.day_pnl_usd(dict(LIVE_SUMMARY)) == -45.0
    assert len(_warnings(caplog)) == 1

    # The commission loop reads every second: the log does not flood.
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
    assert pnl == pytest.approx(-45.0)                         # never less $1.50 again (spec D)
    assert meter["commissions"] == 1.5 and meter["commissions_unknown"] is False
    assert meter["commissions_error"] is None
    assert day_pnl.commission_hold() is None


# -- the hold -------------------------------------------------------------------
@pytest.mark.asyncio
async def test_on_live_the_bot_api_refuses_before_any_hold(ledger, places):
    """The bot API refuses Live before anything else (ADR 042 J), so nothing is placed while the hold stands."""
    set_level(2)                                                       # Live's own dial
    day_pnl.read_account_day_pnl()
    assert day_pnl.commission_hold() is not None
    for kind in ("buy_market", "buy_limit_ask_offset"):
        with pytest.raises(BotError) as exc:
            await fire({"kind": kind, "symbol": "ABCD"}, brain_session_id="brain-1")
        assert exc.value.reason == BOT_REASON_LIVE_NOT_BUILT
    assert places == []


@pytest.mark.asyncio
async def test_exits_cancels_and_flatten_are_never_held(ledger, places, monkeypatch):
    day_pnl.read_account_day_pnl()
    assert day_pnl.commission_hold() is not None                      # a Live read failed
    flattens: list = []

    async def fake_door(cmd, wait_ack=False):
        flattens.append(cmd)
        return _ok(77)

    monkeypatch.setattr("execution.service.execute", fake_door)
    monkeypatch.setattr("execution.flatten_exit.resolve_flatten_marks", lambda _s: (1.9, 2.1, 2.0))
    from bot.flatten import place_close

    out = await place_close("ABCD", 4.0, "SELL")                      # the protective flatten, on Live
    assert out["ok"] is True and [c.source for c in flattens] == ["flatten"]


@pytest.mark.asyncio
async def test_a_successful_read_releases_the_hold(ledger, caplog):
    caplog.set_level(logging.INFO, logger="bot.day_pnl")
    day_pnl.read_account_day_pnl()
    assert day_pnl.commission_hold() is not None
    ledger["broken"] = False
    pnl, _meter = day_pnl.read_account_day_pnl()
    assert pnl == pytest.approx(-45.0)
    assert day_pnl.commission_hold() is None
    assert any("released" in r.getMessage() for r in caplog.records if r.name == "bot.day_pnl")


@pytest.mark.parametrize("venue", ["paper", "sim"])
def test_paper_and_sim_are_never_held(ledger, venue, monkeypatch):
    day_pnl.read_account_day_pnl()                 # a Live read failed earlier in the day
    assert day_pnl.commission_hold() is not None
    reset_venue()
    try:
        set_venue(venue)
        assert day_pnl.commission_hold() is None

        # The practice ledger's DayPnL has paid its fees: no commission read at all.
        monkeypatch.setattr("ibkr.account.get_account_summary",
                            lambda: {"practice": True, "DayPnL": -12.0, "RealizedPnL": -10.0})
        if venue == "sim":       # at the live edge: a Sim replay compares nothing (spec D)
            monkeypatch.setattr("sim.session_clock.live_edge", lambda: True)
        calls = ledger["calls"]
        pnl, meter = day_pnl.read_account_day_pnl()
        assert pnl == -12.0 and meter["commissions_unknown"] is False
        assert ledger["calls"] == calls
    finally:
        reset_venue()
