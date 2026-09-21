"""Practice fill rules (architecture/practice-fills.md). Every fill is an estimate."""
from __future__ import annotations

import pytest

from sim.fill_model import (
    BASIS_LAST_PRINT,
    BASIS_PRINT_CROSS,
    BASIS_QUOTE,
    BASIS_STOP_TRIGGER,
    Fill,
    Reference,
    at_placement,
    on_print,
)

QUOTED = Reference(last=10.00, bid=9.98, ask=10.02)
PRINTS_ONLY = Reference(last=10.00)


def test_market_orders_take_the_recorded_quote_when_one_exists() -> None:
    assert at_placement("BUY", "MKT", QUOTED) == Fill(10.02, BASIS_QUOTE)
    assert at_placement("SELL", "MKT", QUOTED) == Fill(9.98, BASIS_QUOTE)


def test_market_orders_fall_back_to_the_last_print_without_a_quote() -> None:
    assert at_placement("BUY", "MKT", PRINTS_ONLY) == Fill(10.00, BASIS_LAST_PRINT)
    assert at_placement("SELL", "MKT", PRINTS_ONLY) == Fill(10.00, BASIS_LAST_PRINT)


def test_nothing_fills_before_the_replay_has_printed() -> None:
    assert at_placement("BUY", "MKT", Reference(last=None)) is None


def test_marketable_limit_fills_at_the_touch_never_worse_than_the_limit() -> None:
    assert at_placement("BUY", "LMT", QUOTED, limit=10.05) == Fill(10.02, BASIS_QUOTE)
    assert at_placement("SELL", "LMT", QUOTED, limit=9.90) == Fill(9.98, BASIS_QUOTE)


@pytest.mark.parametrize("side, limit", [("BUY", 9.99), ("SELL", 10.03)])
def test_non_marketable_limit_rests(side: str, limit: float) -> None:
    assert at_placement(side, "LMT", QUOTED, limit=limit) is None


def test_resting_limit_fills_at_its_limit_when_a_later_print_touches_it() -> None:
    assert on_print("BUY", "LMT", 9.50, limit=9.50) == Fill(9.50, BASIS_PRINT_CROSS)
    assert on_print("BUY", "LMT", 9.40, limit=9.50) == Fill(9.50, BASIS_PRINT_CROSS)
    assert on_print("BUY", "LMT", 9.51, limit=9.50) is None
    assert on_print("SELL", "LMT", 10.60, limit=10.50) == Fill(10.50, BASIS_PRINT_CROSS)
    assert on_print("SELL", "LMT", 10.49, limit=10.50) is None


def test_stop_rests_then_fills_at_the_triggering_print() -> None:
    assert at_placement("SELL", "STP", QUOTED, stop=9.50) is None
    assert on_print("SELL", "STP", 9.51, stop=9.50) is None
    assert on_print("SELL", "STP", 9.45, stop=9.50) == Fill(9.45, BASIS_STOP_TRIGGER)
    assert on_print("BUY", "STP", 10.55, stop=10.50) == Fill(10.55, BASIS_STOP_TRIGGER)


def test_stop_already_through_the_market_triggers_on_placement() -> None:
    assert at_placement("SELL", "STP", QUOTED, stop=10.10) == Fill(9.98, BASIS_STOP_TRIGGER)
    assert at_placement("BUY", "STP", PRINTS_ONLY, stop=9.90) == Fill(10.00, BASIS_STOP_TRIGGER)
