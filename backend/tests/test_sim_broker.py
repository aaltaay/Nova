"""Sim practice ledger -- fills, cancel, replace. Never talks to IBKR."""
from __future__ import annotations

import pytest

from sim import broker, practice
from sim.fill_model import Reference
from sim.mode import reset_for_tests, set_sim_mode


@pytest.fixture(autouse=True)
def replay_market(monkeypatch):
    reset_for_tests()
    set_sim_mode(True)
    market = {"ref": Reference(last=10.0, bid=9.98, ask=10.02), "ts": 100.0}
    monkeypatch.setattr(practice, "admission", lambda sym: (True, "OK", None) if sym == "IMCC"
                        else (False, "not loaded", "SIM_SYMBOL_MISMATCH"))
    monkeypatch.setattr(practice, "reference", lambda sym: market["ref"] if sym == "IMCC" else Reference(None))
    monkeypatch.setattr(practice, "playhead_ts", lambda: market["ts"])
    yield market
    reset_for_tests()


def test_market_buy_fills_at_the_recorded_ask_and_updates_position() -> None:
    raw = broker.place("IMCC", "BUY", 10, "MKT")
    assert raw["ok"] is True and raw["broker_status"] == "Filled"
    pos = broker.positions()
    assert [(p["symbol"], p["qty"], p["avg_cost"]) for p in pos] == [("IMCC", 10, 10.02)]
    closed = broker.closed_orders()[0]
    assert closed["status"] == "Filled" and closed["held_until"] is None
    assert closed["fill_estimated"] is True and closed["fill_basis"] == "quote"


def test_refused_symbol_never_touches_the_ledger() -> None:
    raw = broker.place("SPY", "BUY", 1, "MKT")
    assert raw["ok"] is False and raw["reason_code"] == "SIM_SYMBOL_MISMATCH"
    assert broker.positions() == [] and broker.open_orders() == []


def test_unsupported_order_type_is_refused() -> None:
    raw = broker.place("IMCC", "BUY", 1, "TRAIL", stop_price=0.5)
    assert raw["ok"] is False and raw["reason_code"] == "SIM_ORDER_TYPE"


def test_cancel_working_limit() -> None:
    raw = broker.place("IMCC", "SELL", 3, "LMT", limit_price=12.0)
    assert raw["broker_status"] == "Submitted"
    out = broker.cancel(int(raw["order_id"]))
    assert out["ok"] is True
    assert broker.open_orders() == []
    assert broker.closed_orders()[0]["status"] == "Cancelled"


def test_replace_to_a_marketable_limit_fills_now() -> None:
    raw = broker.place("IMCC", "BUY", 2, "LMT", limit_price=9.0)
    out = broker.replace(int(raw["order_id"]), limit_price=10.50)
    assert out["ok"] is True and out["broker_status"] == "Filled"
    assert broker.closed_orders()[0]["avg_fill_price"] == 10.02


def test_resting_order_ignores_prints_at_or_before_its_placement() -> None:
    broker.place("IMCC", "BUY", 1, "LMT", limit_price=9.5)
    assert broker.try_fill_working("IMCC", [(99.0, 9.0), (100.0, 9.0)]) == []
    filled = broker.try_fill_working("IMCC", [(100.5, 9.4)])
    assert [r["avg_fill_price"] for r in filled] == [9.5]


def test_account_summary_is_sim() -> None:
    summary = broker.account_summary()
    assert summary["mode"] == "sim"
    assert summary["connected"] is True
    assert summary["AccountType"] == "SIM"
