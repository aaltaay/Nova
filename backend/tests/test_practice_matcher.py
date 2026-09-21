"""Paper matcher: resting orders fill on the live tape prints since the last pass."""
from __future__ import annotations

import os
from datetime import datetime

import pytest

from practice import matcher, tape_hold
from practice.broker import PracticeBroker
from practice.clock import ET
from practice.ledger import Ledger
from sim.fill_model import Reference

NOW = datetime(2026, 9, 21, 10, 0, tzinfo=ET).timestamp()


class FakeLive:
    def __init__(self) -> None:
        self.now = NOW
        self.prints: list[tuple[float, float]] = []

    def reference(self, symbol: str) -> Reference:
        return Reference(10.0, 9.98, 10.02, live=True) if symbol == "IMCC" else Reference(None, live=True)

    def admission(self, symbol: str):
        return (True, "OK", None) if symbol == "IMCC" else (False, "dark", "PRACTICE_NO_LIVE_PRINT")

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return [(ts, px) for ts, px in self.prints if after_ts < ts <= through_ts]

    def now_ts(self) -> float:
        return self.now


@pytest.fixture
def desk(monkeypatch):
    holds: list[list[str]] = []
    errors: dict[str, str] = {}

    async def reconcile(wanted):
        holds.append(sorted(wanted))
        return dict(errors)

    monkeypatch.setattr(tape_hold, "reconcile", reconcile)
    matcher.reset_for_tests()
    ref = FakeLive()
    broker = PracticeBroker(ref, Ledger(100_000, created_ts=NOW), "NOVA-PAPER", venue="paper")
    yield broker, ref, holds, errors
    matcher.reset_for_tests()


@pytest.mark.asyncio
async def test_a_pass_holds_the_resting_symbols_and_fills_on_prints_since_they_rested(desk) -> None:
    broker, ref, holds, _errors = desk
    assert broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.5)["broker_status"] == "Submitted"
    ref.prints = [(NOW - 1, 9.0), (NOW + 1, 9.4)]  # the first print predates the order
    ref.now = NOW + 2
    filled = await matcher.pass_once(broker)
    assert [(r["avg_fill_price"], r["fill_basis"]) for r in filled] == [(9.5, "print_cross")]
    assert holds == [["IMCC"]]
    ref.now = NOW + 3
    assert await matcher.pass_once(broker) == []
    assert holds[-1] == []  # nothing rests: the line is released


@pytest.mark.asyncio
async def test_a_pass_never_rereads_prints_it_already_looked_at(desk) -> None:
    broker, ref, _holds, _errors = desk
    broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.5)
    ref.now = NOW + 2
    assert await matcher.pass_once(broker) == []
    ref.prints = [(NOW + 1, 9.4)]  # arrives late, inside a window already scanned
    ref.now = NOW + 3
    assert await matcher.pass_once(broker) == []
    ref.prints.append((NOW + 3.5, 9.4))
    ref.now = NOW + 4
    assert len(await matcher.pass_once(broker)) == 1


@pytest.mark.asyncio
async def test_a_pass_rolls_the_practice_day_even_with_nothing_resting(desk) -> None:
    broker, ref, _holds, _errors = desk
    before = broker.ledger.day_started_ts
    ref.now = NOW + 24 * 3600
    await matcher.pass_once(broker)
    assert broker.ledger.day_started_ts == before + 24 * 3600


@pytest.mark.asyncio
async def test_a_line_that_will_not_open_is_logged_and_the_order_keeps_waiting(desk, caplog) -> None:
    broker, ref, _holds, errors = desk
    broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.5)
    errors["IMCC"] = "Gateway not connected"
    ref.now = NOW + 2
    with caplog.at_level("WARNING", logger="practice.matcher"):
        assert await matcher.pass_once(broker) == []
    assert "IMCC" in caplog.text and "Gateway not connected" in caplog.text
    assert broker.working_symbols() == ["IMCC"]


def test_the_matcher_is_registered_as_a_runtime_task() -> None:
    path = os.path.join(os.path.dirname(__file__), "..", "app_runtime_tasks.py")
    with open(path, encoding="utf-8") as f:
        source = f.read()
    assert '("practice.matcher", _practice_matcher.run)' in source
