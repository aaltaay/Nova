"""The execution door keeps Paper, Sim and Live apart (#655, audit 2026-09-30).

In-flight commitments, order watches and order ids are a venue's own: a Paper
sell still working must not refuse a Live exit, Paper's fill of order N must not
mark Live's order N filled, and a cancel that names a venue is refused when the
desk is elsewhere.
"""
from __future__ import annotations

import asyncio

import pytest

from execution import inflight, service, telemetry
from execution.models import ExecutionCommand
from ibkr import safety as _safety
from sim.mode import reset_for_tests as reset_venue, set_venue


@pytest.fixture(autouse=True)
def _clean():
    reset_venue()
    inflight.reset_for_tests()
    telemetry.reset_for_tests()
    yield
    inflight.reset_for_tests()
    telemetry.reset_for_tests()
    reset_venue()


def test_a_paper_commitment_never_spends_lives_shares():
    set_venue("paper", persist=False)
    inflight.commit("exec-paper", symbol="AAPL", side="SELL", qty=100)
    assert inflight.committed_qty("AAPL", "SELL") == 100
    set_venue("live", persist=False)
    assert inflight.committed_qty("AAPL", "SELL") == 0          # Live sees none of Paper's
    assert inflight.committed_qty("AAPL", "SELL", "paper") == 100
    inflight.commit("exec-live", symbol="AAPL", side="SELL", qty=40)
    assert inflight.committed_qty("AAPL", "SELL") == 40
    assert [r["execution_id"] for r in inflight.snapshot()] == ["exec-live"]
    assert len(inflight.snapshot(all_venues=True)) == 2


def test_one_venues_order_id_never_frees_anothers_commitment():
    inflight.commit("p", symbol="AAPL", side="SELL", qty=1, venue="paper")
    inflight.commit("l", symbol="AAPL", side="SELL", qty=1, venue="live")
    inflight.attach_order("p", 7)
    inflight.attach_order("l", 7)                                # the same number, two venues
    assert inflight.release_order(7, "live") is True
    assert inflight.committed_qty("AAPL", "SELL", "paper") == 1  # Paper's order 7 still holds
    assert inflight.committed_qty("AAPL", "SELL", "live") == 0
    assert inflight.release_on_broker_status(7, "Filled") is False   # IBKR's callbacks speak for Live only
    assert inflight.release_on_broker_status(7, "Filled", "paper") is True


def test_a_paper_watch_is_not_ibkrs_order_with_the_same_id():
    live = telemetry.watch_order(9, "exec-live")
    paper = telemetry.watch_order(9, "exec-paper", venue="paper")
    sim = telemetry.watch_order(9, "exec-sim", venue="sim")
    assert len({id(live), id(paper), id(sim)}) == 3
    paper.note_status("Filled", filled=1, remaining=0, average_fill_price=10.0, perm_id=9,
                      callback_perf_ns=1)
    assert live.latest_status != "Filled"                        # IBKR's watch is untouched
    assert telemetry.watch_order(9, venue="paper") is paper
    assert telemetry.watch_order(9) is live                      # IBKR's handlers look up by id alone


def _cancel(expected: str | None) -> ExecutionCommand:
    return ExecutionCommand(operation="cancel", idempotency_key=f"c-{expected}", source="manual",
                            order_id=12, symbol="AAPL", skip_risk=True, expected_venue=expected)


def test_a_cancel_naming_another_venue_is_refused_before_anything_is_sent(monkeypatch):
    set_venue("live", persist=False)

    async def boom(*_a, **_k):
        raise AssertionError("the door sent an order meant for another venue")

    monkeypatch.setattr(service, "send_broker", boom)
    receipt = asyncio.run(service.execute(_cancel("paper"), wait_ack=False))
    assert receipt.ok is False and receipt.reason_code == "VENUE_CHANGED"
    assert "not paper" in (receipt.error or "")


def test_the_door_routes_by_the_venue_it_validated_on(monkeypatch):
    """The desk moves while an order is checked: the order is refused, never sent elsewhere."""
    set_venue("paper", persist=False)
    _safety.set_armed(True, reason="test")
    import execution.validate as validate

    def validate_then_flip(cmd, venue=None):
        set_venue("live", persist=False)                         # the operator clicks Live mid-check
        return True, "OK", None

    async def boom(*_a, **_k):
        raise AssertionError("the order was sent after the desk moved")

    monkeypatch.setattr(validate, "validate_command", validate_then_flip)
    monkeypatch.setattr(service, "send_broker", boom)
    cmd = ExecutionCommand(operation="place", idempotency_key="race", source="manual", symbol="AAPL",
                           side="BUY", qty=1, order_type="LMT", limit_price=1.0, skip_risk=True)
    receipt = asyncio.run(service.execute(cmd, wait_ack=False))
    assert receipt.ok is False and receipt.reason_code == "VENUE_CHANGED"
    assert "moved from paper to live" in (receipt.error or "")
