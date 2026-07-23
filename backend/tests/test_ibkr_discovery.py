"""
Tests for the IBKR discovery module (gappers/gainers/losers via IB scanner).
No live IB Gateway required — ib_async's IB client is faked.
"""
from __future__ import annotations

import asyncio
import math

import pytest

import ibkr.discovery as discovery


@pytest.fixture(autouse=True)
def _reset_scan_cache():
    """scan_symbols() now short-TTL-caches results — isolate tests from it."""
    discovery.reset_scan_cache()
    discovery._qualified_contracts.clear()
    discovery._scan_lock = None
    yield
    discovery.reset_scan_cache()
    discovery._qualified_contracts.clear()
    discovery._scan_lock = None
    discovery.reset_scan_cache()
    discovery._qualified_contracts.clear()


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

    _next_req_id = 1000

    def __init__(self, scan_rows: list[_FakeScanRow], tickers: list[_FakeTicker]):
        self._scan_rows = scan_rows
        self._tickers = tickers
        self.wrapper = self
        self.cancelled_req_ids: list[int] = []

    def reqScannerSubscription(self, subscription, *_a, **_k):
        self._last_subscription = subscription
        data = type("ScanDataList", (), {})()
        _FakeIB._next_req_id += 1
        data.reqId = _FakeIB._next_req_id
        return data

    def startReq(self, req_id, container=None):
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        fut.set_result(list(self._scan_rows))
        return fut

    def cancelScannerSubscription(self, data_list):
        self.cancelled_req_ids.append(getattr(data_list, "reqId", None))

    async def qualifyContractsAsync(self, *contracts):
        return list(contracts)

    async def reqTickersAsync(self, *contracts):
        return self._tickers


def _patch_client(monkeypatch, fake_ib):
    """Wire fake IB + stub ib_async types so fail-loud discovery can construct subs."""
    monkeypatch.setattr(discovery._client, "get_ib", lambda: fake_ib)
    monkeypatch.setattr(discovery, "_load_ib_types", lambda: True)
    discovery._scan_lock = None

    class _Sub:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            if not hasattr(self, "belowPrice"):
                self.belowPrice = None

    class _Stock:
        def __init__(self, symbol, exchange, currency):
            self.symbol = symbol
            self.exchange = exchange
            self.currency = currency
            self.primaryExchange = "NASDAQ"

    monkeypatch.setattr(discovery, "_ScannerSubscription", _Sub)
    monkeypatch.setattr(discovery, "_Stock", _Stock)


class TestScanSymbols:
    def test_no_ib_raises_discovery_error(self, monkeypatch):
        monkeypatch.setattr(discovery._client, "get_ib", lambda: None)
        with pytest.raises(discovery.IbkrDiscoveryError, match="not connected"):
            asyncio.run(discovery.scan_symbols("TOP_PERC_GAIN"))

    def test_dedupes_and_preserves_order(self, monkeypatch):
        fake_ib = _FakeIB([_FakeScanRow("AAA"), _FakeScanRow("BBB"), _FakeScanRow("AAA")], [])
        _patch_client(monkeypatch, fake_ib)
        result = asyncio.run(discovery.scan_symbols("TOP_PERC_GAIN"))
        assert result == ["AAA", "BBB"]

    def test_below_price_sets_scanner_subscription(self, monkeypatch):
        seen: list[object] = []

        class _CapturingIB(_FakeIB):
            def reqScannerSubscription(self, subscription, *_a, **_k):
                seen.append(subscription)
                return super().reqScannerSubscription(subscription, *_a, **_k)

        fake_ib = _CapturingIB([_FakeScanRow("BTMD")], [])
        _patch_client(monkeypatch, fake_ib)
        result = asyncio.run(discovery.scan_symbols("TOP_PERC_GAIN", below_price=20.0))
        assert result == ["BTMD"]
        assert seen and float(seen[0].belowPrice) == 20.0

    def test_repeat_call_within_ttl_reuses_cached_result(self, monkeypatch):
        calls: list[int] = []

        class _CountingIB(_FakeIB):
            def reqScannerSubscription(self, subscription, *_a, **_k):
                calls.append(1)
                return super().reqScannerSubscription(subscription, *_a, **_k)

        fake_ib = _CountingIB([_FakeScanRow("AAA")], [])
        _patch_client(monkeypatch, fake_ib)

        first = asyncio.run(discovery.scan_symbols("TOP_PERC_GAIN"))
        second = asyncio.run(discovery.scan_symbols("TOP_PERC_GAIN"))
        assert first == second == ["AAA"]
        # Second call within the TTL window is served from cache — coalesces
        # duplicate one-shot scanner calls from independent loops.
        assert len(calls) == 1

    def test_different_below_price_bypasses_cache(self, monkeypatch):
        calls: list[float | None] = []

        class _CountingIB(_FakeIB):
            def reqScannerSubscription(self, subscription, *_a, **_k):
                calls.append(getattr(subscription, "belowPrice", None))
                return super().reqScannerSubscription(subscription, *_a, **_k)

        fake_ib = _CountingIB([_FakeScanRow("AAA")], [])
        _patch_client(monkeypatch, fake_ib)
        asyncio.run(discovery.scan_symbols("TOP_PERC_GAIN"))
        asyncio.run(discovery.scan_symbols("TOP_PERC_GAIN", below_price=20.0))
        assert len(calls) == 2


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

    def test_keeps_last_when_close_missing(self, monkeypatch):
        tickers = [_FakeTicker("LASTONLY", last=9.5, close=float("nan"))]
        fake_ib = _FakeIB([], tickers)
        _patch_client(monkeypatch, fake_ib)
        quotes = asyncio.run(discovery.snapshot_quotes(["LASTONLY"]))
        assert quotes["LASTONLY"]["price"] == 9.5
        assert quotes["LASTONLY"]["prev_close"] is None


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


