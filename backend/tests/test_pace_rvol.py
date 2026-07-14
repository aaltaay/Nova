"""Tests for Warrior-style pace RVOL (Daily Rate)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from market import pace_relative_volume, volume_day_elapsed_fraction

_ET = ZoneInfo("America/New_York")


def test_volume_day_fraction_midday():
    noon = datetime(2026, 7, 14, 12, 0, 0, tzinfo=_ET)
    # 4:00 → 16:00 = 12h; noon is 8h in → 8/12 ≈ 0.667
    assert abs(volume_day_elapsed_fraction(noon) - (8 / 12)) < 0.001


def test_volume_day_fraction_after_close():
    after = datetime(2026, 7, 14, 17, 0, 0, tzinfo=_ET)
    assert volume_day_elapsed_fraction(after) == 1.0


def test_pace_rvol_doubles_raw_at_halfway():
    # At 10:00 ET: 6h of 12h → frac=0.5. today=avg → pace=2.0
    ten = datetime(2026, 7, 14, 10, 0, 0, tzinfo=_ET)
    assert pace_relative_volume(1_000_000, 1_000_000, now=ten) == 2.0


def test_pace_rvol_none_on_bad_inputs():
    assert pace_relative_volume(0, 1000) is None
    assert pace_relative_volume(1000, 0) is None
    assert pace_relative_volume(None, 1000) is None
