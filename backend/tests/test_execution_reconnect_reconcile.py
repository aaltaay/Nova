"""A new IBKR session is reconciled with what Nova recorded: fills it never heard, positions, liquidations.

Lean's IBKR brokerage dropped fills delivered while it believed it was disconnected (issue 249) and
missed IBKR's own liquidations (issue 156). Nova's handlers never skip a fill for being disconnected,
but a reconnect builds a new ``IB()``, and ib_async reads the gap's fills back as a request's answer:
no ``execDetailsEvent`` fires for them. These tests drive that read-back with a mocked IB.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import execution.store as store
from execution import inflight, reconnect_reconcile, telemetry
from execution.telemetry_handlers import make_handlers
from ibkr import session_fills, unclaimed
from ibkr.order_rows import trade_to_order_row
from nova_os import events_db
from nova_os.events import get_events

NOVA_CLIENT = 17


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    store.init_db()
    events_db.init_db()
    telemetry.reset_for_tests()
    inflight.reset_for_tests()
    yield
    telemetry.reset_for_tests()
    inflight.reset_for_tests()


class _Event:
    def __init__(self) -> None:
        self.handlers: list = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def emit(self, *args) -> None:
        for handler in list(self.handlers):
            handler(*args)


def _fill(exec_id: str, *, order_id: int, shares: float, side: str = "BOT", symbol: str = "ZTG",
          perm_id: int = 0, client_id: int = NOVA_CLIENT, liquidation: int = 0, cum_qty: float | None = None,
          commission_id: str = "") -> SimpleNamespace:
    """An ib_async Fill as a read-back leaves it: the CommissionReport stays empty until IBKR's arrives."""
    return SimpleNamespace(
        contract=SimpleNamespace(symbol=symbol),
        execution=SimpleNamespace(
            execId=exec_id, orderId=order_id, permId=perm_id, clientId=client_id, side=side, shares=shares,
            price=2.0, avgPrice=2.0, cumQty=shares if cum_qty is None else cum_qty, liquidation=liquidation,
            acctNumber="U1", orderRef="", time=datetime(2026, 10, 9, 14, 30, tzinfo=timezone.utc),
        ),
        commissionReport=SimpleNamespace(execId=commission_id, commission=1.25 if commission_id else 0.0),
    )


def _position(symbol: str, qty: float) -> SimpleNamespace:
    return SimpleNamespace(account="U1", contract=SimpleNamespace(symbol=symbol, secType="STK"), position=qty)


class _Ib:
    """A session: its executions, its positions, its trades, and its position event."""

    def __init__(self, *, fills=(), positions=(), trades=()) -> None:
        self._fills = list(fills)
        self._positions = list(positions)
        self._trades = list(trades)
        self.client = SimpleNamespace(clientId=NOVA_CLIENT)
        self.positionEvent = _Event()

    def fills(self):
        return list(self._fills)

    def positions(self):
        return list(self._positions)

    def trades(self):
        return list(self._trades)


def _reserve(key: str, order_id: int) -> str:
    execution_id, _ = store.reserve(
        idempotency_key=key, operation="place", source="manual", symbol="ZTG", received_ns=1,
        payload={"qty": 100, "sent_qty": 100, "side": "BUY", "venue": "live"},
    )
    store.update_stages(execution_id, status="acked", order_id=order_id, mode="live")
    return execution_id


def test_a_fill_made_while_the_socket_was_down_reaches_its_order(monkeypatch):
    """The Lean #249 shape: without the catch-up the watch never hears the fill, the row stays ``acked``
    and the in-flight shares stay "already sent"."""
    execution_id = _reserve("gap-fill", 801)
    inflight.commit(execution_id, symbol="ZTG", side="BUY", qty=100, venue="live")
    inflight.attach_order(execution_id, 801)
    telemetry.watch_order(801, execution_id, side="BUY")
    first = _Ib(positions=[_position("ZTG", 0)])
    reconnect_reconcile.reconcile(first, reconnect=False)

    trade = SimpleNamespace(order=SimpleNamespace(orderId=801, permId=5801, totalQuantity=100),
                            orderStatus=SimpleNamespace(status="Filled"))
    gap = _fill("e-801", order_id=801, perm_id=5801, shares=100)
    second = _Ib(fills=[gap], positions=[_position("ZTG", 100)], trades=[trade])
    found = reconnect_reconcile.reconcile(second, reconnect=True)

    assert found["claims"]["caught_up"] == 1 and found["gaps"] == []
    row = store.get_by_id(execution_id)
    assert row["status"] == "filled" and row["filled_qty"] == 100.0
    assert inflight.committed_qty("ZTG", "BUY", "live") == 0.0


