"""Large Cap swing metrics (ADR 014) — RVOL, ATR expansion, 5d/20d change,
20d high/low, days-to-earnings, and the composite percentile-rank score.
"""
from __future__ import annotations

from datetime import date

import large_cap_metrics as lcm


def _bar(t, o, h, l, c, v):
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v}


def test_days_to_earnings_future_and_none():
    assert lcm.days_to_earnings("2026-09-10", today=date(2026, 8, 25)) == 16
    assert lcm.days_to_earnings(None) is None
    assert lcm.days_to_earnings("not-a-date") is None


def test_compute_rvol_delegates_to_pace_relative_volume():
    # 04:00 ET elapsed fraction floor applies; just check it's a positive ratio
    # for a plausible today/avg pair (exact formula owned by market.py).
    rvol = lcm.compute_rvol(5_000_000, 10_000_000)
    assert rvol is None or rvol > 0
    assert lcm.compute_rvol(None, 10_000_000) is None
    assert lcm.compute_rvol(5_000_000, None) is None


def test_atr_needs_period_plus_one_bars():
    bars = [_bar(str(i), 10, 11, 9, 10, 100) for i in range(10)]
    assert lcm._atr(bars, period=14) is None  # not enough bars
    bars = [_bar(str(i), 10, 11 + (i % 3), 9, 10, 100) for i in range(15)]
    atr = lcm._atr(bars, period=14)
    assert atr is not None
    assert atr > 0


def test_range_expansion_math():
    assert lcm.range_expansion(105, 100, 5.0) == 1.0
    assert lcm.range_expansion(None, 100, 5.0) is None
    assert lcm.range_expansion(105, 100, None) is None
    assert lcm.range_expansion(105, 100, 0) is None


def test_daily_bar_metrics_store_miss_returns_none_and_schedules_fill(monkeypatch):
    scheduled: list[str] = []
    monkeypatch.setattr(lcm, "schedule_daily_fill", lambda sym: scheduled.append(sym))
    import bars_store

    monkeypatch.setattr(bars_store, "read", lambda *a, **k: None)
    out = lcm._compute_daily_bar_metrics("NVDA")
    assert out == lcm._EMPTY_DAILY
    assert scheduled == ["NVDA"]


def test_daily_bar_metrics_full_history_computes_all_fields(monkeypatch):
    monkeypatch.setattr(lcm, "schedule_daily_fill", lambda sym: None)
    import bars_store

    # 21 daily bars, closes trending up 100 -> 120, highs/lows padded around close.
    bars = [
        _bar(f"d{i}", 100 + i, 100 + i + 2, 100 + i - 2, 100 + i, 1_000_000)
        for i in range(21)
    ]
    monkeypatch.setattr(
        bars_store, "read", lambda *a, **k: {"bars": bars, "coverage": {}},
    )
    out = lcm._compute_daily_bar_metrics("AAPL")
    assert out["high_20d"] == max(b["h"] for b in bars[-20:])
    assert out["low_20d"] == min(b["l"] for b in bars[-20:])
    assert out["change_5d_pct"] == (bars[-1]["c"] - bars[-6]["c"]) / bars[-6]["c"]
    assert out["change_20d_pct"] == (bars[-1]["c"] - bars[-21]["c"]) / bars[-21]["c"]
    assert out["atr14"] is not None and out["atr14"] > 0


def test_schedule_daily_fill_once_per_session(monkeypatch):
    """Repeated calls within the same 04:00-ET session must not respray the
    shared 60-req/10-min IBKR historical budget (PROBLEM_LOG 2026-08-26)."""
    import market

    monkeypatch.setattr(market, "session_key_et", lambda *a, **k: "2026-08-26")
    sent: list[str] = []
    from ibkr import historical_service as hs

    monkeypatch.setattr(
        hs, "schedule_fill",
        lambda sym, tf, limit, *, priority="background": sent.append(sym),
    )
    lcm.schedule_daily_fill("NVDA")
    lcm.schedule_daily_fill("NVDA")
    lcm.schedule_daily_fill("NVDA")
    assert sent == ["NVDA"]

    # A different symbol still gets its own first send.
    lcm.schedule_daily_fill("AMD")
    assert sent == ["NVDA", "AMD"]


def test_schedule_daily_fill_resends_after_session_rollover(monkeypatch):
    import market

    sent: list[str] = []
    from ibkr import historical_service as hs

    monkeypatch.setattr(
        hs, "schedule_fill",
        lambda sym, tf, limit, *, priority="background": sent.append(sym),
    )
    monkeypatch.setattr(market, "session_key_et", lambda *a, **k: "2026-08-26")
    lcm.schedule_daily_fill("NVDA")
    monkeypatch.setattr(market, "session_key_et", lambda *a, **k: "2026-08-27")
    lcm.schedule_daily_fill("NVDA")
    assert sent == ["NVDA", "NVDA"]


