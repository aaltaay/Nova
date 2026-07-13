"""
Tests for the IBKR discovery module (gappers/gainers/losers via IB scanner).
No live IB Gateway required — ib_async's IB client is faked.
"""
from __future__ import annotations

import asyncio
import math

import ibkr.discovery as discovery


class _FakeContract:
    def __init__(self, symbol: str, primary_exchange: str = "NASDAQ"):
        self.symbol = symbol
        self.primaryExchange = primary_exchange


class _FakeContractDetails:
    def __init__(self, contract: _FakeContract):
        self.contract = contract


class _FakeScanRow:
    def __init__(self, symbol: str):
        self.contractDetails = _FakeContractDetails(_FakeContract(symbol))


class _FakeTicker:
    def __init__(self, symbol: str, last: float, close: float, open_: float = float("nan"), volume: float = 1000.0):
        self.contract = _FakeContract(symbol)
        self.last = last
        self.close = close
        self.open = open_
        self.volume = volume


class _FakeIB:
    """Stands in for ib_async.IB — only the methods discovery.py calls."""

    def __init__(self, scan_rows: list[_FakeScanRow], tickers: list[_FakeTicker]):
        self._scan_rows = scan_rows
        self._tickers = tickers

    async def reqScannerDataAsync(self, subscription):
        return self._scan_rows

    async def qualifyContractsAsync(self, *contracts):
        return list(contracts)

    async def reqTickersAsync(self, *contracts):
        return self._tickers


def _patch_client(monkeypatch, fake_ib):
    monkeypatch.setattr(discovery._client, "get_ib", lambda: fake_ib)


class TestScanSymbols:
    def test_no_ib_returns_empty(self, monkeypatch):
        monkeypatch.setattr(discovery._client, "get_ib", lambda: None)
        result = asyncio.run(discovery.scan_symbols("TOP_PERC_GAIN"))
        assert result == []

    def test_dedupes_and_preserves_order(self, monkeypatch):
        fake_ib = _FakeIB([_FakeScanRow("AAA"), _FakeScanRow("BBB"), _FakeScanRow("AAA")], [])
        _patch_client(monkeypatch, fake_ib)
        result = asyncio.run(discovery.scan_symbols("TOP_PERC_GAIN"))
        assert result == ["AAA", "BBB"]


class TestSnapshotQuotes:
    def test_nan_fields_are_excluded(self, monkeypatch):
        tickers = [
            _FakeTicker("GOOD", last=10.0, close=8.0),
            _FakeTicker("NODATA", last=float("nan"), close=float("nan")),
        ]
        fake_ib = _FakeIB([], tickers)
        _patch_client(monkeypatch, fake_ib)
        quotes = asyncio.run(discovery.snapshot_quotes(["GOOD", "NODATA"]))
        assert "GOOD" in quotes
        assert "NODATA" not in quotes
        assert quotes["GOOD"]["price"] == 10.0
        assert quotes["GOOD"]["prev_close"] == 8.0
        assert quotes["GOOD"]["exchange"] == "NASDAQ"

    def test_falls_back_to_close_when_no_last(self, monkeypatch):
        tickers = [_FakeTicker("XYZ", last=float("nan"), close=5.0)]
        fake_ib = _FakeIB([], tickers)
        _patch_client(monkeypatch, fake_ib)
        quotes = asyncio.run(discovery.snapshot_quotes(["XYZ"]))
        assert quotes["XYZ"]["price"] == 5.0


class TestGetGappers:
    def test_builds_expected_row_shape_and_filters_min_gap(self, monkeypatch):
        scan_rows = [_FakeScanRow("BIGGAP"), _FakeScanRow("SMALLGAP")]
        tickers = [
            _FakeTicker("BIGGAP", last=11.0, close=10.0),    # +10% gap
            _FakeTicker("SMALLGAP", last=10.01, close=10.0),  # ~0.1% gap, below floor
        ]
        fake_ib = _FakeIB(scan_rows, tickers)
        _patch_client(monkeypatch, fake_ib)

        rows = asyncio.run(discovery.get_gappers())
        symbols = [r["symbol"] for r in rows]
        assert "BIGGAP" in symbols
        assert "SMALLGAP" not in symbols

        row = next(r for r in rows if r["symbol"] == "BIGGAP")
        assert row["price"] == 11.0
        assert row["previous_close"] == row["prev_close"] == 10.0
        assert row["current_price"] == row["price"]
        assert math.isclose(row["gap_percent"], 0.1)
        assert math.isclose(row["change_pct"], row["gap_percent"])
        assert math.isclose(row["change_abs"], 1.0)


class TestGetMovers:
    def test_gainers_sorted_descending(self, monkeypatch):
        scan_rows = [_FakeScanRow("A"), _FakeScanRow("B")]
        tickers = [
            _FakeTicker("A", last=11.0, close=10.0),   # +10%
            _FakeTicker("B", last=15.0, close=10.0),   # +50%
        ]
        fake_ib = _FakeIB(scan_rows, tickers)
        _patch_client(monkeypatch, fake_ib)

        rows = asyncio.run(discovery.get_gainers())
        assert [r["symbol"] for r in rows] == ["B", "A"]

    def test_losers_sorted_ascending(self, monkeypatch):
        scan_rows = [_FakeScanRow("A"), _FakeScanRow("B")]
        tickers = [
            _FakeTicker("A", last=9.0, close=10.0),    # -10%
            _FakeTicker("B", last=5.0, close=10.0),    # -50%
        ]
        fake_ib = _FakeIB(scan_rows, tickers)
        _patch_client(monkeypatch, fake_ib)

        rows = asyncio.run(discovery.get_losers())
        assert [r["symbol"] for r in rows] == ["B", "A"]

    def test_gap_percent_uses_open_vs_prev_close(self, monkeypatch):
        scan_rows = [_FakeScanRow("A")]
        tickers = [_FakeTicker("A", last=12.0, close=10.0, open_=11.0)]  # gap = +10%, change = +20%
        fake_ib = _FakeIB(scan_rows, tickers)
        _patch_client(monkeypatch, fake_ib)

        rows = asyncio.run(discovery.get_gainers())
        row = rows[0]
        assert math.isclose(row["change_pct"], 0.2)
        assert math.isclose(row["gap_percent"], 0.1)
