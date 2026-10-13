"""Tests for momentum pace RVOL (Daily Rate) on the measured volume curve."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from constants import HOD_MOMO_RVOL_PACE_FLOOR
from market import pace_relative_volume, volume_curve_fraction, volume_day_elapsed_fraction

_ET = ZoneInfo("America/New_York")


def _at(h: int, m: int, s: int = 0) -> datetime:
    return datetime(2026, 7, 14, h, m, s, tzinfo=_ET)


def test_volume_day_fraction_reads_the_measured_curve():
    # Knots: 09:30 -> 0.139, 12:00 -> 0.543, 16:00 -> 0.949 (constants_hod_momo).
    assert abs(volume_day_elapsed_fraction(_at(9, 30)) - 0.139) < 1e-9
    assert abs(volume_day_elapsed_fraction(_at(12, 0)) - 0.543) < 1e-9
    assert abs(volume_day_elapsed_fraction(_at(16, 0)) - 0.949) < 1e-9


def test_volume_day_fraction_interpolates_to_the_second():
    # 08:20 is 20/30 of the way from 08:00 (0.081) to 08:30 (0.109).
    expect = 0.081 + (0.109 - 0.081) * 20 / 30
    assert abs(volume_day_elapsed_fraction(_at(8, 20)) - expect) < 1e-9
    assert volume_day_elapsed_fraction(_at(8, 20, 30)) > volume_day_elapsed_fraction(_at(8, 20))


def test_volume_day_fraction_floor_and_ends():
    assert volume_day_elapsed_fraction(_at(3, 0)) == HOD_MOMO_RVOL_PACE_FLOOR
    assert volume_day_elapsed_fraction(_at(4, 1)) == HOD_MOMO_RVOL_PACE_FLOOR
    assert volume_day_elapsed_fraction(_at(20, 0)) == 1.0
    assert volume_day_elapsed_fraction(_at(22, 0)) == 1.0
    assert volume_curve_fraction(0) == 0.0


def test_premarket_mover_reads_rvol_on_premarket_volume():
    """PFAI, 2026-10-13 08:20:00 ET: 107k shares on a 506k average.

    The straight 04:00-16:00 line expected 36% of the day by 08:20 and read 0.59 -- under the 1.5
    floor until 275k shares traded. On the measured curve (10% by 08:20) it reads over 2.
    """
    rvol = pace_relative_volume(107_000, 505_964, now=datetime(2026, 10, 13, 8, 20, tzinfo=_ET))
    assert rvol is not None and 2.0 < rvol < 2.3


def test_pace_rvol_none_on_bad_inputs():
    assert pace_relative_volume(0, 1000) is None
    assert pace_relative_volume(1000, 0) is None
    assert pace_relative_volume(None, 1000) is None
