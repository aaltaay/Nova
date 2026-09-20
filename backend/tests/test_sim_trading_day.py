"""The exchange calendar's own truth: holidays, observance, boundaries (#386).

Before this, ``NOVA_OS_NYSE_HOLIDAYS`` held ten hand-typed 2026 dates, so every
holiday in any other year silently answered "open". These tests pin the derived
calendar, the loud refusal outside its declared range, and the exact cases the
issue reported.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from constants_nova_os import (
    NOVA_OS_CALENDAR_FIRST_YEAR,
    NOVA_OS_CALENDAR_LAST_YEAR,
    NOVA_OS_NYSE_AD_HOC_CLOSURES,
    NOVA_OS_NYSE_HOLIDAY_NAMES,
    NOVA_OS_NYSE_HOLIDAYS,
    NOVA_OS_NYSE_JUNETEENTH_FIRST_YEAR,
)
from sim.trading_day import UnsupportedCalendarYear, is_trading_day, last_trading_day

# The exact set that shipped as the 2026-only literal in constants_nova_os.py.
SHIPPED_2026 = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
}


def test_independence_day_2025_is_closed_and_its_prior_session_is_july_3():
    """The issue's stated reproduction, verbatim."""
    assert is_trading_day(date(2025, 7, 4)) is False
    assert last_trading_day(date(2025, 7, 4)) == date(2025, 7, 3)
    # The prior session for Monday 2025-07-07 skips both the weekend and Jul 4.
    assert last_trading_day(date(2025, 7, 6)) == date(2025, 7, 3)


def test_derived_2026_matches_the_previously_shipped_literal_exactly():
    """Regression guard: production-year behaviour is unchanged by the rewrite."""
    assert {day for day in NOVA_OS_NYSE_HOLIDAYS if day.startswith("2026")} == SHIPPED_2026


@pytest.mark.parametrize("iso, name", [
    ("2026-07-03", "Independence Day"),   # Sat Jul 4 -> Fri
    ("2020-07-03", "Independence Day"),   # Sat Jul 4 -> Fri
    ("2021-12-24", "Christmas Day"),      # Sat Dec 25 -> Fri
    ("2027-06-18", "Juneteenth"),         # Sat Jun 19 -> Fri
    ("2027-12-24", "Christmas Day"),      # Sat Dec 25 -> Fri
    ("2021-07-05", "Independence Day"),   # Sun Jul 4 -> Mon
    ("2022-12-26", "Christmas Day"),      # Sun Dec 25 -> Mon
    ("2022-06-20", "Juneteenth"),         # Sun Jun 19 -> Mon
    ("2017-01-02", "New Year's Day"),     # Sun Jan 1 -> Mon
    ("2023-01-02", "New Year's Day"),     # Sun Jan 1 -> Mon
])
def test_weekend_holidays_shift_to_the_observed_trading_day(iso, name):
    assert is_trading_day(date.fromisoformat(iso)) is False
    assert NOVA_OS_NYSE_HOLIDAY_NAMES[iso] == name


@pytest.mark.parametrize("year", [2022, 2028, 2033])
def test_a_saturday_new_years_day_is_not_observed_and_december_31_trades(year):
    """The NYSE does not close the preceding Friday for Jan 1 — easy to get wrong."""
    assert date(year, 1, 1).weekday() == 5
    assert is_trading_day(date(year - 1, 12, 31)) is True
    assert "New Year's Day" not in {
        name for iso, name in NOVA_OS_NYSE_HOLIDAY_NAMES.items() if iso.startswith(f"{year}-01")
    }


@pytest.mark.parametrize("iso", ["2023-04-07", "2024-03-29", "2025-04-18",
                                 "2026-04-03", "2027-03-26"])
def test_good_friday_is_closed_although_it_is_not_a_federal_holiday(iso):
    assert is_trading_day(date.fromisoformat(iso)) is False
    assert NOVA_OS_NYSE_HOLIDAY_NAMES[iso] == "Good Friday"


def test_every_derived_good_friday_falls_on_a_friday_in_march_or_april():
    fridays = [date.fromisoformat(iso) for iso, name in NOVA_OS_NYSE_HOLIDAY_NAMES.items()
               if name == "Good Friday"]
    assert len(fridays) == NOVA_OS_CALENDAR_LAST_YEAR - NOVA_OS_CALENDAR_FIRST_YEAR + 1
    assert all(day.weekday() == 4 and day.month in (3, 4) for day in fridays)


