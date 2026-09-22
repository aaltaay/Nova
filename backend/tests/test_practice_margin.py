"""Practice buying power: Reg T 2x below the PDT line, FINRA 4x intraday above it."""
from __future__ import annotations

from practice import margin


def test_intraday_four_x_above_the_pdt_line_and_reg_t_two_x_below_it() -> None:
    assert margin.multiplier(25_000) == 4.0
    assert margin.multiplier(24_999.99) == 2.0


def test_buying_power_is_equity_times_multiplier_less_open_exposure() -> None:
    assert margin.buying_power(100_000, 0) == 400_000
    assert margin.buying_power(100_000, 150_000) == 250_000
    assert margin.buying_power(10_000, 50_000) == 0.0


def test_a_reducing_trade_opens_nothing_and_only_the_excess_opens() -> None:
    assert margin.opening_qty("SELL", 5, 10) == 0
    assert margin.opening_qty("SELL", 15, 10) == 5
    assert margin.opening_qty("BUY", 5, -10) == 0
    assert margin.opening_qty("BUY", 12, -10) == 2
    assert margin.opening_qty("BUY", 5, 0) == 5
    assert margin.opening_qty("SELL", 5, 0) == 5


def test_check_refuses_only_what_exceeds_the_available_power() -> None:
    assert margin.check("BUY", 100, 10.0, 0, 100_000, 0) == (True, 1_000.0, 400_000.0)
    ok, needed, available = margin.check("BUY", 50_000, 10.0, 0, 100_000, 0)
    assert (ok, needed, available) == (False, 500_000.0, 400_000.0)
    # Closing a long needs nothing even when the account has no power left.
    assert margin.check("SELL", 100, 10.0, 100, 1_000, 999_000)[0] is True
