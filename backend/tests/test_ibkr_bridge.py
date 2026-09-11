"""Tests for ibkr_bridge.py table/L1 quote application onto HOD Momo."""
from __future__ import annotations

import ibkr_bridge
import hod_momo_active as _hod_active
from ibkr import scanner_session as _ss
from runtime_state import ScannerRuntimeState
from runtime_state.state import TABLE_STATE_FROZEN


def _fake_state() -> ScannerRuntimeState:
    return ScannerRuntimeState()


def test_apply_table_quotes_passes_day_high_to_hod_momo(monkeypatch):
    """Cold reqTickersAsync snapshots must seed HOD truth same as the live L1 path
    (apply_l1_quote) — otherwise HOD strategies stay cold-start blocked until a
    live tick happens to arrive (see gap5 in the end-to-end verification)."""
    state = _fake_state()
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)
    monkeypatch.setattr(_hod_active, "get_active_symbols", lambda: [])

    captured: dict = {}

    def fake_on_trade_update(symbol, price, ts, *, volume=None, day_high=None):
        captured["symbol"] = symbol
        captured["price"] = price
        captured["day_high"] = day_high

    monkeypatch.setattr(ibkr_bridge._hod_momo, "on_trade_update", fake_on_trade_update)

    quotes = {"AAA": {"price": 10.0, "prev_close": 9.0, "volume": 100, "high": 10.5}}
    ibkr_bridge.apply_table_quotes(quotes)

    assert captured["symbol"] == "AAA"
    assert captured["day_high"] == 10.5


def test_apply_table_quotes_missing_high_passes_none(monkeypatch):
    state = _fake_state()
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)
    monkeypatch.setattr(_hod_active, "get_active_symbols", lambda: [])

    captured: dict = {}

    def fake_on_trade_update(symbol, price, ts, *, volume=None, day_high=None):
        captured["day_high"] = day_high

    monkeypatch.setattr(ibkr_bridge._hod_momo, "on_trade_update", fake_on_trade_update)

    quotes = {"AAA": {"price": 10.0, "prev_close": 9.0, "volume": 100}}
    ibkr_bridge.apply_table_quotes(quotes)

    assert captured["day_high"] is None


def test_apply_l1_quote_never_mutates_a_frozen_table(monkeypatch):
    """ADR 008: HOD's reserved L1 pool keeps ticking retained symbols after
    their table freezes — that must never reprice the frozen cache/timestamp
    (see PROBLEM_LOG scanner_stream shadow parity review)."""
    state = _fake_state()
    state.gainer_cache = [{"symbol": "AAA", "price": 5.0, "prev_close": 4.0, "volume": 10}]
    state.gainer_cache_ts = 111.0
    state.gainer_table.state = TABLE_STATE_FROZEN
    state.gainer_table.session_key = _ss.session_key_et()
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)
    monkeypatch.setattr(_hod_active, "get_active_symbols", lambda: ["AAA"])
    monkeypatch.setattr(ibkr_bridge._hod_momo, "on_trade_update", lambda *a, **k: None)

    ibkr_bridge.apply_l1_quote("AAA", 9.0, 500, 4.0, 222.0)

    assert state.gainer_cache[0]["price"] == 5.0
    assert state.gainer_cache_ts == 111.0


def test_apply_l1_quote_reprices_a_live_table(monkeypatch):
    state = _fake_state()
    state.gainer_cache = [{"symbol": "AAA", "price": 5.0, "prev_close": 4.0, "volume": 10}]
    state.gainer_cache_ts = 111.0
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)
    monkeypatch.setattr(_hod_active, "get_active_symbols", lambda: ["AAA"])
    monkeypatch.setattr(ibkr_bridge._hod_momo, "on_trade_update", lambda *a, **k: None)

    ibkr_bridge.apply_l1_quote("AAA", 9.0, 500, 4.0, 222.0)

    assert state.gainer_cache[0]["price"] == 9.0
    assert state.gainer_cache_ts == 222.0