def test_a_read_back_fill_with_no_commission_is_unknown_never_zero(monkeypatch):
    execution_id = _reserve("gap-commission", 802)
    watch = telemetry.watch_order(802, execution_id, side="BUY")
    watch.note_commission(1.0)                     # the first fill's report, heard live
    reconnect_reconcile.reconcile(_Ib(), reconnect=False)
    no_trade = _Ib(fills=[_fill("e-802b", order_id=802, shares=50, cum_qty=50)], positions=[_position("ZTG", 50)])
    reconnect_reconcile.reconcile(no_trade, reconnect=True)
    assert watch.commission_unknown is True
    assert store.get_by_id(execution_id)["commission"] is None


def test_an_order_row_never_books_a_commission_that_has_not_arrived_as_zero():
    """ib_async gives each fill an empty CommissionReport (commission 0.0) until IBKR's report arrives."""
    from ib_async import CommissionReport

    base = dict(order=SimpleNamespace(orderId=1, action="BUY", totalQuantity=2, orderType="MKT", lmtPrice=0.0,
                                      auxPrice=0.0, outsideRth=False, orderRef="nova-1", permId=0, parentId=0),
                contract=SimpleNamespace(symbol="ZTG"),
                orderStatus=SimpleNamespace(status="Filled", filled=2, remaining=0, avgFillPrice=2.0, whyHeld=""))
    arrived = SimpleNamespace(execution=SimpleNamespace(execId="a", shares=1.0, price=2.0),
                              commissionReport=CommissionReport(execId="a", commission=0.35))
    pending = SimpleNamespace(execution=SimpleNamespace(execId="b", shares=1.0, price=2.0),
                              commissionReport=CommissionReport())
    assert trade_to_order_row(SimpleNamespace(**base, fills=[arrived]))["commission"] == 0.35
    assert trade_to_order_row(SimpleNamespace(**base, fills=[arrived, pending]))["commission"] is None
    assert trade_to_order_row(SimpleNamespace(**base, fills=[arrived]))["order_ref"] == "nova-1"


def test_an_ibkr_liquidation_is_loud_and_kept(monkeypatch):
    """Lean IB #156: IBKR's own liquidation (order id -1, client 0) reached no handler."""
    reconnect_reconcile.reconcile(_Ib(positions=[_position("ZTG", 100)]), reconnect=False)
    liquidated = _fill("e-liq", order_id=-1, client_id=0, side="SLD", shares=100, liquidation=1)
    ib = _Ib(fills=[liquidated], positions=[_position("ZTG", 0)])
    found = reconnect_reconcile.reconcile(ib, reconnect=True)
    assert found["claims"]["liquidation"] == 1 and found["gaps"] == []      # the fill explains the move
    assert unclaimed.status()["counts"] == {"liquidation": 1}
    events = [e for e in get_events() if (e.get("payload") or {}).get("event") == "ibkr_liquidation"]
    assert len(events) == 1 and events[0]["payload"]["exec_id"] == "e-liq"


def test_a_liquidation_between_reconnects_is_said_as_its_position_moves():
    ib = _Ib(positions=[_position("ZTG", 100)])
    reconnect_reconcile.on_ready(ib)
    ib._fills.append(_fill("e-liq-live", order_id=0, client_id=0, side="SLD", shares=100, liquidation=1))
    ib.positionEvent.emit(_position("ZTG", 0))
    assert unclaimed.status()["counts"].get("liquidation") == 1


def test_a_position_that_moved_with_no_fill_to_explain_it_is_loud():
    reconnect_reconcile.reconcile(_Ib(positions=[_position("ZTG", 100)]), reconnect=False)
    found = reconnect_reconcile.reconcile(_Ib(positions=[_position("ZTG", 40)]), reconnect=True)
    assert found["gaps"] == [{"account": "U1", "symbol": "ZTG", "before": 100.0, "after": 40.0,
                              "by_fills": 0.0, "unexplained": -60.0}]
    assert unclaimed.status()["counts"] == {"position_gap": 1}
    assert any((e.get("payload") or {}).get("event") == "ibkr_position_gap" for e in get_events())


