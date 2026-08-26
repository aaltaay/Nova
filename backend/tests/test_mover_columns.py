"""Regression tests for the empty Gainers columns (2026-08-26).

Two independent causes, both locked in here:

1. ``gap_percent`` was never computed on the IBKR L1 reprice path, so Gap %
   rendered ``N/A`` on every mover row for the whole session.
2. Nothing filled ``rel_volume`` / ``float`` / ``short_interest`` /
   ``market_cap`` under ``discovery=ibkr`` -- ``enrich_ibkr_mover`` existed but
   was never called, and the two functions that fetch yfinance fundamentals
   both return early for ibkr.

Plus the honesty guard: a displayed live table whose rows have no price past
the admission grace window must fail integrity, not report pass.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mover_enrich_hooks as meh  # noqa: E402
import mover_enrich_view as mev  # noqa: E402
from hod_momo_integrity_scanner import _row_price_checks  # noqa: E402
from ibkr.discovery import reprice_mover_row  # noqa: E402


# --- gap_percent from the IB session open (tick 14) -------------------------

def test_reprice_mover_row_computes_gap_from_open():
    row = {"symbol": "CRE", "price": None, "prev_close": None, "gap_percent": None}
    out = reprice_mover_row(row, {"price": 6.77, "prev_close": 2.57, "volume": 10, "open": 3.0})
    assert out["gap_percent"] is not None
    # (3.00 - 2.57) / 2.57
    assert round(out["gap_percent"], 4) == round((3.0 - 2.57) / 2.57, 4)
    # Intraday change is a different number and must stay separate.
    assert round(out["change_pct"], 4) == round((6.77 - 2.57) / 2.57, 4)


def test_reprice_mover_row_leaves_gap_null_without_open():
    """No tick-14 yet: never reuse change_pct as a gap."""
    out = reprice_mover_row(
        {"symbol": "CRE", "gap_percent": None},
        {"price": 6.77, "prev_close": 2.57, "volume": 10},
    )
    assert out["gap_percent"] is None
    assert out["change_pct"] is not None


def test_reprice_mover_row_keeps_prior_gap_when_open_missing():
    """A later tick without open must not blank an already-known gap."""
    out = reprice_mover_row(
        {"symbol": "CRE", "prev_close": 2.57, "open": 3.0, "gap_percent": 0.1673},
        {"price": 7.0, "prev_close": 2.57, "volume": 20},
    )
    assert out["gap_percent"] is not None


# --- reference columns ------------------------------------------------------

def test_decorate_rows_fills_reference_columns(monkeypatch):
    from fundamentals import _fundamentals_cache

    monkeypatch.setitem(_fundamentals_cache, "CRE", {
        "market_cap": 1_234_000_000,
        "float_shares": 5_000_000,
        "short_interest": 900_000,
        "short_ratio": 2.5,
        "average_volume": 1_000_000,
    })
    rows = [{"symbol": "CRE", "volume": 4_000_000}]
    out = mev.decorate_rows(rows)

    assert out[0]["market_cap"] == 1_234_000_000
    assert out[0]["float"] == 5_000_000
    assert out[0]["short_interest"] == 900_000
    assert out[0]["short_ratio"] == 2.5
    assert out[0]["rel_volume"] == 4.0
    # ADR 008: a frozen table's stored row must not be mutated by a view.
    assert rows[0] == {"symbol": "CRE", "volume": 4_000_000}


def test_decorate_rows_never_clobbers_existing_values(monkeypatch):
    """Afterhours enriches its own rows; a cold cache must not blank them."""
    from fundamentals import _fundamentals_cache

    monkeypatch.setitem(_fundamentals_cache, "AAOG", {})
    out = mev.decorate_rows([
        {"symbol": "AAOG", "volume": 10, "market_cap": 42, "rel_volume": 3.3},
    ])
    assert out[0]["market_cap"] == 42
    assert out[0]["rel_volume"] == 3.3


def test_decorate_rows_leaves_rvol_null_without_avg_volume(monkeypatch):
    from fundamentals import _fundamentals_cache

    monkeypatch.setitem(_fundamentals_cache, "VMAR", {"market_cap": None})
    out = mev.decorate_rows([{"symbol": "VMAR", "volume": 0}])
    assert out[0]["rel_volume"] is None


def test_relative_volume_guards():
    assert mev.relative_volume(None, 100) is None
    assert mev.relative_volume(100, None) is None
    assert mev.relative_volume(100, 0) is None
    assert mev.relative_volume(250, 100) == 2.5


def test_decorate_rows_avg_volume_is_yfinance_not_alpaca(monkeypatch):
    """PROBLEM_LOG 2026-07-16: Alpaca IEX avg volume blew RVOL up 100x-3000x."""
    from fundamentals import _fundamentals_cache
    from runtime_state import get_runtime_state

    state = get_runtime_state()
    monkeypatch.setitem(state.avg_volume_cache, "CJMB", 13_620.0)   # Alpaca IEX
    monkeypatch.setitem(_fundamentals_cache, "CJMB", {"average_volume": 3_375_816.0})
    out = mev.decorate_rows([{"symbol": "CJMB", "volume": 3_375_816}])
    assert out[0]["rel_volume"] == 1.0


# --- fundamentals warm is single-flight ------------------------------------

def test_mover_warm_is_single_flight(monkeypatch):
    """One warm worker at a time.

    A thread per commit per table stacked hundreds of live yfinance sockets and
    threads onto the API process on a cold cache until it stopped accepting
    connections on :8000.
    """
    import threading

    batches: list[list[str]] = []
    entered = threading.Event()
    gate = threading.Event()

    def fake_batch(symbols):
        batches.append(list(symbols))
        entered.set()
        gate.wait(timeout=5)

    monkeypatch.setattr("fundamentals.fetch_fundamentals_batch", fake_batch)
    meh._pending.clear()
    meh._worker = None

    meh.on_mover_roster_commit("gainers", [{"symbol": "AAA"}])
    first = meh._worker
    assert first is not None
    assert entered.wait(timeout=5), "warm worker never started"

    # Commits while the worker is busy must queue, not spawn more threads.
    meh.on_mover_roster_commit("losers", [{"symbol": "BBB"}])
    meh.on_mover_roster_commit("afterhours", [{"symbol": "CCC"}])
    assert meh._worker is first
    assert meh._pending == {"BBB", "CCC"}

    gate.set()
    first.join(timeout=5)
    assert batches[0] == ["AAA"]
    assert batches[1] == ["BBB", "CCC"]
    assert meh._pending == set()


def test_mover_warm_ignores_non_mover_tables():
    meh._pending.clear()
    meh._worker = None
    meh.on_mover_roster_commit("large_cap", [{"symbol": "AAPL"}])
    assert meh._pending == set()
    assert meh._worker is None


# --- row-price honesty on a displayed live table ---------------------------

def test_row_price_checks_fail_when_live_table_is_starved():
    checks = _row_price_checks([
        {"table": "gainers", "rows": 50, "priced": 25, "roster_age_sec": 3600.0},
    ])
    assert [c["status"] for c in checks] == ["fail"]
    assert "25/50" in checks[0]["detail"]


def test_row_price_checks_pass_inside_admission_grace():
    """Name-only admission (ADR 008) legitimately shows price=null briefly."""
    checks = _row_price_checks([
        {"table": "gainers", "rows": 50, "priced": 0, "roster_age_sec": 5.0},
    ])
    assert [c["status"] for c in checks] == ["pass"]


def test_row_price_checks_pass_when_fully_priced():
    checks = _row_price_checks([
        {"table": "gainers", "rows": 50, "priced": 50, "roster_age_sec": 3600.0},
    ])
    assert [c["status"] for c in checks] == ["pass"]
