"""A practice send answers when the venue answers (operator report, 2026-09-24).

"This is extremely dangerous. Why are things not getting sent fast enough?"
The Paper ticket read "Placing..." for five seconds after its order had
filled. The practice broker settles a place inside the send; its notice of a
fill at placement reached a watch the send then replaced, and a resting order
sent no notice at all, so the execution door's acknowledgment wait found
nothing and ran out its full ``EXECUTION_ACK_WAIT_SEC``: 21 of 23 Paper orders
that day answered in 5.1 s while their fills landed in under 150 ms.

These run the real door (``execution.service.execute``) on a Paper broker and
fail the moment the acknowledgment wait has to wait at all.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from execution import inflight, service, store, telemetry
from execution.models import ExecutionCommand
from ibkr import safety as _safety
from practice import broker as practice_broker
from practice import order_rules
from practice.broker import for_venue, reset_for_tests
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue

NOW = 1_700_000_000.0


class FakeLive:
    """A live market that prices IMCC at 9.98 x 10.02 and never prints on its own."""

    def reference(self, symbol: str) -> Reference:
        return Reference(10.0, 9.98, 10.02, live=True) if symbol == "IMCC" else Reference(None, live=True)

    def admission(self, symbol: str):
        return (True, "OK", None) if symbol == "IMCC" else (False, "dark", "PRACTICE_NO_LIVE_PRINT")

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return NOW

    def session_close_ts(self, ts: float) -> float:
        return ts + 86_400


@pytest.fixture
def paper(monkeypatch):
    reset_venue()
    reset_for_tests()
    service.reset_for_tests()
    store.init_db()
    monkeypatch.setattr(practice_broker, "LiveReference", FakeLive)
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    waits: list[bool] = []
    real_wait = telemetry.OrderWatch.wait_ack

    async def spy_wait(self, timeout_sec: float) -> bool:
        # True: the venue's answer was not on the watch, so the door would
        # have waited up to ``timeout_sec`` for a callback that never comes.
        waits.append(self.ack_ns is None)
        return await real_wait(self, 0.01)

    monkeypatch.setattr(telemetry.OrderWatch, "wait_ack", spy_wait)
    yield SimpleNamespace(broker=for_venue("paper"), waits=waits)
    service.reset_for_tests()
    inflight.reset_for_tests()
    reset_for_tests()
    reset_venue()


def _limit_buy(key: str, price: float) -> ExecutionCommand:
    return ExecutionCommand(
        operation="place", idempotency_key=key, source="manual",
        symbol="IMCC", side="BUY", qty=100, order_type="LMT", limit_price=price,
        skip_risk=True,
    )


@pytest.mark.asyncio
async def test_a_fill_at_placement_answers_without_waiting(paper) -> None:
    receipt = await service.execute(_limit_buy("fill-now", 10.05))

    assert receipt.ok is True, receipt.error
    assert receipt.broker_status == "Filled"
    assert paper.waits == [False]
    assert receipt.timings.broker_ack_ns is not None
    assert receipt.timings.filled_ns is not None
    row = store.get_by_id(receipt.execution_id)
    assert (row["status"], row["broker_status"]) == ("filled", "Filled")
    assert row["broker_ack_ns"] is not None


@pytest.mark.asyncio
async def test_a_resting_order_answers_submitted_without_waiting(paper) -> None:
    receipt = await service.execute(_limit_buy("rest", 9.50))

    assert receipt.ok is True, receipt.error
    assert receipt.broker_status == "Submitted"
    assert paper.waits == [False]
    assert receipt.timings.broker_ack_ns is not None
    assert receipt.timings.filled_ns is None
    assert store.get_by_id(receipt.execution_id)["status"] == "acked"


@pytest.mark.asyncio
async def test_a_price_replace_answers_without_waiting(paper) -> None:
    placed = await service.execute(_limit_buy("rest-then-move", 9.50))
    moved = await service.execute(ExecutionCommand(
        operation="replace", idempotency_key="move", source="manual",
        order_id=placed.order_id, limit_price=9.60, skip_risk=True,
    ))

    assert moved.ok is True, moved.error
    assert moved.broker_status == "Submitted"
    assert paper.waits == [False, False]
    assert moved.timings.broker_ack_ns is not None


@pytest.mark.asyncio
async def test_an_order_the_venue_cancels_at_the_fill_is_refused_in_its_words(paper, monkeypatch) -> None:
    """It used to wait 5 s and then read as placed ("sent"), with nothing working."""
    monkeypatch.setattr(
        order_rules, "fill_refusal",
        lambda *_a, **_k: ("Not enough buying power at the fill", "PRACTICE_BUYING_POWER"),
    )

    receipt = await service.execute(_limit_buy("cancelled-at-fill", 10.05))

    assert receipt.ok is False
    assert receipt.reason_code == "PRACTICE_BUYING_POWER"
    assert receipt.error == "Not enough buying power at the fill"
    assert receipt.broker_status == "Cancelled"
    assert receipt.order_id is not None
    assert paper.waits == []
    row = store.get_by_id(receipt.execution_id)
    assert (row["status"], row["reason_code"]) == ("failed", "PRACTICE_BUYING_POWER")
    assert inflight.committed_qty("IMCC", "BUY") == 0.0
    assert paper.broker.working_orders() == []