def test_fills_the_old_session_knew_are_not_counted_twice():
    heard = _fill("e-heard", order_id=900, shares=100)
    reconnect_reconcile.reconcile(_Ib(fills=[heard], positions=[_position("ZTG", 100)]), reconnect=False)
    found = reconnect_reconcile.reconcile(_Ib(fills=[heard], positions=[_position("ZTG", 100)]), reconnect=True)
    assert found["unheard"] == 0 and found["gaps"] == []


def test_a_fill_another_client_sent_is_said_not_dropped():
    reconnect_reconcile.reconcile(_Ib(), reconnect=False)
    tws = _fill("e-tws", order_id=0, client_id=0, shares=10, perm_id=4242)
    found = reconnect_reconcile.reconcile(_Ib(fills=[tws], positions=[_position("ZTG", 10)]), reconnect=True)
    assert found["claims"]["outside"] == 1 and unclaimed.status()["counts"] == {"outside_fill": 1}


def test_a_live_fill_heard_is_never_called_unheard_by_the_next_session():
    on_exec = make_handlers(telemetry._watches.get)[2]
    fill = _fill("e-live", order_id=901, shares=100)
    trade = SimpleNamespace(order=SimpleNamespace(orderId=901, permId=0, totalQuantity=100),
                            orderStatus=SimpleNamespace(status="Filled", remaining=0, filled=100))
    on_exec(trade, fill)
    assert session_fills.take_unheard(_Ib(fills=[fill])) == []


def test_an_ibkr_error_on_an_order_no_watch_holds_is_said(caplog):
    """``telemetry_handlers.on_ib_error`` returned without a word when no watch held the order."""
    order = SimpleNamespace(order=SimpleNamespace(orderId=77))
    ib = _Ib(trades=[order])
    on_error = make_handlers(telemetry._watches.get, ib)[0]
    on_error(77, 201, "Order rejected - reason: margin")
    on_error(9999, 162, "Historical market data Service error")     # a data request: its own handler's
    assert [e["order_id"] for e in unclaimed.status()["events"]] == [77]
    assert "no Nova order is watching" in caplog.text


def test_why_held_is_recorded_and_a_locate_hold_is_told_apart(caplog):
    execution_id = _reserve("held", 902)
    telemetry.watch_order(902, execution_id, side="SELL")
    on_status = make_handlers(telemetry._watches.get)[1]

    def status(why: str):
        return SimpleNamespace(order=SimpleNamespace(orderId=902, permId=0),
                               orderStatus=SimpleNamespace(status="PreSubmitted", filled=0.0, remaining=100.0,
                                                           avgFillPrice=0.0, whyHeld=why))

    on_status(status("locate"))
    watch = telemetry._watches[902]
    assert watch.why_held == "locate" and store.get_by_id(execution_id)["why_held"] == "locate"
    assert any(r.levelname == "WARNING" and "whyHeld=locate" in r.getMessage() for r in caplog.records)
    on_status(status(""))
    assert watch.why_held is None and watch.last_why_held == "locate"
    assert store.get_by_id(execution_id)["why_held"] == "locate"     # the ledger keeps the hold it had


def test_fills_and_commissions_are_heard_while_the_session_reads_disconnected(monkeypatch):
    """Lean IB #249 returned early from its fill handler while it thought it was disconnected (Error 1100).
    Nova's handlers never ask: a fill IBKR delivers in the window reaches its watch."""
    import ibkr.client as client_mod
    import ibkr.session_state as session_state

    session_state.set_degraded()                          # what Error 1100 does
    monkeypatch.setattr(client_mod, "is_connected", lambda: False)
    execution_id = _reserve("degraded", 903)
    telemetry.watch_order(903, execution_id, side="BUY")
    _err, _status, on_exec, on_comm = make_handlers(telemetry._watches.get)
    trade = SimpleNamespace(order=SimpleNamespace(orderId=903, permId=0, totalQuantity=100),
                            orderStatus=SimpleNamespace(status="Filled", remaining=0, filled=100))
    fill = _fill("e-degraded", order_id=903, shares=100)
    on_exec(trade, fill)
    on_comm(trade, fill, SimpleNamespace(commission=0.5))
    watch = telemetry._watches[903]
    assert watch.has_fill() and watch.commission == 0.5
    assert store.get_by_id(execution_id)["status"] == "filled"
    session_state.reset_for_testing()
