"""UTC calendar dates for yfinance split / earnings epochs."""
from fundamentals import _yf_date_str, format_recent_split


class TestYfDateStr:
    def test_epoch_midnight_utc_not_local_off_by_one(self):
        # LVLU lastSplitDate from yfinance: 2025-07-07 00:00:00 UTC.
        # Local-tz fromtimestamp in US/Eastern painted 2025-07-06.
        assert _yf_date_str(1751846400) == "2025-07-07"

    def test_naive_strftime_object(self):
        class _Ts:
            def strftime(self, fmt):
                return "2025-07-07"

        assert _yf_date_str(_Ts()) == "2025-07-07"

    def test_none(self):
        assert _yf_date_str(None) is None


class TestFormatRecentSplit:
    def test_factor_and_epoch(self):
        assert format_recent_split("1:15", 1751846400) == "1:15 (2025-07-07)"

    def test_factor_only(self):
        assert format_recent_split("1:15", None) == "1:15"

    def test_missing_factor(self):
        assert format_recent_split(None, 1751846400) is None
