"""The exchange calendar's own truth: holidays, observance, boundaries (#386).

Before this, ``NOVA_OS_NYSE_HOLIDAYS`` held ten hand-typed 2026 dates, so every
holiday in any other year silently answered "open". These tests pin the derived
calendar against an independently entered table, the two documented behaviours
at the range edges (refuse for operator input, degrade for derived dates), and
the shared Nova OS consumers that read the same table.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from constants_nova_os import (
    NOVA_OS_CALENDAR_FIRST_YEAR,
    NOVA_OS_CALENDAR_LAST_YEAR,
    NOVA_OS_CALENDAR_TABLE_FIRST_YEAR,
    NOVA_OS_NYSE_AD_HOC_CLOSURES,
    NOVA_OS_NYSE_HOLIDAY_NAMES,
    NOVA_OS_NYSE_HOLIDAYS,
    NOVA_OS_NYSE_JUNETEENTH_FIRST_YEAR,
)
from sim.trading_day import (
    UnsupportedCalendarYear,
    is_supported,
    is_trading_day,
    last_open_day,
    last_trading_day,
    require_supported,
)

ET = ZoneInfo("America/New_York")

# The exact set that shipped as the 2026-only literal in constants_nova_os.py.
SHIPPED_2026 = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
}

# Every full-day NYSE closure in the table's range, entered by hand from the
# published NYSE calendars (2015-2027 are published; 2028-2035 were written out
# from the observance rules plus the standard Easter table, NOT read back out of
# constants_nova_os). This is the independent source the derivation is checked
# against: a wrong Easter, a wrong "nth weekday", a missed Saturday observance
# or a Juneteenth that starts in the wrong year all show up as a diff here.
PUBLISHED_CLOSURES = {
    2014: ("01-01", "01-20", "02-17", "04-18", "05-26", "07-04", "09-01", "11-27", "12-25"),
    2015: ("01-01", "01-19", "02-16", "04-03", "05-25", "07-03", "09-07", "11-26", "12-25"),
    2016: ("01-01", "01-18", "02-15", "03-25", "05-30", "07-04", "09-05", "11-24", "12-26"),
    2017: ("01-02", "01-16", "02-20", "04-14", "05-29", "07-04", "09-04", "11-23", "12-25"),
    2018: ("01-01", "01-15", "02-19", "03-30", "05-28", "07-04", "09-03", "11-22", "12-05", "12-25"),
    2019: ("01-01", "01-21", "02-18", "04-19", "05-27", "07-04", "09-02", "11-28", "12-25"),
    2020: ("01-01", "01-20", "02-17", "04-10", "05-25", "07-03", "09-07", "11-26", "12-25"),
    2021: ("01-01", "01-18", "02-15", "04-02", "05-31", "07-05", "09-06", "11-25", "12-24"),
    2022: ("01-17", "02-21", "04-15", "05-30", "06-20", "07-04", "09-05", "11-24", "12-26"),
    2023: ("01-02", "01-16", "02-20", "04-07", "05-29", "06-19", "07-04", "09-04", "11-23", "12-25"),
    2024: ("01-01", "01-15", "02-19", "03-29", "05-27", "06-19", "07-04", "09-02", "11-28", "12-25"),
    2025: ("01-01", "01-09", "01-20", "02-17", "04-18", "05-26", "06-19", "07-04", "09-01", "11-27",
           "12-25"),
    2026: ("01-01", "01-19", "02-16", "04-03", "05-25", "06-19", "07-03", "09-07", "11-26", "12-25"),
    2027: ("01-01", "01-18", "02-15", "03-26", "05-31", "06-18", "07-05", "09-06", "11-25", "12-24"),
    2028: ("01-17", "02-21", "04-14", "05-29", "06-19", "07-04", "09-04", "11-23", "12-25"),
    2029: ("01-01", "01-15", "02-19", "03-30", "05-28", "06-19", "07-04", "09-03", "11-22", "12-25"),
    2030: ("01-01", "01-21", "02-18", "04-19", "05-27", "06-19", "07-04", "09-02", "11-28", "12-25"),
    2031: ("01-01", "01-20", "02-17", "04-11", "05-26", "06-19", "07-04", "09-01", "11-27", "12-25"),
    2032: ("01-01", "01-19", "02-16", "03-26", "05-31", "06-18", "07-05", "09-06", "11-25", "12-24"),
    2033: ("01-17", "02-21", "04-15", "05-30", "06-20", "07-04", "09-05", "11-24", "12-26"),
    2034: ("01-02", "01-16", "02-20", "04-07", "05-29", "06-19", "07-04", "09-04", "11-23", "12-25"),
    2035: ("01-01", "01-15", "02-19", "03-23", "05-28", "06-19", "07-04", "09-03", "11-22", "12-25"),
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


@pytest.mark.parametrize("year", sorted(PUBLISHED_CLOSURES))
def test_every_derived_date_matches_the_hand_entered_nyse_calendar(year):
    """The derivation is checked against a source outside the implementation."""
    derived = sorted(iso for iso in NOVA_OS_NYSE_HOLIDAYS if iso.startswith(f"{year}-"))
    assert derived == [f"{year}-{day}" for day in PUBLISHED_CLOSURES[year]]


def test_the_hand_entered_table_covers_exactly_the_derived_range():
    """A widened range with no new literals would otherwise pass unchecked."""
    assert sorted(PUBLISHED_CLOSURES) == list(
        range(NOVA_OS_CALENDAR_TABLE_FIRST_YEAR, NOVA_OS_CALENDAR_LAST_YEAR + 1))
    assert sum(len(days) for days in PUBLISHED_CLOSURES.values()) == len(NOVA_OS_NYSE_HOLIDAYS)


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
    assert len(fridays) == NOVA_OS_CALENDAR_LAST_YEAR - NOVA_OS_CALENDAR_TABLE_FIRST_YEAR + 1
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


@pytest.mark.parametrize("year", range(NOVA_OS_CALENDAR_TABLE_FIRST_YEAR,
                                       NOVA_OS_CALENDAR_LAST_YEAR + 1))
def test_no_derived_closure_lands_on_a_weekend_or_repeats(year):
    days = sorted(date.fromisoformat(iso) for iso in NOVA_OS_NYSE_HOLIDAYS
                  if iso.startswith(f"{year}-"))
    assert all(day.weekday() < 5 for day in days)   # never lands on a weekend
    assert len(set(days)) == len(days)              # no duplicates or rule collisions


# ── Range edges: refuse what the operator typed, degrade what Nova derived ────

@pytest.mark.parametrize("day", [date(2014, 6, 2), date(2036, 6, 2)])
def test_dates_outside_the_supported_range_refuse_loudly(day):
    """Refusing beats the old silent "open" for a year we cannot vouch for."""
    for call in (is_trading_day, last_trading_day, require_supported):
        with pytest.raises(UnsupportedCalendarYear) as excinfo:
            call(day)
        message = str(excinfo.value)
        assert str(NOVA_OS_CALENDAR_FIRST_YEAR) in message
        assert str(NOVA_OS_CALENDAR_LAST_YEAR) in message
        assert day.isoformat() in message
    assert is_supported(day) is False


def test_the_refusal_text_does_not_leak_nova_source_paths_to_the_operator():
    """This string is rendered straight into a 422 body."""
    with pytest.raises(UnsupportedCalendarYear) as excinfo:
        require_supported(date(2036, 6, 2))
    message = str(excinfo.value)
    assert ".py" not in message and "backend/" not in message
    assert message == "2036-06-02 is outside the supported exchange calendar 2015-2035"


@pytest.mark.parametrize("day, prior", [
    # The first supported day is inside the range, so it must answer, not raise:
    # the walk steps into the table's margin year (#386 finding 8).
    (date(NOVA_OS_CALENDAR_FIRST_YEAR, 1, 1), date(2014, 12, 31)),
    (date(NOVA_OS_CALENDAR_FIRST_YEAR, 1, 2), date(2015, 1, 2)),
    (date(NOVA_OS_CALENDAR_LAST_YEAR, 12, 31), date(2035, 12, 31)),
])
def test_an_in_range_date_never_raises_even_at_the_lower_edge(day, prior):
    assert is_supported(day) is True
    assert last_trading_day(day) == prior


def test_the_first_and_last_supported_days_are_answered_not_refused():
    assert is_trading_day(date(NOVA_OS_CALENDAR_FIRST_YEAR, 1, 1)) is False   # Thu, New Year's
    assert is_trading_day(date(NOVA_OS_CALENDAR_FIRST_YEAR, 1, 2)) is True    # Fri, traded
    assert is_trading_day(date(NOVA_OS_CALENDAR_FIRST_YEAR, 12, 31)) is True  # Thu, traded
    assert is_trading_day(date(NOVA_OS_CALENDAR_LAST_YEAR, 1, 1)) is False    # Mon, New Year's
    assert is_trading_day(date(NOVA_OS_CALENDAR_LAST_YEAR, 12, 31)) is True   # Mon, traded


@pytest.mark.parametrize("day, expected", [
    (date(1970, 1, 5), date(1970, 1, 5)),    # Monday: a container booted at the epoch
    (date(1970, 1, 4), date(1970, 1, 2)),    # Sunday: the weekday rule still applies
    (date(2036, 6, 2), date(2036, 6, 2)),    # past the range: answers, does not refuse
    (date(2036, 7, 4), date(2036, 7, 4)),    # Friday Jul 4 2036 — unvouched, so "open"
])
def test_last_open_day_degrades_instead_of_refusing_for_derived_dates(day, expected, caplog):
    """Wall-clock callers sit under routes with no ValueError mapping (500, not 422)."""
    import logging
    with caplog.at_level(logging.WARNING):
        assert last_open_day(day) == expected
    assert "outside the supported exchange calendar" in caplog.text


def test_last_open_day_is_the_vouched_calendar_inside_the_range(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        assert last_open_day(date(2025, 7, 4)) == date(2025, 7, 3)
        assert last_open_day(date(2025, 7, 6)) == date(2025, 7, 3)
    assert caplog.text == ""


def test_unsupported_calendar_year_is_a_value_error_so_routes_render_422():
    assert issubclass(UnsupportedCalendarYear, ValueError)


def test_no_supported_closed_run_is_long_enough_to_need_an_iteration_bound():
    """The longest real closed stretch in range is three days (holiday + weekend)."""
    day, run, longest = date(NOVA_OS_CALENDAR_TABLE_FIRST_YEAR, 1, 2), 0, 0
    while day <= date(NOVA_OS_CALENDAR_LAST_YEAR, 12, 31):
        run = run + 1 if day.isoformat() in NOVA_OS_NYSE_HOLIDAYS or day.weekday() >= 5 else 0
        longest = max(longest, run)
        day += timedelta(days=1)
    assert longest == 3


# ── Shared Nova OS consumers of the same table (issue NEXT item 2) ────────────
# gates.is_nyse_holiday, flatten_exit.flatten_needs_extended_hours and the Sim
# session clock all read NOVA_OS_NYSE_HOLIDAYS. All three answered "open" on
# every non-2026 holiday before #386; nothing pinned them.

@pytest.mark.parametrize("iso, holiday", [
    ("2025-07-04", True), ("2025-07-03", False),   # the issue's year
    ("2019-12-25", True), ("2019-12-26", False),   # far below the once-hardcoded year
    ("2032-05-31", True), ("2032-06-01", False),   # far above it
])
def test_gate_zero_sees_every_year_of_holidays(iso, holiday):
    from nova_os.gates import is_nyse_holiday, session_allows_trading
    noon = datetime.combine(date.fromisoformat(iso), datetime.min.time(), tzinfo=ET).replace(hour=12)
    assert is_nyse_holiday(noon) is holiday
    # Gate 0 reads the same table, so a holiday closes the session window too.
    assert session_allows_trading(noon) is (not holiday)


@pytest.mark.parametrize("iso, extended", [
    ("2025-07-04", True), ("2025-07-03", False),
    ("2031-01-01", True), ("2031-01-02", False),
])
def test_flatten_routes_through_extended_hours_on_holidays_in_any_year(iso, extended):
    from execution.flatten_exit import flatten_needs_extended_hours_unpatched
    noon = datetime.combine(date.fromisoformat(iso), datetime.min.time(), tzinfo=ET).replace(hour=12)
    assert flatten_needs_extended_hours_unpatched(noon) is extended


@pytest.mark.parametrize("iso, session", [
    ("2025-07-04", "2025-07-03"),   # Independence Day replays Thursday
    ("2025-07-05", "2025-07-03"),   # Saturday, back across the holiday
    ("2019-12-25", "2019-12-24"),   # a year the old table knew nothing about
    ("2036-07-04", "2036-07-04"),   # unvouched year: degraded, never a 500
])
def test_the_sim_session_falls_back_to_a_real_open_day_in_every_year(iso, session):
    from sim import session_clock as clock
    clock.reset_for_tests()
    try:
        noon = datetime.combine(date.fromisoformat(iso), datetime.min.time(), tzinfo=ET).replace(hour=12)
        start, end = clock.session_bounds_on(noon)
        assert start.date().isoformat() == session
        assert (end - start).total_seconds() == 16 * 60 * 60
    finally:
        clock.reset_for_tests()


def test_early_close_half_days_are_not_modelled_and_open_a_full_session():
    """A documented non-goal, pinned so it cannot change without a decision.

    The Friday after Thanksgiving closes at 13:00 ET. Nova's table holds full-day
    closures only, so the day is a normal trading day and session bounds run the
    full 04:00-20:00 — a replay of it looks live with an empty tape after 13:00.
    Modelling half-days means an early-close table plus a session-bounds change
    in every consumer; see the sim/trading_day.py docstring.
    """
    from sim import session_clock as clock
    half_day = date(2025, 11, 28)
    assert is_trading_day(half_day) is True
    clock.reset_for_tests()
    try:
        noon = datetime.combine(half_day, datetime.min.time(), tzinfo=ET).replace(hour=12)
        start, end = clock.session_bounds_on(noon)
        assert (start.hour, end.hour) == (4, 20)
    finally:
        clock.reset_for_tests()
