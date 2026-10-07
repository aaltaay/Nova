"""LULD rules (ADR 047): the Plan's percentage parameters, the bands' rounding, hours, tier and coverage."""
from __future__ import annotations

from datetime import datetime
from fractions import Fraction
from zoneinfo import ZoneInfo

import pytest

from luld import rules

ET = ZoneInfo("America/New_York")


def ts(day: str, hhmmss: str) -> float:
    return datetime.fromisoformat(f"{day}T{hhmmss}").replace(tzinfo=ET).timestamp()


def band(ref: str, prev: float, tier: int | None = 2, closing: bool = False):
    param = rules.parameter(prev, tier, closing=closing)
    assert param is not None
    lo, up = rules.bands(Fraction(ref), param)
    return (float(lo) if lo is not None else None), float(up)


@pytest.mark.parametrize(("prev", "tier", "closing", "kind", "pct"), [
    (5.00, 2, False, "pct", "0.1"),
    (5.00, 1, False, "pct", "0.05"),
    (5.00, 2, True, "pct", "0.1"),     # Amendment 18: no doubling for Tier 2 over $3
    (5.00, 1, True, "pct", "0.1"),     # Tier 1 doubles at the close
    (3.00, None, False, "pct", "0.2"),  # "up to and including $3.00"
    (0.75, None, False, "pct", "0.2"),
    (2.00, None, True, "pct", "0.4"),
    (0.74, None, False, "low", "0.75"),
    (0.50, None, True, "low", "1.5"),
])
def test_percentage_parameter_by_previous_close(prev, tier, closing, kind, pct):
    param = rules.parameter(prev, tier, closing=closing)
    assert param is not None and param.kind == kind and param.pct == Fraction(pct)


def test_the_tier_is_needed_only_over_three_dollars():
    assert rules.parameter(5.0, None, closing=False) is None
    assert rules.parameter(None, 2, closing=False) is None
    assert rules.tier_needed(3.01) and not rules.tier_needed(3.00) and not rules.tier_needed(None)


def test_bands_round_half_up_to_the_penny():
    # GRML 2026-09-22 reopened at 15.75 and paused 27 s later at 14.18 (14.175 rounded up).
    assert band("15.75", 10.85) == (14.18, 17.33)
    assert band("10.00", 9.0) == (9.0, 11.0)


def test_the_low_priced_rule_takes_the_lesser_of_dollars_and_percent():
    assert band("0.50", 0.5, None) == (0.35, 0.65)          # 15c, less than 75% (37.5c)
    assert band("0.10", 0.1, None) == (0.03, 0.18)          # 7.5c (75%) less than 15c, rounded half up
    # At the close the lower band falls under a cent: there is none.
    assert band("0.10", 0.1, None, closing=True) == (None, 0.25)


def test_parameter_words():
    assert rules.parameter(5.0, 2, closing=False).text() == "10%"
    assert "doubled" in rules.parameter(2.0, None, closing=True).text()
    assert rules.parameter(0.5, None, closing=False).text().startswith("the lesser of $0.15")


def test_regular_hours_on_an_exchange_day_only():
    bounds = rules.rth_bounds(ts("2026-09-22", "12:00:00"))
    assert bounds == (ts("2026-09-22", "09:30:00"), ts("2026-09-22", "16:00:00"))
    assert rules.rth_bounds(ts("2026-09-26", "12:00:00")) is None   # a Saturday
    assert rules.closing_at(ts("2026-09-22", "10:00:00")) == ts("2026-09-22", "15:35:00")


def test_tier_from_the_company_size():
    assert rules.tier_from_size(20e9)[::2] == (1, True)
    assert rules.tier_from_size(300e6)[::2] == (2, True)
    assert rules.tier_from_size(6e9)[::2] == (1, False)      # probably in the Russell 1000
    assert rules.tier_from_size(3e9)[::2] == (2, False)
    tier, why, sure = rules.tier_from_size(None)
    assert (tier, sure) == (2, False) and "assumed" in why


@pytest.mark.parametrize(("symbol", "stock_type", "covered"), [
    ("AAPL", None, True),
    ("ADTHW", None, False),        # a Nasdaq fifth-letter warrant
    ("ABCDR", None, False),        # a right
    ("ABC WS", None, False),
    ("ABCDW", "COMMON", True),     # IBKR's stock type decides when known
    ("XYZ", "WAR", False),
])
def test_rights_and_warrants_are_not_covered(symbol, stock_type, covered):
    assert rules.covered(symbol, stock_type)[0] is covered
