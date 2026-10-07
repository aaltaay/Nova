"""NYSE early closes (13:00 ET), derived by rule (ADR 048: the day cover runs at 12:55 on them).

Pinned against the published NYSE calendars, so the rule is checked against something other than
itself.
"""
from __future__ import annotations

from constants_nova_os import (
    NOVA_OS_CALENDAR_FIRST_YEAR,
    NOVA_OS_CALENDAR_LAST_YEAR,
    NOVA_OS_NYSE_EARLY_CLOSES,
    NOVA_OS_NYSE_HOLIDAYS,
)

# The published NYSE early closes, 2015-2026.
PUBLISHED = {
    2015: {"2015-11-27", "2015-12-24"},
    2016: {"2016-11-25"},
    2017: {"2017-07-03", "2017-11-24"},
    2018: {"2018-07-03", "2018-11-23", "2018-12-24"},
    2019: {"2019-07-03", "2019-11-29", "2019-12-24"},
    2020: {"2020-11-27", "2020-12-24"},
    2021: {"2021-11-26"},
    2022: {"2022-11-25"},
    2023: {"2023-07-03", "2023-11-24"},
    2024: {"2024-07-03", "2024-11-29", "2024-12-24"},
    2025: {"2025-07-03", "2025-11-28", "2025-12-24"},
    2026: {"2026-11-27", "2026-12-24"},
}


def test_every_published_early_close_and_no_other():
    for year, days in PUBLISHED.items():
        derived = {d for d in NOVA_OS_NYSE_EARLY_CLOSES if d.startswith(f"{year}-")}
        assert derived == days, year


def test_an_early_close_is_never_a_holiday_and_the_range_is_covered():
    assert not NOVA_OS_NYSE_EARLY_CLOSES & NOVA_OS_NYSE_HOLIDAYS
    years = {int(d[:4]) for d in NOVA_OS_NYSE_EARLY_CLOSES}
    assert set(range(NOVA_OS_CALENDAR_FIRST_YEAR, NOVA_OS_CALENDAR_LAST_YEAR + 1)) <= years
