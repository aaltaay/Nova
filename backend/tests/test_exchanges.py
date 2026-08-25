"""Tests for listing-exchange lookup used on scanner rows."""

from exchanges import (
    attach_exchange,
    attach_exchanges,
    clear,
    exchange_for,
    normalize_ib_exchange,
    update_from_assets,
)


def setup_function() -> None:
    clear()


def test_update_from_assets_and_lookup() -> None:
    update_from_assets([
        {"symbol": "AAPL", "exchange": "NASDAQ"},
        {"symbol": "IBM", "exchange": "NYSE"},
        {"symbol": "BAD"},  # no exchange — ignored
    ])
    assert exchange_for("AAPL") == "NASDAQ"
    assert exchange_for("ibm") == "NYSE"
    assert exchange_for("MISSING") is None


def test_attach_exchange_sets_field() -> None:
    update_from_assets([{"symbol": "VEEE", "exchange": "NASDAQ"}])
    row = attach_exchange({"symbol": "VEEE", "price": 1.0})
    assert row["exchange"] == "NASDAQ"


def test_attach_exchange_preserves_existing() -> None:
    update_from_assets([{"symbol": "VEEE", "exchange": "NASDAQ"}])
    row = attach_exchange({"symbol": "VEEE", "exchange": "ARCA"})
    assert row["exchange"] == "ARCA"


def test_attach_exchanges_batch() -> None:
    update_from_assets([
        {"symbol": "AAA", "exchange": "NYSE"},
        {"symbol": "BBB", "exchange": "AMEX"},
    ])
    rows = attach_exchanges([{"symbol": "AAA"}, {"symbol": "BBB"}, {"symbol": "CCC"}])
    assert rows[0]["exchange"] == "NYSE"
    assert rows[1]["exchange"] == "AMEX"
    assert rows[2]["exchange"] is None


def test_normalize_ib_exchange_passthrough_for_known_values() -> None:
    assert normalize_ib_exchange("NASDAQ") == "NASDAQ"
    assert normalize_ib_exchange("nyse") == "NYSE"


def test_normalize_ib_exchange_maps_known_aliases() -> None:
    assert normalize_ib_exchange("ISLAND") == "NASDAQ"
    assert normalize_ib_exchange("NYSEARCA") == "ARCA"


def test_normalize_ib_exchange_unknown_or_missing_is_none() -> None:
    assert normalize_ib_exchange("SOME_UNKNOWN_VENUE") is None
    assert normalize_ib_exchange(None) is None
    assert normalize_ib_exchange("") is None
