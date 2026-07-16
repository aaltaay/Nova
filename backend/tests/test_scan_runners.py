"""Tests for scan_runners.run_discovery_scan control flow."""
from __future__ import annotations

import scan_runners
from runtime_state import ScannerRuntimeState


def _fake_state() -> ScannerRuntimeState:
    return ScannerRuntimeState()


def test_run_discovery_scan_ibkr_populates_cache_without_alpaca_headers(monkeypatch):
    """IBKR prices must populate even when Alpaca listing/news credentials are absent."""
    state = _fake_state()
    calls = {"ensure_avg_volume": 0, "check_news": 0, "mark_resub": 0, "save": 0}

    monkeypatch.setattr(scan_runners, "get_runtime_state", lambda: state)
    monkeypatch.setattr(scan_runners, "_get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(scan_runners, "_alpaca_headers", lambda: None)
    monkeypatch.setattr(
        scan_runners,
        "run_ibkr",
        lambda coro: [{"symbol": "AAPL", "gap_percent": 0.1}],
    )
    monkeypatch.setattr(scan_runners._ibkr_discovery, "get_gappers", lambda: object())
    monkeypatch.setattr(
        scan_runners,
        "ensure_avg_volume",
        lambda *a, **k: calls.__setitem__("ensure_avg_volume", calls["ensure_avg_volume"] + 1),
    )
    monkeypatch.setattr(
        scan_runners,
        "_check_news",
        lambda *a, **k: calls.__setitem__("check_news", calls["check_news"] + 1) or {},
    )
    monkeypatch.setattr(
        scan_runners,
        "enrich_gappers",
        lambda gappers, news: list(gappers),
    )
    monkeypatch.setattr(
        scan_runners,
        "mark_resub",
        lambda: calls.__setitem__("mark_resub", calls["mark_resub"] + 1),
    )
    monkeypatch.setattr(
        scan_runners,
        "save_gapper_snapshot",
        lambda *a, **k: calls.__setitem__("save", calls["save"] + 1),
    )

    scan_runners.run_discovery_scan()

    assert state.gapper_cache == [{"symbol": "AAPL", "gap_percent": 0.1}]
    assert calls == {"ensure_avg_volume": 0, "check_news": 0, "mark_resub": 1, "save": 1}


def test_run_discovery_scan_ibkr_happy_path_populates_cache(monkeypatch):
    state = _fake_state()

    monkeypatch.setattr(scan_runners, "get_runtime_state", lambda: state)
    monkeypatch.setattr(scan_runners, "_get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(scan_runners, "_alpaca_headers", lambda: {"api-key": "x"})
    monkeypatch.setattr(
        scan_runners, "run_ibkr",
        lambda coro: [{"symbol": "AAPL", "gap_percent": 0.1}],
    )
    monkeypatch.setattr(scan_runners._ibkr_discovery, "get_gappers", lambda: object())
    monkeypatch.setattr(scan_runners, "ensure_avg_volume", lambda *a, **k: None)
    monkeypatch.setattr(scan_runners, "_check_news", lambda *a, **k: {"AAPL": "2026-07-15T00:00:00Z"})
    monkeypatch.setattr(
        scan_runners, "enrich_gappers",
        lambda gappers, news: [{**g, "has_news": g["symbol"] in news} for g in gappers],
    )
    saved = {}
    monkeypatch.setattr(
        scan_runners, "save_gapper_snapshot",
        lambda gappers, ts: saved.update(gappers=gappers, ts=ts),
    )
    resub_calls = []
    monkeypatch.setattr(scan_runners, "mark_resub", lambda: resub_calls.append(True))

    scan_runners.run_discovery_scan()

    assert state.gapper_cache == [{"symbol": "AAPL", "gap_percent": 0.1, "has_news": True}]
    assert resub_calls == [True]
    assert saved["gappers"] == state.gapper_cache


def test_run_gainers_update_ibkr_without_alpaca_headers(monkeypatch):
    state = _fake_state()
    monkeypatch.setattr(scan_runners, "get_runtime_state", lambda: state)
    monkeypatch.setattr(scan_runners, "_get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(scan_runners, "_alpaca_headers", lambda: None)
    monkeypatch.setattr(
        scan_runners,
        "run_ibkr",
        lambda coro: [{"symbol": "XYZ", "price": 10.0, "change_pct": 0.05}],
    )
    monkeypatch.setattr(scan_runners._ibkr_discovery, "get_gainers", lambda: object())
    monkeypatch.setattr(scan_runners._ibkr_discovery, "get_losers", lambda: object())
    monkeypatch.setattr(
        scan_runners,
        "enrich_ibkr_mover",
        lambda row, news: {**row, "enriched": True, "news": news},
    )
    monkeypatch.setattr(scan_runners, "save_movers_snapshot", lambda *a, **k: None)

    scan_runners.run_gainers_update()

    assert len(state.gainer_cache) == 1
    assert state.gainer_cache[0]["symbol"] == "XYZ"
    assert state.gainer_cache[0]["enriched"] is True
