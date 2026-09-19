"""Sim Feed -- looping SIM1 tape only. No real tickers."""
from __future__ import annotations

from constants_sim import SIM_SYMBOL
from sim import market
from sim.feed import tick
from sim.mode import reset_for_tests, set_sim_mode


def setup_function() -> None:
    reset_for_tests()
    set_sim_mode(True)


def teardown_function() -> None:
    reset_for_tests()


def test_step_loops_last_and_print_payload() -> None:
    first = market.step()
    second = market.step()
    assert first["symbol"] == SIM_SYMBOL
    assert first["type"] == "print"
    assert first["exchange"] == "SIM"
    assert first["price"] != second["price"]
    assert isinstance(first["time"], str) and "T" in first["time"]
    q = market.quote()
    assert q is not None
    assert q["bid"] < q["ask"]


def test_tick_helper_returns_print() -> None:
    payload = tick()
    assert payload["symbol"] == SIM_SYMBOL
    assert payload["size"] > 0


def test_book_has_sim_mm_levels() -> None:
    book = market.book()
    assert len(book["bids"]) == 5
    assert book["bids"][0]["mm"] == "SIM"
    assert book["l1_fallback"] is False


def test_quote_refuses_real_tickers() -> None:
    assert market.quote("SPY") is None
    assert market.last_quotes(["SPY"]) == {}


def test_chart_bars_iso_ascending() -> None:
    for tf in ("10Sec", "1Min", "5Min", "1Day"):
        bars = market.chart_bars(SIM_SYMBOL, tf, 40)
        assert bars["source"] == "sim"
        assert len(bars["bars"]) > 5
        times = [b["t"] for b in bars["bars"]]
        assert all(isinstance(t, str) for t in times)
        assert times == sorted(times)
        assert len(times) == len(set(times))


def test_session_scrub_moves_clock() -> None:
    from sim import session_clock as clock

    a = clock.scrub_to_minute(30)
    assert a["scrubbed"] is True
    assert a["minute_from_open"] == 30
    assert a["phase"] == "premarket"
    b = clock.scrub_to_minute(4 * 60)  # 10:00
    assert b["phase"] == "rth"
    clock.clear_scrub()
