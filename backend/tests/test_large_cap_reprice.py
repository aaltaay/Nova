"""L1-tick repricing glue for the Large Cap table (ADR 014)."""
from __future__ import annotations

import large_cap_alerts
import large_cap_metrics
import large_cap_reprice as lcr


def test_apply_l1_tick_updates_matching_row_only(monkeypatch):
    monkeypatch.setattr(
        large_cap_metrics, "build_row_metrics",
        lambda sym, **kw: {
            "rvol": 3.0, "atr_expansion": 1.5, "change_5d_pct": 0.02,
            "change_20d_pct": 0.05, "high_20d": 195.0, "low_20d": 150.0,
            "days_to_earnings": 10,
        },
    )
    fired = []
    monkeypatch.setattr(
        large_cap_alerts, "check_breakout",
        lambda sym, **kw: fired.append(sym),
    )
    rows = [
        {"symbol": "NVDA", "price": 190.0, "prev_close": 185.0, "volume": 1000},
        {"symbol": "AMD", "price": 100.0, "prev_close": 99.0, "volume": 500},
    ]
    quote = {"price": 200.0, "prev_close": 185.0, "volume": 2_000_000}
    new_rows, patch = lcr.apply_l1_tick(rows, "NVDA", quote, now=123.0)

    nvda = next(r for r in new_rows if r["symbol"] == "NVDA")
    amd = next(r for r in new_rows if r["symbol"] == "AMD")
    assert new_rows is rows
    assert nvda["price"] == 200.0
    assert nvda["rvol"] == 3.0
    assert nvda["quote_ts"] == 123.0
    assert amd == rows[1]  # untouched
    assert patch["rvol"] == 3.0
    assert fired == ["NVDA"]


def test_apply_l1_tick_no_match_returns_none_patch(monkeypatch):
    monkeypatch.setattr(large_cap_metrics, "build_row_metrics", lambda sym, **kw: {})
    monkeypatch.setattr(large_cap_alerts, "check_breakout", lambda sym, **kw: None)
    rows = [{"symbol": "AMD", "price": 100.0, "prev_close": 99.0, "volume": 500}]
    new_rows, patch = lcr.apply_l1_tick(rows, "NVDA", {"price": 1.0}, now=1.0)
    assert new_rows == rows
    assert patch is None