def test_juneteenth_starts_the_year_the_exchange_first_observed_it():
    # Federal from 2021, but the NYSE traded 2021-06-18 and first closed in 2022.
    assert NOVA_OS_NYSE_JUNETEENTH_FIRST_YEAR == 2022
    assert is_trading_day(date(2021, 6, 18)) is True
    assert is_trading_day(date(2022, 6, 20)) is False
    assert is_trading_day(date(2025, 6, 19)) is False


@pytest.mark.parametrize("iso", sorted(NOVA_OS_NYSE_AD_HOC_CLOSURES))
def test_ad_hoc_national_days_of_mourning_are_closed(iso):
    assert is_trading_day(date.fromisoformat(iso)) is False
    assert NOVA_OS_NYSE_HOLIDAY_NAMES[iso] == "National day of mourning"


def test_a_plain_weekend_walks_back_to_friday():
    assert last_trading_day(date(2025, 3, 16)) == date(2025, 3, 14)  # Sunday


@pytest.mark.parametrize("day, prior", [
    ("2026-01-01", "2025-12-31"),
    ("2027-01-01", "2026-12-31"),
    ("2023-01-01", "2022-12-30"),  # Sun Jan 1 observed Mon Jan 2; walk past the year edge
])
def test_the_prior_session_crosses_the_year_boundary(day, prior):
    assert last_trading_day(date.fromisoformat(day)) == date.fromisoformat(prior)


@pytest.mark.parametrize("day, prior", [
    ("2025-03-09", "2025-03-07"),  # spring forward
    ("2025-11-02", "2025-10-31"),  # fall back
])
def test_trading_day_selection_is_independent_of_dst(day, prior):
    """Selection is date-based; session length on DST days is out of scope here."""
    assert last_trading_day(date.fromisoformat(day)) == date.fromisoformat(prior)


@pytest.mark.parametrize("year", range(NOVA_OS_CALENDAR_FIRST_YEAR, NOVA_OS_CALENDAR_LAST_YEAR + 1))
def test_every_supported_year_has_the_expected_holiday_shape(year):
    days = sorted(date.fromisoformat(iso) for iso in NOVA_OS_NYSE_HOLIDAYS
                  if iso.startswith(f"{year}-"))
    expected = 10 - (date(year, 1, 1).weekday() == 5) - (year < NOVA_OS_NYSE_JUNETEENTH_FIRST_YEAR)
    expected += sum(date.fromisoformat(iso).year == year for iso in NOVA_OS_NYSE_AD_HOC_CLOSURES)
    assert len(days) == expected
    assert all(day.weekday() < 5 for day in days)   # never lands on a weekend
    assert len(set(days)) == len(days)              # no duplicates or rule collisions


@pytest.mark.parametrize("day", [date(2014, 6, 2), date(2036, 6, 2)])
def test_dates_outside_the_supported_range_refuse_loudly(day):
    """Refusing beats the old silent "open" for a year we cannot vouch for."""
    with pytest.raises(UnsupportedCalendarYear) as excinfo:
        is_trading_day(day)
    message = str(excinfo.value)
    assert str(NOVA_OS_CALENDAR_FIRST_YEAR) in message
    assert str(NOVA_OS_CALENDAR_LAST_YEAR) in message
    assert day.isoformat() in message


def test_the_backward_walk_terminates_at_the_lower_boundary():
    # 2015-01-01 is a holiday and 2014-12-31 is out of range, so the walk must
    # refuse rather than guess or spin.
    with pytest.raises(UnsupportedCalendarYear):
        last_trading_day(date(NOVA_OS_CALENDAR_FIRST_YEAR, 1, 1))


def test_unsupported_calendar_year_is_a_value_error_so_routes_render_422():
    assert issubclass(UnsupportedCalendarYear, ValueError)


def test_the_first_and_last_supported_days_are_answered_not_refused():
    assert is_trading_day(date(NOVA_OS_CALENDAR_FIRST_YEAR, 12, 31)) in (True, False)
    assert is_trading_day(date(NOVA_OS_CALENDAR_LAST_YEAR, 1, 2)) in (True, False)


def test_no_supported_closed_run_is_long_enough_to_need_an_iteration_bound():
    """The longest real closed stretch in range is three days (holiday + weekend)."""
    day, run, longest = date(NOVA_OS_CALENDAR_FIRST_YEAR, 1, 2), 0, 0
    while day <= date(NOVA_OS_CALENDAR_LAST_YEAR, 12, 31):
        run = run + 1 if not is_trading_day(day) else 0
        longest = max(longest, run)
        day += timedelta(days=1)
    assert longest == 3