def test_apply_l1_quote_archives_active_set_tick(monkeypatch):
    """G5: every HOD-decision L1 tick must land in archive.l1_ticks."""
    state = _fake_state()
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)
    monkeypatch.setattr(_hod_active, "get_active_symbols", lambda: ["AAA"])
    monkeypatch.setattr(ibkr_bridge._hod_momo, "on_trade_update", lambda *a, **k: None)
    monkeypatch.setattr(
        "ibkr.ticks.get_day_high",
        lambda _sym: 10.25,
    )

    archived: list[dict] = []

    def fake_archive(symbol, price, ts, *, volume=None, day_high=None):
        archived.append(
            {
                "symbol": symbol,
                "price": price,
                "ts": ts,
                "volume": volume,
                "day_high": day_high,
            }
        )

    monkeypatch.setattr(ibkr_bridge, "_archive_l1_tick", fake_archive)

    ibkr_bridge.apply_l1_quote("AAA", 9.5, 1_000, 8.0, 333.0)

    assert len(archived) == 1
    assert archived[0]["symbol"] == "AAA"
    assert archived[0]["price"] == 9.5
    assert archived[0]["volume"] == 1000.0
    assert archived[0]["day_high"] == 10.25
    assert archived[0]["ts"] == 333.0


def test_apply_table_quotes_archives_active_set_tick(monkeypatch):
    state = _fake_state()
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)
    monkeypatch.setattr(_hod_active, "get_active_symbols", lambda: ["AAA"])
    monkeypatch.setattr(ibkr_bridge._hod_momo, "on_trade_update", lambda *a, **k: None)

    archived: list[dict] = []
    monkeypatch.setattr(
        ibkr_bridge,
        "_archive_l1_tick",
        lambda symbol, price, ts, *, volume=None, day_high=None: archived.append(
            {"symbol": symbol, "price": price, "volume": volume, "day_high": day_high}
        ),
    )

    quotes = {"AAA": {"price": 10.0, "prev_close": 9.0, "volume": 100, "high": 10.5}}
    ibkr_bridge.apply_table_quotes(quotes)

    assert len(archived) == 1
    assert archived[0]["symbol"] == "AAA"
    assert archived[0]["day_high"] == 10.5
    assert archived[0]["volume"] == 100.0


def test_apply_l1_quote_reprices_large_cap_cache(monkeypatch):
    """ADR 014: an L1 tick for a symbol on the Large Cap table must reprice
    that row's swing metrics too, independent of gainer/gapper/afterhours."""
    state = _fake_state()
    state.large_cap_cache = [
        {"symbol": "NVDA", "price": 190.0, "prev_close": 185.0, "volume": 1_000_000},
    ]
    state.large_cap_cache_ts = 0.0
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)
    monkeypatch.setattr(_hod_active, "get_active_symbols", lambda: [])

    import large_cap_metrics as _lc_metrics

    monkeypatch.setattr(
        _lc_metrics, "build_row_metrics",
        lambda sym, **kw: {
            "rvol": 3.0, "atr_expansion": 1.0, "change_5d_pct": 0.01,
            "change_20d_pct": 0.02, "high_20d": 195.0, "low_20d": 150.0,
            "days_to_earnings": 5,
        },
    )

    patch = ibkr_bridge.apply_l1_quote("NVDA", 200.0, 2_000_000, 185.0, 444.0)

    assert state.large_cap_cache[0]["price"] == 200.0
    assert state.large_cap_cache[0]["rvol"] == 3.0
    assert state.large_cap_cache_ts == 444.0
    assert patch["rvol"] == 3.0


def test_apply_l1_quote_ignores_large_cap_when_cache_empty(monkeypatch):
    state = _fake_state()
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)
    monkeypatch.setattr(_hod_active, "get_active_symbols", lambda: [])

    patch = ibkr_bridge.apply_l1_quote("NVDA", 200.0, 2_000_000, 185.0, 444.0)

    assert state.large_cap_cache == []
    assert "rvol" not in patch


