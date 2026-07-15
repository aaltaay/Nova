"""Tests for IBKR-backed after-hours mover discovery."""
from __future__ import annotations

from afterhours_discovery import (
    build_afterhours_rows_from_ibkr_gainers,
    reprice_afterhours_rows_ibkr,
)


def test_build_afterhours_rows_filters_and_shapes():
    rows = build_afterhours_rows_from_ibkr_gainers(
        [
            {"symbol": "xcur", "price": 2.55, "prev_close": 1.65, "change_pct": 0.5455, "volume": 4_170_000},
            {"symbol": "LOW", "price": 1.10, "prev_close": 1.05, "change_pct": 0.047, "volume": 1000},
            {"symbol": "ATHE", "price": 2.54, "prev_close": 1.86, "change_pct": 0.3655, "volume": 3_700_000},
        ],
        min_change_pct=10.0,
    )
    syms = [r["symbol"] for r in rows]
    assert syms == ["XCUR", "ATHE"]
    assert rows[0]["gap_percent"] == 0.5455
    assert rows[0]["volume"] == 4_170_000
    assert rows[0]["current_price"] == 2.55


def test_reprice_afterhours_rows_ibkr_updates_price_and_volume(monkeypatch):
    import market as m

    monkeypatch.setattr(m, "volume_day_elapsed_fraction", lambda now=None: 1.0)
    rows = [
        {
            "symbol": "XCUR",
            "price": 2.40,
            "prev_close": 1.65,
            "previous_close": 1.65,
            "current_price": 2.40,
            "gap_percent": 0.45,
            "change_pct": 0.45,
            "volume": 1000,
        }
    ]
    quotes = {"XCUR": {"price": 2.55, "volume": 4_170_000}}
    out = reprice_afterhours_rows_ibkr(rows, quotes, {"XCUR": 100_000.0})
    assert out[0]["price"] == 2.55
    assert out[0]["volume"] == 4_170_000
    assert out[0]["rel_volume"] == 41.7  # 4.17M / 100k at full-day pace
