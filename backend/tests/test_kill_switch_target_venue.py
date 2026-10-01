"""The execution door's target venue: the kill switch's cancels only (spec D, #656).

The kill switch sweeps every venue's working orders whatever the desk shows, so its cancels name
the venue they mean. Nothing else may: a place, a buy or another source is refused, and Live only
while IBKR (Live's broker) is connected. A cancel aimed at Paper or Sim needs no IBKR at all.
"""
from __future__ import annotations

import asyncio

import pytest

from execution import broker_send, inflight, live_cancel, service, telemetry
from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
from ibkr import safety as _safety
from sim.mode import reset_for_tests as reset_venue, set_venue


@pytest.fixture(autouse=True)
def _clean():
    from execution import store

    store.init_db()
    reset_venue()
    inflight.reset_for_tests()
    telemetry.reset_for_tests()
    yield
    inflight.reset_for_tests()
    telemetry.reset_for_tests()
    reset_venue()


def _aimed(target: str, *, source: str = "kill", operation: str = "cancel", key: str = "k") -> ExecutionCommand:
    return ExecutionCommand(operation=operation, idempotency_key=f"{key}-{target}-{source}-{operation}",  # type: ignore[arg-type]
                            source=source, order_id=12, symbol="AAPL", side="BUY", qty=1,  # type: ignore[arg-type]
                            order_type="LMT", limit_price=1.0, skip_risk=True, target_venue=target)


def _recorder(sent: list):
    async def record(cmd, execution_id, timings, *, wait_ack=True, reject, venue=None):
        sent.append(venue)
        return ExecutionReceipt(ok=True, execution_id=execution_id, operation=cmd.operation, source=cmd.source,
                                idempotency_key=cmd.idempotency_key, order_id=cmd.order_id or 5, mode=venue,
                                timings=timings)
    return record


async def _never(*_a, **_k):
    raise AssertionError("an order was sent that the door had to refuse")


@pytest.mark.parametrize("source, operation", [("manual", "cancel"), ("bot", "cancel"), ("flatten", "cancel"),
                                               ("kill", "place")])
def test_only_a_kill_cancel_may_name_a_target_venue(monkeypatch, source, operation):
    set_venue("live", persist=False)
    monkeypatch.setattr(service, "send_broker", _never)
    receipt = asyncio.run(service.execute(_aimed("paper", source=source, operation=operation), wait_ack=False))
    assert receipt.ok is False and receipt.reason_code == "TARGET_VENUE_REFUSED"
    assert "only the kill switch's cancels" in (receipt.error or "")


def test_an_unknown_target_venue_is_refused(monkeypatch):
    monkeypatch.setattr(service, "send_broker", _never)
    receipt = asyncio.run(service.execute(_aimed("moon"), wait_ack=False))
    assert receipt.reason_code == "TARGET_VENUE_REFUSED" and "unknown target venue" in (receipt.error or "")


def test_a_kill_cancel_aimed_at_live_needs_ibkr_connected(monkeypatch):
    set_venue("paper", persist=False)
    monkeypatch.setattr("ibkr.client.is_connected", lambda: False)
    monkeypatch.setattr(service, "send_broker", _never)
    receipt = asyncio.run(service.execute(_aimed("live"), wait_ack=False))
    assert receipt.ok is False and receipt.reason_code == "TARGET_VENUE_REFUSED"
    assert "IBKR is not connected" in (receipt.error or "")


def test_a_kill_cancel_aimed_at_paper_goes_to_paper_from_a_live_desk_with_ibkr_down(monkeypatch):
    """#656: the desk on Live, the Gateway down -- Paper's order is still cancelled on Paper."""
    set_venue("live", persist=False)
    monkeypatch.setattr("ibkr.client.is_enabled", lambda: False)
    monkeypatch.setattr("ibkr.client.is_connected", lambda: False)
    sent: list = []
    monkeypatch.setattr(service, "send_broker", _recorder(sent))
    receipt = asyncio.run(service.execute(_aimed("paper"), wait_ack=False))
    assert receipt.ok is True and sent == ["paper"] and receipt.venue == "paper"


def test_a_wedged_ib_loop_holds_ibkrs_sends_only(monkeypatch):
    import loop_lag

    set_venue("paper", persist=False)
    _safety.set_armed(True, reason="test")
    monkeypatch.setattr(loop_lag, "is_wedged", lambda: True)
    sent: list = []
    monkeypatch.setattr(service, "send_broker", _recorder(sent))

    def cancel(key: str) -> ExecutionCommand:
        return ExecutionCommand(operation="cancel", idempotency_key=key, source="manual", order_id=5,
                                symbol="AAPL", skip_risk=True)

    assert asyncio.run(service.execute(cancel("wedge-paper"), wait_ack=False)).ok is True
    assert sent == ["paper"]                                 # Paper never touches the IB loop
    set_venue("live", persist=False)
    monkeypatch.setattr("ibkr.client.is_enabled", lambda: True)
    monkeypatch.setattr("ibkr.client.is_connected", lambda: True)
    receipt = asyncio.run(service.execute(cancel("wedge-live"), wait_ack=False))
    assert receipt.ok is False and receipt.reason_code == "IB_LOOP_WEDGED" and sent == ["paper"]


def test_a_live_kill_cancel_asks_ibkr_itself_not_the_desks_venue(monkeypatch):
    """From a Paper desk ``ibkr.orders.cancel_order`` refuses (the desk is practice): the kill's Live
    cancel goes to IBKR directly (``execution.live_cancel``)."""
    set_venue("paper", persist=False)
    asked: list[int] = []

    async def ibkr_cancel(order_id, *, watch=None):
        asked.append(order_id)
        return {"ok": True, "error": None, "verified_gone": True, "order_id": order_id}

    async def desk_cancel(order_id, *, watch=None):
        raise AssertionError("the desk-venue cancel was used for a Live kill cancel")

    monkeypatch.setattr(live_cancel, "cancel_verified", ibkr_cancel)
    monkeypatch.setattr(broker_send, "cancel_order_verified_on_ib", desk_cancel)
    receipt = asyncio.run(broker_send.send_broker(_aimed("live"), "exec-kill-live", StageTimings(received_ns=1),
                                                  wait_ack=False, reject=None, venue="live"))
    assert receipt.ok is True and asked == [12]


def test_ibkrs_own_cancel_verifies_on_ibkrs_open_orders(monkeypatch):
    """``live_cancel`` cancels on IBKR and waits until IBKR no longer lists the order."""
    trades = [type("T", (), {"order": type("O", (), {"orderId": 12})()})()]
    cancelled: list[int] = []

    class FakeIB:
        def cancelOrder(self, order):            # noqa: N802 -- ib_async's name
            cancelled.append(order.orderId)
            trades.clear()

        def openTrades(self):                    # noqa: N802 -- ib_async's name
            return list(trades)

    monkeypatch.setattr("ibkr.client.is_enabled", lambda: True)
    monkeypatch.setattr("ibkr.client.is_connected", lambda: True)
    monkeypatch.setattr("ibkr.client.get_ib", lambda: FakeIB())
    result = asyncio.run(live_cancel.cancel_verified(12))
    assert result == {"ok": True, "error": None, "verified_gone": True, "order_id": 12}
    assert cancelled == [12]
