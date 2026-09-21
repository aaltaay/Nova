"""Sim Feed -- no synthetic tape. With nothing loaded, the Sim venue is empty."""
from __future__ import annotations

from sim import chart_replay, market
from sim.feed import tick
from sim.mode import reset_for_tests, set_sim_mode


def setup_function() -> None:
    reset_for_tests()
    set_sim_mode(True)


def teardown_function() -> None:
    reset_for_tests()


def test_tick_without_a_loaded_replay_produces_nothing() -> None:
    assert tick() == {}


def test_no_quote_book_or_prints_are_fabricated_for_any_symbol() -> None:
    for symbol in (None, "SPY", "SIM1"):
        assert market.quote(symbol) is None
    assert market.book() == {}
    assert market.last_quotes(["SPY"]) == {}
    assert market.last_quotes() == {}
    assert market.recent_prints(5) == []
    assert market.ticker_snapshot("SPY") == {}


def test_charts_never_invent_bars_without_a_replay(monkeypatch) -> None:
    import bars_store

    monkeypatch.setattr(bars_store, "read", lambda *a, **k: None)
    payload = chart_replay.fetch_replay_bars("SIM1", "1Min", 40)
    assert payload["bars"] == [] and payload["source"] == "ibkr"


def test_session_scrub_moves_clock() -> None:
    from sim import session_clock as clock

    a = clock.scrub_to_minute(30)
    assert a["scrubbed"] is True
    assert a["minute_from_open"] == 30
    assert a["phase"] == "premarket"
    b = clock.scrub_to_minute(6 * 60)  # 10:00
    assert b["phase"] == "rth"
    clock.clear_scrub()
