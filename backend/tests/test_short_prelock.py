"""What the execution door reads before its lock for a short (ADR 048 decision 2, gap 4).

Nothing under the lock waits on IBKR. Before it, a bot's short may wait a moment for IBKR's what-if
margin; the ticket's short never waits -- the what-if is asked in the background and the order is
judged by the answer kept for the stock, else the published rules. A Live short with
``IBKR_SHORT_ENABLED`` off gathers nothing: the door refuses it at once.
"""
from __future__ import annotations

import asyncio

import pytest

from constants_shorts import SHORT_WHATIF_BOT_WAIT_SEC
from execution.models import ExecutionCommand
from short_sale import prelock, whatif


def _short(**kw) -> ExecutionCommand:
    base = dict(operation="bracket", idempotency_key="pre", source="manual", symbol="FADE", side="SELL", qty=500,
                order_type="LMT", limit_price=4.0, entry_price=4.0, stop_price=4.2, target_price=3.6,
                short_entry=True)
    base.update(kw)
    return ExecutionCommand(**base)


@pytest.fixture
def ibkr(monkeypatch):
    calls = {"asked": [], "requested": [], "gathered": []}

    async def ask(symbol, side, qty, price, *, timeout):
        calls["asked"].append((symbol, side, qty, price, timeout))

    monkeypatch.setattr("ibkr.client.is_ready", lambda: True)
    monkeypatch.setattr(whatif, "fresh", lambda symbol, side: False)
    monkeypatch.setattr(whatif, "ask", ask)
    monkeypatch.setattr(whatif, "request", lambda *a: calls["requested"].append(a))
    monkeypatch.setattr(prelock, "gather", lambda symbol, venue: calls["gathered"].append((symbol, venue)) or "facts")
    monkeypatch.setattr(prelock, "_venue", lambda: "paper")
    return calls


def test_a_bots_short_waits_a_moment_for_ibkrs_margin(ibkr) -> None:
    assert asyncio.run(prelock.facts_for(_short(source="bot"))) == "facts"
    assert ibkr["asked"] == [("FADE", "SELL", 500, 4.0, SHORT_WHATIF_BOT_WAIT_SEC)]
    assert ibkr["requested"] == [] and ibkr["gathered"] == [("FADE", "paper")]


def test_the_tickets_short_never_waits(ibkr) -> None:
    assert asyncio.run(prelock.facts_for(_short(client_timing={"click_wall_ms": 1}))) == "facts"
    assert ibkr["asked"] == [] and ibkr["requested"] == [("FADE", "SELL", 500, 4.0)]


def test_a_practice_buy_only_warms_the_figure_and_a_live_short_without_the_key_reads_nothing(ibkr, monkeypatch):
    buy = ExecutionCommand(operation="place", idempotency_key="buy", source="manual", symbol="FADE", side="BUY",
                           qty=100, order_type="LMT", limit_price=4.0)
    assert asyncio.run(prelock.facts_for(buy)) is None
    assert ibkr["requested"] == [("FADE", "BUY", 100, 4.0)] and ibkr["gathered"] == []

    monkeypatch.setattr(prelock, "_venue", lambda: "live")
    monkeypatch.setattr("ibkr.safety.short_enabled", lambda: False)
    assert asyncio.run(prelock.facts_for(_short(source="bot"))) is None
    assert ibkr["asked"] == [] and ibkr["gathered"] == []