def test_apply_l1_quote_patches_one_row_without_rebuilding_lists(monkeypatch):
    """D-019: a tick must not list-comprehend every scanner cache."""
    from ibkr.l1_apply import reset_row_indexes_for_tests

    reset_row_indexes_for_tests()
    state = _fake_state()
    aaa = {"symbol": "AAA", "price": 5.0, "prev_close": 4.0, "volume": 10}
    bbb = {"symbol": "BBB", "price": 6.0, "prev_close": 5.0, "volume": 11}
    loser = {"symbol": "CCC", "price": 1.0, "prev_close": 2.0, "volume": 3}
    state.gainer_cache = [aaa, bbb]
    state.loser_cache = [loser]
    state.loser_cache_ts = 50.0
    gainer_list = state.gainer_cache
    loser_list = state.loser_cache
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)
    monkeypatch.setattr(_hod_active, "get_active_symbols", lambda: ["AAA"])
    monkeypatch.setattr(ibkr_bridge._hod_momo, "on_trade_update", lambda *a, **k: None)

    ibkr_bridge.apply_l1_quote("AAA", 9.0, 500, 4.0, 222.0)

    assert state.gainer_cache is gainer_list
    assert state.loser_cache is loser_list
    assert state.gainer_cache[1] is bbb
    assert state.loser_cache[0] is loser
    assert state.gainer_cache[0]["price"] == 9.0
    assert state.loser_cache_ts == 50.0


def test_apply_l1_quote_reprices_afterhours_in_place(monkeypatch):
    from ibkr.l1_apply import reset_row_indexes_for_tests

    reset_row_indexes_for_tests()
    state = _fake_state()
    state.current_mode = "afterhours"
    keep = {"symbol": "KEEP", "price": 8.0, "prev_close": 7.0, "volume": 100}
    hit = {"symbol": "HIT", "price": 10.0, "prev_close": 8.0, "volume": 200}
    state.afterhours_cache = [keep, hit]
    ah_list = state.afterhours_cache
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)
    monkeypatch.setattr(_hod_active, "get_active_symbols", lambda: [])
    monkeypatch.setattr(ibkr_bridge._hod_momo, "on_trade_update", lambda *a, **k: None)

    patch = ibkr_bridge.apply_l1_quote("HIT", 12.0, 400, 8.0, 333.0)

    assert state.afterhours_cache is ah_list
    assert state.afterhours_cache[0] is keep
    assert state.afterhours_cache[1]["price"] == 12.0
    assert patch["change_pct"] == 0.5


def test_refresh_hod_active_set_always_recomputes(monkeypatch):
    """Regression for the WLDS lockout (PROBLEM_LOG 2026-07-23): once all three
    scanner tables freeze for the day, their cache list objects are never
    reassigned again (ADR 008 — frozen membership is immutable), so an
    id()+len()-based memoization would return the same stale snapshot
    forever. refresh_hod_active_set must reflect the live cache contents on
    every call, even when the caller mutates the same list object in place
    between calls rather than reassigning it."""
    state = _fake_state()
    state.afterhours_cache = [{"symbol": "AAA", "change_pct": 50.0}]
    monkeypatch.setattr(ibkr_bridge, "get_runtime_state", lambda: state)

    first = ibkr_bridge.refresh_hod_active_set()
    assert "AAA" in first
    assert "WLDS" not in first

    # Same list object (id unchanged), mutated in place — mirrors what a
    # frozen table's cache would look like if a symbol were already present
    # in it but a stale-cache bug had excluded it from an earlier snapshot.
    state.afterhours_cache.append({"symbol": "WLDS", "change_pct": 117.0})

    second = ibkr_bridge.refresh_hod_active_set()
    assert "WLDS" in second
