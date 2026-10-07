"""The short hours and the day cover's clock (ADR 048 1.9 and 5)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from short_sale import hours

ET = ZoneInfo("America/New_York")


def _ts(day: str, hhmm: str) -> float:
    return datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=ET).timestamp()


def test_new_shorts_from_0935_to_1550_on_an_ordinary_day():
    day = "2026-10-07"
    assert "09:35" in hours.entry_refusal(_ts(day, "09:34"))
    assert hours.entry_refusal(_ts(day, "09:35")) is None
    assert hours.entry_refusal(_ts(day, "15:49")) is None
    refused = hours.entry_refusal(_ts(day, "15:50"))
    assert "15:50" in refused and "15:55" in refused


def test_an_early_close_stops_shorts_at_1250_and_covers_at_1255():
    day = "2026-11-27"  # the day after Thanksgiving: the NYSE closes at 13:00
    got = hours.hours_on(_ts(day, "10:00"))
    assert got.half_day
    assert hours.clock(got.last_short_ts) == "12:50" and hours.clock(got.cover_ts) == "12:55"
    assert "early close" in hours.entry_refusal(_ts(day, "12:50"))
    assert not hours.cover_due(_ts(day, "12:54")) and hours.cover_due(_ts(day, "12:55"))


def test_a_short_is_due_its_cover_whenever_the_clock_is_outside_its_hours():
    day = "2026-10-07"
    assert hours.cover_due(_ts(day, "09:00"))       # survived the night
    assert not hours.cover_due(_ts(day, "09:35"))
    assert not hours.cover_due(_ts(day, "15:54"))
    assert hours.cover_due(_ts(day, "15:55"))
    assert hours.cover_due(_ts("2026-10-10", "11:00"))   # a Saturday
    assert hours.hours_on(_ts("2026-11-26", "11:00")) is None  # Thanksgiving
    assert "No session today" in hours.entry_refusal(_ts("2026-10-10", "11:00"))
