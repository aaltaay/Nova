"""IBKR-like practice fees (architecture/practice-account.md, section 2)."""
from __future__ import annotations

from datetime import datetime

import pytest

from constants_practice import (
    PRACTICE_FINRA_CAT_PER_SHARE,
    PRACTICE_FINRA_TAF_MAX,
    PRACTICE_FINRA_TAF_PER_SHARE,
    PRACTICE_SEC_FEE_RATE,
)
from practice import fees
from practice.clock import ET

SEPT_30 = datetime(2026, 9, 30, 15, 59, tzinfo=ET).timestamp()


def _et(*parts: int) -> float:
    return datetime(*parts, tzinfo=ET).timestamp()


def test_per_share_rate_never_below_the_one_dollar_minimum() -> None:
    assert fees.commission(100, 10.0) == 1.0  # 100 * 0.005 = 0.50 -> floor 1.00
    assert fees.commission(1000, 10.0) == 5.0


def test_percent_of_value_cap_wins_over_the_minimum_on_a_tiny_order() -> None:
    assert fees.commission(1, 50.0) == 0.5  # 1 % of 50 beats the 1.00 floor, as on IBKR
    assert fees.commission(10, 5.0) == 0.5


def test_sells_pay_sec_and_finra_pass_throughs() -> None:
    charged = fees.for_fill("SELL", 1000, 10.0, SEPT_30)
    assert charged.commission == 5.0
    assert charged.sec_fee == pytest.approx(10_000 * PRACTICE_SEC_FEE_RATE)
    assert charged.finra_taf == pytest.approx(1000 * PRACTICE_FINRA_TAF_PER_SHARE)
    assert charged.finra_cat == pytest.approx(1000 * PRACTICE_FINRA_CAT_PER_SHARE)
    assert charged.total == pytest.approx(5.0 + 0.206 + 0.195 + 0.003)


def test_finra_taf_holiday_covers_trade_dates_october_through_december_2026() -> None:
    """SR-FINRA-2026-021: no TAF Oct 1 - Dec 31, 2026, both days included, by Eastern trade date."""
    for ts in (_et(2026, 10, 1, 0, 0), _et(2026, 10, 2, 8, 52), _et(2026, 12, 31, 19, 59)):
        assert fees.taf_holiday(ts)
        assert fees.for_fill("SELL", 100, 2.62, ts).finra_taf == 0.0
    for ts in (_et(2026, 9, 30, 23, 59), _et(2027, 1, 1, 4, 0)):
        assert not fees.taf_holiday(ts)
        assert fees.for_fill("SELL", 100, 2.62, ts).finra_taf == pytest.approx(100 * PRACTICE_FINRA_TAF_PER_SHARE)


def test_the_sec_fee_and_cat_are_not_paused_with_the_taf() -> None:
    charged = fees.for_fill("SELL", 100, 2.62, _et(2026, 10, 2, 8, 52))
    assert charged.sec_fee == pytest.approx(262 * PRACTICE_SEC_FEE_RATE, abs=1e-6)  # rounded to 6 places
    assert charged.finra_cat == pytest.approx(100 * PRACTICE_FINRA_CAT_PER_SHARE)
    assert charged.total == pytest.approx(1.0 + 0.005397 + 0.0003)


def test_an_unknown_trade_time_pays_the_standing_taf() -> None:
    assert not fees.taf_holiday(None)
    assert fees.for_fill("SELL", 100, 2.62).finra_taf == pytest.approx(100 * PRACTICE_FINRA_TAF_PER_SHARE)


def test_finra_taf_is_capped_per_trade() -> None:
    _sec, taf = fees.regulatory("SELL", 1_000_000, 1.0)
    assert taf == PRACTICE_FINRA_TAF_MAX


def test_buys_pay_commission_and_cat_only() -> None:
    charged = fees.for_fill("BUY", 1000, 10.0, SEPT_30)
    assert (charged.sec_fee, charged.finra_taf) == (0.0, 0.0)
    assert charged.finra_cat == pytest.approx(0.003)
    assert charged.total == pytest.approx(5.003)


def test_cat_matches_a_live_ibkr_fill() -> None:
    """IBKR charged a 1-share Live buy of IMCC at 7.38 exactly 0.073803: the 1 % cap plus CAT."""
    assert fees.for_fill("BUY", 1, 7.38, SEPT_30).total == pytest.approx(0.073803)


def test_fees_round_trip_through_their_dict_form() -> None:
    charged = fees.for_fill("SELL", 10, 20.0, SEPT_30)
    assert fees.Fees.from_dict(charged.as_dict()) == charged
    assert fees.Fees.from_dict(None) == fees.Fees(0.0)


def test_a_fill_stored_before_cat_keeps_what_it_was_charged() -> None:
    stored = {"commission": 1.0, "sec_fee": 0.0054, "finra_taf": 0.0195, "total": 1.0249}
    read = fees.Fees.from_dict(stored)
    assert read.finra_cat == 0.0 and read.total == pytest.approx(1.0249)


def test_nothing_is_charged_for_an_empty_fill() -> None:
    assert fees.commission(0, 10.0) == 0.0
    assert fees.commission(10, 0.0) == 0.0
    assert fees.for_fill("BUY", 10, 0.0, SEPT_30).total == 0.0
