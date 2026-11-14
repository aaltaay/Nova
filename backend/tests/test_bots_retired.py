"""The bots are retired (ADR 072): the strategies only watch, and the door refuses a retired sender's new order.

Nova has three traders -- you, Claude and the brain. A strategy bot, Auto-entry, Approve, Nova's exit, the Live Trader
and the bot API send no new order; a close, KILL and a cancel of what they still hold always go. Claude's Paper seat
(``origin="claude"``) still sends through the same door. The door test runs the real ``execution.service.execute`` on
Paper with the real ledger; only the live feed's edge is faked.
"""
from __future__ import annotations

import asyncio

import pytest

from bot import setup_levels
from bot.errors import BotError
from constants_bot import BOT_LEVEL_EYES, BOT_REASON_STRATEGIES_WATCH, BOT_SCANNER_SETUPS
from constants_nova_os import BOTS_RETIRED_CODE, RETIRED_SENDER_ORIGINS
from execution import inflight, retired_senders, store, telemetry, venue_door
from execution.models import ExecutionCommand
from execution.service import execute
from practice import broker as practice_broker
from practice.broker import reset_for_tests as reset_brokers
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue
from sim.mode import set_venue

NOW = 1_700_000_000.0


def _cmd(**kw) -> ExecutionCommand:
    base = {"operation": "place", "idempotency_key": "k", "source": "bot", "symbol": "ABCD", "side": "BUY",
            "qty": 10, "order_type": "LMT", "limit_price": 5.0}
    base.update(kw)
    return ExecutionCommand(**base)


@pytest.mark.parametrize("origin", RETIRED_SENDER_ORIGINS)
def test_every_retired_sender_is_refused_in_words(origin):
    why = retired_senders.refusal(_cmd(origin=origin))
    assert why and "ADR 072" in why and "you, Claude" in why


@pytest.mark.parametrize("operation", ["place", "bracket", "replace", "exit_oco"])
def test_a_bot_sourced_order_without_an_origin_is_refused(operation):
    assert retired_senders.refusal(_cmd(operation=operation, origin=None))


def test_the_bot_api_says_it_waits_for_the_brain():
    assert "brain's door" in retired_senders.refusal(_cmd(origin="bot_api"))


def test_claude_still_sends_through_the_door():
    assert retired_senders.refusal(_cmd(origin="claude")) is None
    assert retired_senders.refusal(_cmd(operation="bracket", origin="claude")) is None


@pytest.mark.parametrize("source", ["flatten", "kill", "cancel_working"])
def test_a_close_or_kill_of_what_a_bot_holds_still_goes(source):
    assert retired_senders.refusal(_cmd(source=source, origin="bot", side="SELL")) is None


def test_a_cancel_of_a_bot_order_still_goes():
    assert retired_senders.refusal(_cmd(operation="cancel", origin="bot", order_id=7)) is None


def test_your_own_ticket_is_not_touched():
    assert retired_senders.refusal(_cmd(source="manual", origin=None)) is None
    assert retired_senders.refusal(_cmd(source="manual", origin="ticket_flatten")) is None


def test_every_strategy_reads_eyes_and_none_trades():
    row = {"levels": {sid: 2 for sid in BOT_SCANNER_SETUPS}, "chosen": BOT_SCANNER_SETUPS[0]}
    assert setup_levels.own_levels(row) == {sid: BOT_LEVEL_EYES for sid in BOT_SCANNER_SETUPS}
    assert setup_levels.effective(row) == setup_levels.own_levels(row)
    assert setup_levels.at_strategy(row) == []


def test_a_level_cannot_be_set_any_more():
    with pytest.raises(BotError) as raised:
        setup_levels.apply({}, {BOT_SCANNER_SETUPS[0]: 2})
    assert raised.value.reason == BOT_REASON_STRATEGIES_WATCH
    assert setup_levels.apply({}, {}) == {}


class FakeLive:
    def reference(self, symbol: str) -> Reference:
        return Reference(5.0, 4.99, 5.01, live=True)

    def admission(self, symbol: str):
        return True, "OK", None

    def prints_between(self, symbol, after_ts, through_ts):
        return []

    def now_ts(self) -> float:
        return NOW


@pytest.fixture
def paper(monkeypatch, tmp_path):
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    store.init_db()
    telemetry.reset_for_tests()
    inflight.reset_for_tests()
    reset_venue()
    reset_brokers()
    monkeypatch.setattr(practice_broker, "LiveReference", FakeLive)
    set_venue("paper")
    yield
    inflight.reset_for_tests()
    telemetry.reset_for_tests()
    reset_brokers()
    reset_venue()


def test_the_door_refuses_a_strategy_bot_buy_and_records_why(paper):
    receipt = asyncio.run(execute(_cmd(idempotency_key="bot:buy:1", origin="bot")))
    assert receipt.ok is False
    assert receipt.reason_code == BOTS_RETIRED_CODE
    assert "retired" in (receipt.error or "")
    row = store.get_by_id(receipt.execution_id)
    assert row is not None and row["status"] == "rejected"
    assert practice_broker.for_venue("paper").working_orders() == []


def test_the_door_refuses_the_live_trader_even_with_a_target_venue(paper):
    receipt = asyncio.run(execute(_cmd(idempotency_key="lt:buy:1", origin="live_trader", target_venue="paper")))
    assert receipt.ok is False
    assert receipt.reason_code in (BOTS_RETIRED_CODE, venue_door.TARGET_REFUSED)
