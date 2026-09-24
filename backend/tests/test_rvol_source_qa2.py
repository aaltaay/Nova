"""Every scanner row that carries an RVOL names the average it divides by (QA C39 follow-up).

The universe gapper enrichment and the after-hours L1 reprice divided by the
Alpaca IEX daily-bar average without saying so, so the desk marked those rows
"source not reported".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import afterhours_discovery  # noqa: E402
import universe  # noqa: E402
from constants_scanner import SCANNER_RVOL_SOURCE_ALPACA  # noqa: E402
from ibkr import scanner_hydrate  # noqa: E402
from runtime_state import get_runtime_state  # noqa: E402


def test_universe_gappers_name_the_alpaca_average(monkeypatch):
    monkeypatch.setattr(universe, "_fetch_fundamentals_batch", lambda _s: None)
    monkeypatch.setattr(universe._exchanges, "attach_exchange", lambda _g: None)
    state = get_runtime_state()
    monkeypatch.setattr(state, "avg_volume_cache", {"GRML": 1_000_000.0})
    rows = universe.enrich_gappers(
        [{"symbol": "GRML", "volume": 3_000_000}, {"symbol": "NONE", "volume": 10}], news={},
    )
    by_sym = {r["symbol"]: r for r in rows}
    assert by_sym["GRML"]["rel_volume"] == 3.0
    assert by_sym["GRML"]["rvol_source"] == SCANNER_RVOL_SOURCE_ALPACA
    # No average, no RVOL -- and no source claimed for it.
    assert by_sym["NONE"]["rel_volume"] is None
    assert by_sym["NONE"]["rvol_source"] is None


def test_after_hours_reprice_names_the_average_it_measured_against():
    row = {"symbol": "TOPS", "prev_close": 1.0, "price": 1.2, "volume": 1000, "rel_volume": 7.5, "rvol_source": "yfinance"}
    measured = afterhours_discovery.reprice_afterhours_row_ibkr(row, {"price": 1.3, "volume": 900_000}, {"TOPS": 100_000.0})
    assert measured["rvol_source"] == SCANNER_RVOL_SOURCE_ALPACA
    # No average here: the row keeps its own RVOL and its own source.
    kept = afterhours_discovery.reprice_afterhours_row_ibkr(row, {"price": 1.3}, {})
    assert kept["rel_volume"] == 7.5
    assert kept["rvol_source"] == "yfinance"


def test_a_name_only_row_states_no_volume():
    stub = scanner_hydrate.stub_row("SMX", 1)
    assert stub["volume"] is None
    assert stub["price"] is None


def test_after_hours_reprice_leaves_an_unknown_volume_unknown():
    """#459: neither the tick nor the row knew the volume, and the reprice wrote 0."""
    row = {"symbol": "TOPS", "prev_close": 1.0, "price": 1.2, "volume": None, "rel_volume": None}
    out = afterhours_discovery.reprice_afterhours_row_ibkr(row, {"price": 1.3}, {"TOPS": 100_000.0})
    assert out["price"] == 1.3
    assert out["volume"] is None
    # No volume, no RVOL -- and no source claimed for one.
    assert out["rel_volume"] is None
    assert out["rvol_source"] is None
    # A row with no volume key at all is the same unknown.
    keyless = {"symbol": "TOPS", "prev_close": 1.0, "price": 1.2}
    assert afterhours_discovery.reprice_afterhours_row_ibkr(keyless, {"price": 1.3}, {})["volume"] is None


def test_after_hours_reprice_keeps_what_the_row_or_the_tick_knows():
    row = {"symbol": "TOPS", "prev_close": 1.0, "price": 1.2, "volume": 250_000, "rel_volume": 7.5, "rvol_source": "yfinance"}
    assert afterhours_discovery.reprice_afterhours_row_ibkr(row, {"price": 1.3}, {})["volume"] == 250_000
    ticked = afterhours_discovery.reprice_afterhours_row_ibkr(row, {"price": 1.3, "volume": 900_000.0}, {})
    assert ticked["volume"] == 900_000
    # A tick that says zero states it; that is not an unknown.
    assert afterhours_discovery.reprice_afterhours_row_ibkr(row, {"price": 1.3, "volume": 0}, {})["volume"] == 0


def test_after_hours_rows_from_name_only_gainers_state_no_volume():
    rows = afterhours_discovery.build_afterhours_rows_from_ibkr_gainers(
        [{"symbol": "SMX", "price": 2.5, "prev_close": 1.5, "change_pct": 0.66}],
        min_change_pct=10.0,
    )
    assert rows[0]["volume"] is None


def test_a_trade_print_does_not_make_an_unknown_volume_known():
    """The Alpaca trade stream adds a print's size to a known volume only (#459)."""
    import websocket

    cache = [{"symbol": "SMX", "prev_close": 1.5, "price": 2.4, "volume": None}]
    assert websocket.apply_trade_to_mover_list(cache, "SMX", 2.5, 100)
    assert cache[0]["volume"] is None
    assert cache[0]["price"] == 2.5
    known = [{"symbol": "SMX", "prev_close": 1.5, "price": 2.4, "volume": 1_000}]
    websocket.apply_trade_to_mover_list(known, "SMX", 2.5, 100)
    assert known[0]["volume"] == 1_100
