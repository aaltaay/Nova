"""ADR 010 HOT/COLD classification -- hydrate and snapshot_quotes are never HOT."""
from __future__ import annotations

import pytest

from ibkr.work_class import WorkClass, classify, is_hot


@pytest.mark.parametrize(
    "label",
    [
        "snapshot_quotes",
        "hydrate_rows",
        "surge_seed",
        "enrichment",
        "reprice",
        "reqTickersAsync",
        "reqHistoricalDataAsync",
        "reqCompletedOrdersAsync",
        "setups_stream",
    ],
)
def test_cold_labels(label: str) -> None:
    assert classify(label) is WorkClass.COLD
    assert is_hot(label) is False


@pytest.mark.parametrize(
    "label",
    [
        "placeOrder",
        "cancelOrder",
        "reqMktData",
        "reqScannerSubscription",
        "reqMktDepth",
        "reqTickByTickData",
        "connectAsync",
        "qualify_hot",
    ],
)
def test_hot_labels(label: str) -> None:
    assert classify(label) is WorkClass.HOT
    assert is_hot(label) is True


def test_hydrate_must_not_classify_hot() -> None:
    assert classify("hydrate_rows") is not WorkClass.HOT
    assert classify("hydrate") is WorkClass.COLD
    assert classify("snapshot_quotes") is not WorkClass.HOT


def test_unknown_label_raises() -> None:
    with pytest.raises(ValueError, match="unknown label"):
        classify("not_a_real_ib_job")


def test_empty_label_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        classify("   ")
