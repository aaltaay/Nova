"""Sim Fill -- market fill, limit cross, cancel. Never talks to IBKR."""
from __future__ import annotations

from sim import broker, market
from sim.mode import reset_for_tests, set_sim_mode


def setup_function() -> None:
    reset_for_tests()
    set_sim_mode(True)


def teardown_function() -> None:
    reset_for_tests()


def test_market_buy_fills_and_updates_position() -> None:
    raw = broker.place("SIM1", "BUY", 10, "MKT")
    assert raw["ok"] is True
    assert raw["broker_status"] == "Filled"
    pos = broker.positions()
    assert len(pos) == 1
    assert pos[0]["symbol"] == "SIM1"
    assert pos[0]["qty"] == 10
    assert broker.open_orders() == []
    closed = broker.closed_orders()
    assert closed[0]["status"] == "Filled"
    assert closed[0]["held_until"] is None


def test_limit_rests_then_crosses_on_tape() -> None:
    last = market.last()
    raw = broker.place("SIM1", "BUY", 5, "LMT", limit_price=round(last - 1.0, 2))
    assert raw["ok"] is True
    assert raw["broker_status"] == "Submitted"
    assert len(broker.open_orders()) == 1
    filled = broker.try_fill_working(last - 1.0)
    assert len(filled) == 1
    assert filled[0]["status"] == "Filled"
    assert broker.open_orders() == []


def test_cancel_working_limit() -> None:
    last = market.last()
    raw = broker.place("SIM1", "SELL", 3, "LMT", limit_price=round(last + 2.0, 2))
    oid = int(raw["order_id"])
    out = broker.cancel(oid)
    assert out["ok"] is True
    assert broker.open_orders() == []
    assert broker.closed_orders()[0]["status"] == "Cancelled"


def test_place_refuses_real_ticker() -> None:
    raw = broker.place("SPY", "BUY", 1, "MKT")
    assert raw["ok"] is False
    assert raw["reason_code"] == "SIM_SYMBOL"
    assert broker.positions() == []


def test_account_summary_is_sim() -> None:
    summary = broker.account_summary()
    assert summary["mode"] == "sim"
    assert summary["connected"] is True
    assert summary["AccountType"] == "SIM"
