"""Tests for scan_runners.run_discovery_scan control flow.

scan_runners.py mutates main.py's module-level caches via `_m()`; these tests
replace `_m()` with a plain namespace object so no real network/IBKR call or
main.py global state is touched.
"""
from __future__ import annotations

from types import SimpleNamespace

import scan_runners


def _fake_main() -> SimpleNamespace:
    return SimpleNamespace(_gapper_cache=[], _gapper_cache_ts=0.0, _last_discovery_ts=0.0)


def test_run_discovery_scan_ibkr_returns_early_without_headers(monkeypatch):
    """IBKR discovery still needs Alpaca headers for news/avg-volume enrichment —
    a missing headers dict must short-circuit before touching the cache."""
    fake_main = _fake_main()
    calls = {"ensure_avg_volume": 0, "mark_resub": 0, "save": 0}

    monkeypatch.setattr(scan_runners, "_m", lambda: fake_main)
    monkeypatch.setattr(scan_runners, "_get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(scan_runners, "_alpaca_headers", lambda: None)
    monkeypatch.setattr(scan_runners, "run_ibkr", lambda coro: [{"symbol": "AAPL"}])
    monkeypatch.setattr(scan_runners._ibkr_discovery, "get_gappers", lambda: object())
    monkeypatch.setattr(
        scan_runners, "ensure_avg_volume",
        lambda *a, **k: calls.__setitem__("ensure_avg_volume", calls["ensure_avg_volume"] + 1),
    )
    monkeypatch.setattr(
        scan_runners, "mark_resub",
        lambda: calls.__setitem__("mark_resub", calls["mark_resub"] + 1),
    )
    monkeypatch.setattr(
        scan_runners, "save_gapper_snapshot",
        lambda *a, **k: calls.__setitem__("save", calls["save"] + 1),
    )

    scan_runners.run_discovery_scan()

    assert fake_main._gapper_cache == []
    assert calls == {"ensure_avg_volume": 0, "mark_resub": 0, "save": 0}


def test_run_discovery_scan_ibkr_happy_path_populates_cache(monkeypatch):
    fake_main = _fake_main()

    monkeypatch.setattr(scan_runners, "_m", lambda: fake_main)
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

    assert fake_main._gapper_cache == [{"symbol": "AAPL", "gap_percent": 0.1, "has_news": True}]
    assert resub_calls == [True]
    assert saved["gappers"] == fake_main._gapper_cache
