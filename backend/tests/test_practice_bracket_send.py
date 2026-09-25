"""A bracket through the execution door on Paper (#606 step 1).

The manual ticket's default take-profit / stop-loss goes out as one bracket
command (``routes.trading_execution``); on Paper and Sim it used to be refused
``SIM_NO_BRACKET``. These run the real door (``execution.service.execute``)
on a Paper broker: the send answers when the venue answers (no acknowledgment
wait), the receipt and the execution row carry the three order ids, the watches
are Live's, and a list of working orders can be cancelled one by one without a
false failure.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from constants_practice import PRACTICE_NO_SHORTS_CODE
from execution import inflight, service, store, telemetry
from execution.models import ExecutionCommand
from ibkr import orders as ibkr_orders
from ibkr import safety as _safety
from practice import broker as practice_broker
from practice import order_rules
from practice.broker import for_venue, reset_for_tests
from routes import trading_execution as route
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
        # True: the venue's answer was not on the watch, so the door would have waited.
        waits.append(self.ack_ns is None)
        return await real_wait(self, 0.01)

    monkeypatch.setattr(telemetry.OrderWatch, "wait_ack", spy_wait)
    yield SimpleNamespace(broker=for_venue("paper"), waits=waits)
    service.reset_for_tests()
    inflight.reset_for_tests()
    reset_for_tests()
    reset_venue()


def _bracket(key: str, entry: float = 9.90, **kw) -> ExecutionCommand:
    base = dict(
        operation="bracket", idempotency_key=key, source="manual", symbol="IMCC", side="BUY",
        qty=100, order_type="LMT", limit_price=entry, entry_price=entry, target_price=10.50,
        stop_price=9.50, skip_risk=True,
    )
    base.update(kw)
    return ExecutionCommand(**base)


@pytest.mark.asyncio
async def test_a_bracket_answers_at_once_with_its_three_order_ids(paper) -> None:
    receipt = await service.execute(_bracket("rest"))

    assert receipt.ok is True, receipt.error
    assert (receipt.mode, receipt.broker_status) == ("paper", "Submitted")
    assert paper.waits == [False]
    assert receipt.timings.broker_ack_ns is not None and receipt.timings.filled_ns is None
    p = receipt.parent_order_id
    assert (receipt.order_id, receipt.target_order_id, receipt.stop_order_id) == (p, p + 1, p + 2)
    legacy = receipt.legacy_place_dict()
    assert (legacy["parent_order_id"], legacy["target_order_id"], legacy["stop_order_id"]) == (p, p + 1, p + 2)
    row = store.get_by_id(receipt.execution_id)
    assert (row["status"], row["order_id"], row["parent_order_id"], row["target_order_id"], row["stop_order_id"]) == (
        "acked", p, p, p + 1, p + 2,
    )
    entry = telemetry.watch_order(p)
    assert (entry.leg_role, entry.aggregate_eligible, entry.side, entry.ack_status) == ("parent", True, "BUY", "Submitted")
    for role, oid in (("target", p + 1), ("stop", p + 2)):
        leg = telemetry.watch_order(oid)
        assert (leg.leg_role, leg.aggregate_eligible, leg.side, leg.execution_id) == (
            role, False, "SELL", receipt.execution_id,
        )


@pytest.mark.asyncio
async def test_a_marketable_bracket_reads_filled_and_its_exits_work(paper) -> None:
    receipt = await service.execute(_bracket("fill-now", entry=10.05))

    assert (receipt.ok, receipt.broker_status) == (True, "Filled")
    assert paper.waits == [False]
    assert receipt.timings.filled_ns is not None
    assert store.get_by_id(receipt.execution_id)["status"] == "filled"
    assert {r["order_id"]: r["status"] for r in paper.broker.working_orders()} == {
        receipt.target_order_id: "Submitted", receipt.stop_order_id: "Submitted",
    }


@pytest.mark.asyncio
async def test_an_entry_the_venue_cancels_at_the_fill_is_refused_in_its_words(paper, monkeypatch) -> None:
    monkeypatch.setattr(
        order_rules, "fill_refusal",
        lambda *_a, **_k: ("Not enough buying power at the fill", "PRACTICE_BUYING_POWER"),
    )

    receipt = await service.execute(_bracket("cancelled-at-fill", entry=10.05))

    assert (receipt.ok, receipt.reason_code, receipt.broker_status) == (False, "PRACTICE_BUYING_POWER", "Cancelled")
    assert receipt.error == "Not enough buying power at the fill"
    assert receipt.parent_order_id is not None and receipt.order_id == receipt.parent_order_id
    assert paper.waits == []
    row = store.get_by_id(receipt.execution_id)
    assert (row["status"], row["reason_code"], row["parent_order_id"]) == (
        "failed", "PRACTICE_BUYING_POWER", receipt.parent_order_id,
    )
    assert paper.broker.working_orders() == []  # its exits went with it


@pytest.mark.asyncio
async def test_a_short_bracket_is_refused_no_shorts(paper) -> None:
    receipt = await service.execute(_bracket(
        "short", entry=10.0, side="SELL", short_entry=True, target_price=9.5, stop_price=10.5,
    ))

    assert (receipt.ok, receipt.reason_code) == (False, PRACTICE_NO_SHORTS_CODE)
    assert paper.broker.working_orders() == [] and paper.broker.ledger.events == []


@pytest.mark.asyncio
async def test_the_tickets_default_legs_place_a_practice_bracket(paper) -> None:
    req = route.OrderRequest(
        symbol="IMCC", side="BUY", qty=100, order_type="LMT", limit_price=9.90,
        take_profit_price=10.50, stop_loss_price=9.50,
    )
    receipt = await service.execute(route._manual_order_command(req, "ticket-legs", None, 0))

    assert (receipt.ok, receipt.operation, receipt.broker_status) == (True, "bracket", "Submitted")
    assert sorted((r["leg_role"], r["status"]) for r in paper.broker.working_orders()) == [
        ("parent", "Submitted"), ("stop", "PreSubmitted"), ("target", "PreSubmitted"),
    ]


@pytest.mark.asyncio
async def test_cancelling_every_working_order_one_by_one_reports_no_false_failure(paper) -> None:
    """KILL's sweep, the account flatten and cancel-all cancel a snapshot of working orders in turn."""
    receipt = await service.execute(_bracket("rest"))
    p = receipt.parent_order_id
    snapshot = [int(row["order_id"]) for row in ibkr_orders.open_orders()]
    assert snapshot == [p, p + 1, p + 2]

    outcomes = []
    for oid in snapshot:  # the entry's cancel takes its exits along before their turn comes
        done = await service.execute(ExecutionCommand(
            operation="cancel", idempotency_key=f"kill:{oid}", source="kill", order_id=oid, skip_risk=True,
        ), wait_ack=False)
        outcomes.append((done.ok, done.broker_status, done.error))

    assert outcomes == [(True, "Cancelled", None)] * 3
    assert paper.broker.working_orders() == []
