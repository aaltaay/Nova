"""The practice day rolls at 04:00 ET; stamps are arithmetic, never OS-bound."""
from __future__ import annotations

from datetime import datetime

from practice import clock

ET = clock.ET


def test_the_day_starts_at_four_et_and_the_small_hours_belong_to_the_previous_day() -> None:
    late = datetime(2026, 9, 21, 15, 0, tzinfo=ET).timestamp()
    early = datetime(2026, 9, 22, 3, 59, tzinfo=ET).timestamp()
    boundary = datetime(2026, 9, 22, 4, 0, tzinfo=ET).timestamp()
    assert clock.day_start_ts(late) == datetime(2026, 9, 21, 4, 0, tzinfo=ET).timestamp()
    assert clock.day_start_ts(early) == clock.day_start_ts(late)
    assert clock.day_start_ts(boundary) == boundary


def test_negative_and_near_zero_epochs_do_not_crash_on_windows() -> None:
    assert clock.iso_et(-54_000).startswith("1969-12-31")
    assert clock.day_start_ts(100.0) < 100.0


def test_iso_stamps_carry_their_zone() -> None:
    ts = datetime(2026, 9, 21, 12, 0, tzinfo=ET).timestamp()
    assert clock.iso_et(ts) == "2026-09-21T12:00:00-04:00"
    assert clock.iso_utc(ts) == "2026-09-21T16:00:00+00:00"
