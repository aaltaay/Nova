"""Hard guard: Sim on means ibkr.orders cannot place to Gateway."""
from __future__ import annotations

from constants_sim import SIM_NO_IBKR_CODE, SIM_NO_IBKR_REASON
from ibkr import orders as ibkr_orders
from sim.mode import reset_for_tests, set_sim_mode


def setup_function() -> None:
    reset_for_tests()


def teardown_function() -> None:
    reset_for_tests()


def test_place_order_refused_in_sim() -> None:
    set_sim_mode(True)
    raw = ibkr_orders.place_order("AAPL", "BUY", 1, "MKT")
    assert raw["ok"] is False
    assert raw["error"] == SIM_NO_IBKR_REASON
    assert raw["reason_code"] == SIM_NO_IBKR_CODE
    assert raw["mode"] == "sim"


def test_bracket_refused_in_sim() -> None:
    set_sim_mode(True)
    raw = ibkr_orders.place_bracket_order("AAPL", "BUY", 1, 25.0, 24.0, 26.0)
    assert raw["ok"] is False
    assert raw["error"] == SIM_NO_IBKR_REASON


def test_cancel_refused_on_ibkr_adapter_in_sim() -> None:
    set_sim_mode(True)
    raw = ibkr_orders.cancel_order(99)
    assert raw["ok"] is False
    assert raw["error"] == SIM_NO_IBKR_REASON