class TestGetAfterhoursGainers:
    def test_uses_dedicated_ah_scan_code(self, monkeypatch):
        """Distinct scan universe from TOP_PERC_GAIN — never the intraday reshape."""
        seen_codes: list[str] = []

        class _CapturingIB(_FakeIB):
            def reqScannerSubscription(self, subscription, *_a, **_k):
                seen_codes.append(subscription.scanCode)
                return super().reqScannerSubscription(subscription, *_a, **_k)

        scan_rows = [_FakeScanRow("AH1")]
        tickers = [_FakeTicker("AH1", last=11.0, close=10.0)]
        fake_ib = _CapturingIB(scan_rows, tickers)
        _patch_client(monkeypatch, fake_ib)

        rows = asyncio.run(discovery.get_afterhours_gainers())
        assert [r["symbol"] for r in rows] == ["AH1"]
        assert seen_codes == ["TOP_AFTER_HOURS_PERC_GAIN"]


class TestRepriceRows:
    """Between-scan reprice tick (main.py _reprice_ibkr_caches) — keeps price
    and change fields derived from the SAME prev_close so they never drift
    apart, regardless of how often a fresh snapshot arrives."""

    def test_reprice_gapper_row_recomputes_change_from_new_price(self):
        row = {
            "symbol": "AAA",
            "price": 11.0,
            "current_price": 11.0,
            "previous_close": 10.0,
            "prev_close": 10.0,
            "change_pct": 0.1,
            "change_abs": 1.0,
            "gap_percent": 0.1,
            "volume": 1000,
        }
        updated = discovery.reprice_gapper_row(row, {"price": 12.0, "prev_close": 9.0, "volume": 2000})
        assert updated["price"] == updated["current_price"] == 12.0
        assert math.isclose(updated["change_pct"], 0.2)
        assert math.isclose(updated["change_abs"], 2.0)
        assert math.isclose(updated["gap_percent"], 0.2)
        assert updated["volume"] == 2000
        # prev_close is anchored to the row's own basis, not the fresh quote's
        assert updated["previous_close"] == 10.0

    def test_reprice_gapper_row_missing_prev_close_returns_unchanged(self):
        row = {"symbol": "AAA", "price": 11.0}
        updated = discovery.reprice_gapper_row(row, {"price": 12.0, "prev_close": None})
        assert updated == row

    def test_reprice_mover_row_recomputes_change_from_new_price(self):
        row = {"symbol": "BBB", "price": 9.0, "prev_close": 10.0, "change_pct": -0.1, "change_abs": -1.0, "volume": 500}
        updated = discovery.reprice_mover_row(row, {"price": 8.0, "prev_close": 12.0, "volume": 600})
        assert updated["price"] == 8.0
        assert math.isclose(updated["change_pct"], -0.2)
        assert math.isclose(updated["change_abs"], -2.0)
        assert updated["volume"] == 600
