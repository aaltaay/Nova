"""Tests for scan_runners.run_discovery_scan control flow."""
from __future__ import annotations

import pytest

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


def test_run_discovery_scan_alpaca_populates_cache(monkeypatch):
    """The Alpaca provider still owns its own one-shot discovery."""
    state = _fake_state()
    calls = {"mark_resub": 0, "save": 0}

    monkeypatch.setattr(scan_runners, "get_runtime_state", lambda: state)
    monkeypatch.setattr(scan_runners, "_get_discovery_provider", lambda: "alpaca")
    monkeypatch.setattr(scan_runners, "_alpaca_headers", lambda: None)
    monkeypatch.setattr(
        scan_runners,
        "get_discovery_port",
        lambda: _FakeDiscoveryPort([{"symbol": "AAPL", "gap_percent": 0.1}]),
    )
    monkeypatch.setattr(scan_runners, "enrich_gappers", lambda gappers, news: list(gappers))
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
    assert calls == {"mark_resub": 1, "save": 1}


def test_run_discovery_scan_refuses_when_provider_is_ibkr(monkeypatch):
    """One roster owner: the persistent lease, not this one-shot scan.

    The IBKR branch here has been unreachable since the 2026-08-07
    authoritative cutover. It stayed in the tree long enough to attract three
    separate "premarket gappers" fixes that production never executed
    (2026-08-24), so it now refuses instead of writing a second roster.
    """
    state = _fake_state()
    monkeypatch.setattr(scan_runners, "get_runtime_state", lambda: state)
    monkeypatch.setattr(scan_runners, "_get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(scan_runners, "_alpaca_headers", lambda: {"api-key": "x"})

    def _boom_port():
        raise AssertionError("IBKR one-shot discovery must not be reached")

    monkeypatch.setattr(scan_runners, "get_discovery_port", _boom_port)

    scan_runners.run_discovery_scan()

    assert state.gapper_cache == []
    assert state.gapper_cache_ts == 0.0


def test_run_gainers_update_refuses_when_provider_is_ibkr(monkeypatch):
    state = _fake_state()
    monkeypatch.setattr(scan_runners, "get_runtime_state", lambda: state)
    monkeypatch.setattr(scan_runners, "_get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(scan_runners, "_alpaca_headers", lambda: None)

    def _boom_port():
        raise AssertionError("IBKR one-shot movers must not be reached")

    monkeypatch.setattr(scan_runners, "get_movers_port", _boom_port)

    scan_runners.run_gainers_update()

    assert state.gainer_cache == []
    assert state.loser_cache == []


def test_ibkr_scanner_adapter_refuses_every_roster_call():
    """Backstop chokepoint: any surviving caller fails loud, never writes."""
    from adapters.ibkr_scanner import IbkrScannerAdapter
    from ibkr_bridge import IbkrBridgeError

    adapter = IbkrScannerAdapter()
    for call in (adapter.get_gappers, adapter.get_gainers, adapter.get_losers):
        with pytest.raises(IbkrBridgeError, match="lease-owned"):
            call()
