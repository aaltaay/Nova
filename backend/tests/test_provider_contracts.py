"""Shared adapter contract tests (ADR 002) — shape + no cross-provider fallback."""
from __future__ import annotations

from adapters.alpaca_ticker import AlpacaTickerSnapshotAdapter
from adapters.ibkr_scanner import IbkrScannerAdapter
from adapters.ibkr_ticker import IbkrTickerSnapshotAdapter
from ports.scanner import DiscoveryPort, MoversPort
from ports.ticker import TickerSnapshotPort


def test_ibkr_scanner_satisfies_discovery_and_movers_ports():
    adapter = IbkrScannerAdapter()
    assert isinstance(adapter, DiscoveryPort)
    assert isinstance(adapter, MoversPort)


def test_ticker_adapters_satisfy_snapshot_port():
    assert isinstance(IbkrTickerSnapshotAdapter(), TickerSnapshotPort)
    assert isinstance(AlpacaTickerSnapshotAdapter({}, "sip"), TickerSnapshotPort)


def test_ibkr_ticker_adapter_does_not_call_alpaca(monkeypatch):
    """IBKR snapshot path must never invoke Alpaca fetch helpers."""
    calls: list[str] = []

    def _boom(*_a, **_k):
        calls.append("alpaca")
        raise AssertionError("Alpaca fallback forbidden under IBKR adapter")

    monkeypatch.setattr("ticker_alpaca.fetch_ticker_snapshot", _boom)
    monkeypatch.setattr(
        "adapters.ibkr_ticker.fetch_ticker_snapshot_ibkr",
        lambda symbol: {"symbol": symbol, "latest_trade": {"price": 1.0}},
    )
    out = IbkrTickerSnapshotAdapter().fetch_snapshot("AAPL")
    assert out["symbol"] == "AAPL"
    assert calls == []


def test_composition_selects_ibkr_ports(monkeypatch):
    from composition import market_data_providers as mdp

    monkeypatch.setattr(mdp, "_get_discovery_provider", lambda: "ibkr")
    assert isinstance(mdp.get_discovery_port(), IbkrScannerAdapter)
    assert isinstance(mdp.get_movers_port(), IbkrScannerAdapter)
    assert isinstance(mdp.get_ticker_snapshot_port(), IbkrTickerSnapshotAdapter)


def test_composition_selects_alpaca_ports(monkeypatch):
    from composition import market_data_providers as mdp

    monkeypatch.setattr(mdp, "_get_discovery_provider", lambda: "alpaca")
    from adapters.alpaca_scanner import AlpacaDiscoveryAdapter, AlpacaMoversAdapter

    assert isinstance(mdp.get_discovery_port(), AlpacaDiscoveryAdapter)
    assert isinstance(mdp.get_movers_port(), AlpacaMoversAdapter)
    assert isinstance(mdp.get_ticker_snapshot_port({}, "sip"), AlpacaTickerSnapshotAdapter)
