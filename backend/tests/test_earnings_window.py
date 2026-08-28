"""Yahoo earnings-day window: offset, session, and ET date helpers."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import earnings_window as ew

ET = ZoneInfo("America/New_York")


def _ts(y, m, d, hh, mm=0) -> int:
    return int(datetime(y, m, d, hh, mm, tzinfo=ET).timestamp())


NOW = datetime(2026, 8, 27, 10, 0, tzinfo=ET)


def test_offset_today_tomorrow_yesterday():
    assert ew.earnings_day_offset(_ts(2026, 8, 27, 16, 0), now_et=NOW) == 0
    assert ew.earnings_day_offset(_ts(2026, 8, 28, 8, 30), now_et=NOW) == 1
    assert ew.earnings_day_offset(_ts(2026, 8, 26, 16, 0), now_et=NOW) == -1


def test_offset_outside_one_day_window_is_none():
    assert ew.earnings_day_offset(_ts(2026, 8, 25, 16, 0), now_et=NOW) is None
    assert ew.earnings_day_offset(_ts(2026, 8, 29, 8, 30), now_et=NOW) is None


def test_offset_none_and_unparseable():
    assert ew.earnings_day_offset(None, now_et=NOW) is None
    assert ew.earnings_day_offset("not-a-ts", now_et=NOW) is None


def test_offset_falls_back_to_earnings_date_string():
    assert ew.earnings_day_offset(None, earnings_date="2026-08-27", now_et=NOW) == 0
    assert ew.earnings_day_offset(None, earnings_date="2026-08-25", now_et=NOW) is None
    assert ew.earnings_day_offset(None, earnings_date="bad", now_et=NOW) is None


def test_session_bmo_amc_intraday():
    assert ew.earnings_session(_ts(2026, 8, 27, 8, 30)) == "bmo"
    assert ew.earnings_session(_ts(2026, 8, 27, 16, 0)) == "amc"
    assert ew.earnings_session(_ts(2026, 8, 27, 12, 0)) == "intraday"
    assert ew.earnings_session(None) is None


def test_session_open_and_close_boundaries():
    assert ew.earnings_session(_ts(2026, 8, 27, 9, 29)) == "bmo"
    assert ew.earnings_session(_ts(2026, 8, 27, 9, 30)) == "intraday"
    assert ew.earnings_session(_ts(2026, 8, 27, 15, 59)) == "intraday"
    assert ew.earnings_session(_ts(2026, 8, 27, 16, 0)) == "amc"


def test_et_midnight_uses_calendar_day_not_utc():
    just_after_midnight = datetime(2026, 8, 27, 0, 1, tzinfo=ET)
    assert ew.earnings_day_offset(_ts(2026, 8, 26, 16, 0), now_et=just_after_midnight) == -1
    assert ew.earnings_day_offset(_ts(2026, 8, 27, 8, 30), now_et=just_after_midnight) == 0


def test_earnings_date_et():
    assert ew.earnings_date_et(_ts(2026, 8, 27, 16, 0)) == "2026-08-27"
    assert ew.earnings_date_et(_ts(2026, 11, 19, 8, 30)) == "2026-11-19"
    assert ew.earnings_date_et(None) is None
