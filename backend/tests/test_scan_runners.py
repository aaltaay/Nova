"""Tests for scan_runners.run_discovery_scan control flow."""
from __future__ import annotations

import scan_runners
from runtime_state import ScannerRuntimeState


class _FakeDiscoveryPort:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def get_gappers(self) -> list[dict]:
        return list(self._rows)


class _FakeMoversPort:
    def __init__(self, gainers: list[dict], losers: list[dict] | None = None):
        self._gainers = gainers
        self._losers = losers or []

    def get_gainers(self) -> list[dict]:
        return list(self._gainers)

    def get_losers(self) -> list[dict]:
        return list(self._losers)


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
        "get_discovery_port",
        lambda: _FakeDiscoveryPort([{"symbol": "AAPL", "gap_percent": 0.1}]),
    )
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
        scan_runners,
        "get_discovery_port",
        lambda: _FakeDiscoveryPort([{"symbol": "AAPL", "gap_percent": 0.1}]),
    )
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
        "get_movers_port",
        lambda: _FakeMoversPort([{"symbol": "XYZ", "price": 10.0, "change_pct": 0.05}]),
    )
    monkeypatch.setattr(
        scan_runners,
        "enrich_ibkr_mover",
        lambda row, news: {**row, "enriched": True, "news": news},
    )
    monkeypatch.setattr(scan_runners, "save_movers_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(scan_runners, "mark_resub", lambda: None)

    scan_runners.run_gainers_update()

    assert len(state.gainer_cache) == 1
    assert state.gainer_cache[0]["symbol"] == "XYZ"
    assert state.gainer_cache[0]["enriched"] is True


def test_run_gainers_update_clears_sticky_bridge_error(monkeypatch):
    """Successful movers refresh must clear sticky ibkr_bridge_last_error (RTH)."""
    state = _fake_state()
    state.ibkr_bridge_last_error = (
        "gainers: IbkrDiscoveryError: scanner TOP_PERC_GAIN timed out after 20s"
    )
    state.ibkr_bridge_last_error_ts = 1_700_000_000.0
    monkeypatch.setattr(scan_runners, "get_runtime_state", lambda: state)
    monkeypatch.setattr(scan_runners, "_get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(scan_runners, "_alpaca_headers", lambda: None)
    monkeypatch.setattr(
        scan_runners,
        "get_movers_port",
        lambda: _FakeMoversPort([{"symbol": "XYZ", "price": 10.0, "change_pct": 0.05}]),
    )
    monkeypatch.setattr(
        scan_runners,
        "enrich_ibkr_mover",
        lambda row, news: {**row, "enriched": True},
    )
    monkeypatch.setattr(scan_runners, "save_movers_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(scan_runners, "mark_resub", lambda: None)

    scan_runners.run_gainers_update()

    assert state.gainer_cache
    assert state.ibkr_bridge_last_error == ""


def test_run_gainers_update_clears_sticky_bridge_error_on_losers_only(monkeypatch):
    """Clearing must not require gainers specifically — losers landing rows
    proves the bridge is live again just as well (see PROBLEM_LOG 2026-07-23
    sticky-banner-after-reconnect)."""
    state = _fake_state()
    state.ibkr_bridge_last_error = "losers: IbkrDiscoveryError: ib=none"
    state.ibkr_bridge_last_error_ts = 1_700_000_000.0
    monkeypatch.setattr(scan_runners, "get_runtime_state", lambda: state)
    monkeypatch.setattr(scan_runners, "_get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(scan_runners, "_alpaca_headers", lambda: None)
    monkeypatch.setattr(
        scan_runners,
        "get_movers_port",
        lambda: _FakeMoversPort([], [{"symbol": "ZZZ", "price": 5.0, "change_pct": -0.05}]),
    )
    monkeypatch.setattr(
        scan_runners,
        "enrich_ibkr_mover",
        lambda row, news: {**row, "enriched": True},
    )
    monkeypatch.setattr(scan_runners, "save_movers_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(scan_runners, "mark_resub", lambda: None)

    scan_runners.run_gainers_update()

    assert state.loser_cache
    assert state.ibkr_bridge_last_error == ""
