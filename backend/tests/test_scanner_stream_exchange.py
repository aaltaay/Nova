"""IB scan rows carry contract.primaryExchange -- roster admission must not
throw it away (2026-08-25: exchange filter blanked the desk because IBKR
discovery never populated ``exchanges.py``'s Alpaca-sourced lookup map)."""
from __future__ import annotations

from ibkr import scanner_stream as stream


class _FakeContract:
    def __init__(self, symbol: str, primary_exchange: str | None):
        self.symbol = symbol
        self.primaryExchange = primary_exchange


class _FakeContractDetails:
    def __init__(self, contract: _FakeContract):
        self.contract = contract


class _FakeScanRow:
    def __init__(self, symbol: str, primary_exchange: str | None):
        self.contractDetails = _FakeContractDetails(
            _FakeContract(symbol, primary_exchange)
        )


def test_symbols_from_rows_returns_ranked_symbols_and_exchange_map():
    rows = [
        _FakeScanRow("AAA", "NASDAQ"),
        _FakeScanRow("BBB", "NYSE"),
        _FakeScanRow("CCC", None),
    ]
    symbols, exchanges = stream._symbols_from_rows(rows)
    assert symbols == ["AAA", "BBB", "CCC"]
    assert exchanges == {"AAA": "NASDAQ", "BBB": "NYSE"}
    assert "CCC" not in exchanges


def test_symbols_from_rows_normalizes_ib_alias():
    rows = [_FakeScanRow("AAA", "ISLAND")]
    symbols, exchanges = stream._symbols_from_rows(rows)
    assert symbols == ["AAA"]
    assert exchanges == {"AAA": "NASDAQ"}


def test_symbols_from_rows_drops_unrecognized_exchange():
    rows = [_FakeScanRow("AAA", "SOME_UNKNOWN_VENUE")]
    symbols, exchanges = stream._symbols_from_rows(rows)
    assert symbols == ["AAA"]
    assert exchanges == {}
