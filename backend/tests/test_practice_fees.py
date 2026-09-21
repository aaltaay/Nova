"""IBKR-like practice fees (architecture/practice-account.md, section 2)."""
from __future__ import annotations

import pytest

from constants_practice import (
    PRACTICE_FINRA_TAF_MAX,
    PRACTICE_FINRA_TAF_PER_SHARE,
    PRACTICE_SEC_FEE_RATE,
)
from practice import fees


def test_per_share_rate_never_below_the_one_dollar_minimum() -> None:
    assert fees.commission(100, 10.0) == 1.0  # 100 * 0.005 = 0.50 -> floor 1.00
    assert fees.commission(1000, 10.0) == 5.0


def test_percent_of_value_cap_wins_over_the_minimum_on_a_tiny_order() -> None:
    assert fees.commission(1, 50.0) == 0.5  # 1 % of 50 beats the 1.00 floor, as on IBKR
    assert fees.commission(10, 5.0) == 0.5


def test_sells_pay_sec_and_finra_pass_throughs() -> None:
    charged = fees.for_fill("SELL", 1000, 10.0)
    assert charged.commission == 5.0
    assert charged.sec_fee == pytest.approx(10_000 * PRACTICE_SEC_FEE_RATE)
    assert charged.finra_taf == pytest.approx(1000 * PRACTICE_FINRA_TAF_PER_SHARE)
    assert charged.total == pytest.approx(5.0 + 0.206 + 0.195)


def test_finra_taf_is_capped_per_trade() -> None:
    _sec, taf = fees.regulatory("SELL", 1_000_000, 1.0)
    assert taf == PRACTICE_FINRA_TAF_MAX


def test_buys_pay_commission_only() -> None:
    charged = fees.for_fill("BUY", 1000, 10.0)
    assert (charged.sec_fee, charged.finra_taf) == (0.0, 0.0)
    assert charged.total == 5.0


def test_fees_round_trip_through_their_dict_form() -> None:
    charged = fees.for_fill("SELL", 10, 20.0)
    assert fees.Fees.from_dict(charged.as_dict()) == charged
    assert fees.Fees.from_dict(None) == fees.Fees(0.0)


def test_nothing_is_charged_for_an_empty_fill() -> None:
    assert fees.commission(0, 10.0) == 0.0
    assert fees.commission(10, 0.0) == 0.0
