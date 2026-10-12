"""The exit-only pair on a loaded replay (#681): it fills on the replayed prints and unwinds with the playhead.

A target's fill shrinks the stop as an effect of that fill's event, so a scrub back before it puts the stop
back to every share and the target back to working; a scrub back before the pair was sent takes the pair
away and frees the shares it committed (ADR 020 decision 3, as any order's).
"""
from __future__ import annotations

import pytest

from execution import inflight, service
from execution.models import ExecutionCommand
from ibkr import safety as _safety
from practice.broker import for_venue
from sim import feed
from sim import session_clock as clock
from sim.mode import set_venue
from tests.test_sim_practice import historical, isolated  # noqa: F401 -- autouse: a private Sim store

SYM = "IMCC"
# 04:00:10 10.00 (the buy) · 04:00:20 10.60 (target 1) · 04:00:40 9.40 (the stop)
TAPE = [(10, 10.00, {}), (20, 10.60, {}), (40, 9.40, {})]


@pytest.fixture
def replay():
    inflight.reset_for_tests()
    service.reset_for_tests()
    set_venue("sim", persist=False)
    historical(TAPE)
    _safety.set_armed(True, reason="test")
    go(10)
    broker = for_venue("sim")
    assert broker.place(SYM, "BUY", 100, "LMT", limit_price=10.05)["broker_status"] == "Filled"
    yield broker
    service.reset_for_tests()
    inflight.reset_for_tests()


def go(sec: float) -> None:
    clock.scrub_to_second(sec)
    clock.set_paused(True)
    feed.match_practice_fills()


def rows(broker) -> dict[int, dict]:
    return {int(r["order_id"]): r for r in [*broker.working_orders(), *broker.closed_orders()]}


async def send_pair() -> object:
    return await service.execute(ExecutionCommand(
        operation="exit_oco", idempotency_key="sim-pair", source="manual", origin="nova_exit", symbol=SYM,
        side="SELL", qty=100, order_type="STP", stop_price=9.50, target_price=10.50, target2_price=11.50,
        target1_qty=50, skip_risk=True))


@pytest.mark.asyncio
async def test_a_scrub_back_before_target_one_restores_the_whole_stop(replay) -> None:
    go(12)
    r = await send_pair()
    assert r.ok, r.error
    go(30)                                                    # target 1 filled on the 10.60 print at :20
    assert rows(replay)[r.target_order_id]["status"] == "Filled"
    assert rows(replay)[r.stop_order_id]["qty"] == 50 and replay.ledger.held_qty(SYM) == 50

    go(15)                                                    # after the pair, before target 1's fill
    now = rows(replay)
    assert (now[r.stop_order_id]["status"], now[r.stop_order_id]["qty"]) == ("Submitted", 100)
    assert now[r.target_order_id]["status"] == now[r.target2_order_id]["status"] == "Submitted"
    assert replay.ledger.held_qty(SYM) == 100

    go(45)                                                    # forward again: target 1, then the stop for the rest
    now = rows(replay)
    assert now[r.target_order_id]["status"] == "Filled" and now[r.stop_order_id]["filled_qty"] == 50
    assert now[r.target2_order_id]["status"] == "Cancelled" and replay.ledger.held_qty(SYM) == 0


@pytest.mark.asyncio
async def test_a_scrub_back_before_the_pair_takes_it_away_and_frees_its_shares(replay) -> None:
    go(12)
    r = await send_pair()
    assert [c["qty"] for c in inflight.snapshot("sim")] == [100.0]
    go(11)
    assert replay.working_orders() == [] and r.stop_order_id not in rows(replay)
    assert inflight.snapshot("sim") == [] and replay.ledger.held_qty(SYM) == 100