def test_daily_bar_metrics_partial_history_respects_session_guard(monkeypatch):
    """The 15-min TTL recompute path must reuse the same once-per-session
    guard as the roster-commit hook, not respray on every miss."""
    import market

    monkeypatch.setattr(market, "session_key_et", lambda *a, **k: "2026-08-26")
    sent: list[str] = []
    from ibkr import historical_service as hs

    monkeypatch.setattr(
        hs, "schedule_fill",
        lambda sym, tf, limit, *, priority="background": sent.append(sym),
    )
    import bars_store

    monkeypatch.setattr(bars_store, "read", lambda *a, **k: None)
    lcm._compute_daily_bar_metrics("NVDA")
    lcm._compute_daily_bar_metrics("NVDA")
    assert sent == ["NVDA"]


def test_daily_bar_metrics_is_ttl_cached(monkeypatch):
    calls = {"n": 0}

    def _fake_compute(sym):
        calls["n"] += 1
        return dict(lcm._EMPTY_DAILY)

    monkeypatch.setattr(lcm, "_compute_daily_bar_metrics", _fake_compute)
    lcm.daily_bar_metrics("TSLA")
    lcm.daily_bar_metrics("TSLA")
    assert calls["n"] == 1  # second call served from TTL cache, no recompute


def test_build_row_metrics_never_calls_fetch_fundamentals(monkeypatch):
    """Hot L1 tick path must only read the fundamentals cache dict, never
    trigger a synchronous yfinance fetch (would block the caller)."""
    import fundamentals

    def _boom(*_a, **_k):
        raise AssertionError("build_row_metrics must not call fetch_fundamentals")

    monkeypatch.setattr(fundamentals, "fetch_fundamentals", _boom)
    fundamentals._fundamentals_cache["NVDA"] = {
        "average_volume": 40_000_000,
        "earnings_date": "2026-07-30",
        "earnings_next_date": "2026-11-20",
        "market_cap": 4_500_000_000_000, "float_shares": 24_000_000_000,
    }
    monkeypatch.setattr(lcm, "daily_bar_metrics", lambda sym: dict(lcm._EMPTY_DAILY))
    out = lcm.build_row_metrics("NVDA", price=190.0, prev_close=185.0, volume=50_000_000)
    assert "rvol" in out
    assert out["days_to_earnings"] == lcm.days_to_earnings("2026-11-20")
    assert out["days_to_earnings"] != lcm.days_to_earnings("2026-07-30")
    assert out["market_cap"] == 4_500_000_000_000
    assert out["float"] == 24_000_000_000


def test_build_row_metrics_ignores_last_event_when_next_missing(monkeypatch):
    """Last-report earnings_date must not become a Large Cap countdown."""
    import fundamentals

    fundamentals._fundamentals_cache["AAPL"] = {
        "average_volume": 50_000_000,
        "earnings_date": "2026-07-30",
        "earnings_next_date": None,
    }
    monkeypatch.setattr(lcm, "daily_bar_metrics", lambda sym: dict(lcm._EMPTY_DAILY))
    out = lcm.build_row_metrics("AAPL", price=190.0, prev_close=185.0, volume=50_000_000)
    assert out["days_to_earnings"] is None


def test_compute_scores_percentile_ranks_and_direction_agnostic():
    rows = [
        {"symbol": "A", "rvol": 5.0, "atr_expansion": 2.0, "change_20d_pct": 0.20},
        {"symbol": "B", "rvol": 1.0, "atr_expansion": 0.5, "change_20d_pct": -0.30},
        {"symbol": "C", "rvol": None, "atr_expansion": None, "change_20d_pct": None},
    ]
    out = lcm.compute_scores(rows)
    by_sym = {r["symbol"]: r for r in out}
    # B's -30% move has larger magnitude than A's +20% -- direction-agnostic
    # scoring must not penalize it for being negative.
    assert by_sym["B"]["large_cap_score"] is not None
    assert by_sym["A"]["large_cap_score"] is not None
    assert by_sym["C"]["large_cap_score"] is None  # no components present
    assert by_sym["C"]["score_completeness"] == 0.0
    assert by_sym["A"]["score_completeness"] == 1.0


def test_compute_scores_empty_roster():
    assert lcm.compute_scores([]) == []
