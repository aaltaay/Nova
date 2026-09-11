"""UTC calendar dates for yfinance split / earnings epochs."""
import fundamentals
from fundamentals import _yf_date_str, _yf_epoch, format_recent_split


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


class TestYfEpoch:
    def test_int_and_list(self):
        assert _yf_epoch(1785441600) == 1785441600
        assert _yf_epoch([1785441600]) == 1785441600
        assert _yf_epoch(None) is None
        assert _yf_epoch([]) is None
        assert _yf_epoch("nope") is None


class TestFormatRecentSplit:
    def test_factor_and_epoch(self):
        assert format_recent_split("1:15", 1751846400) == "1:15 (2025-07-07)"

    def test_factor_only(self):
        assert format_recent_split("1:15", None) == "1:15"

    def test_missing_factor(self):
        assert format_recent_split(None, 1751846400) is None


def test_fetch_fundamentals_splits_last_and_next_earnings(monkeypatch):
    """earningsTimestamp is last/current event; Start/End is the next date."""
    import fundamentals as fund

    class _Ticker:
        info = {
            "earningsTimestamp": 1785441600,       # 2026-07-30 16:00 ET
            "earningsTimestampStart": 1793304000,  # 2026-10-29 16:00 ET
            "earningsTimestampEnd": 1793304000,
            "isEarningsDateEstimate": False,
        }

    monkeypatch.setattr(fund.yf, "Ticker", lambda _s: _Ticker())
    fund._fundamentals_cache.clear()
    fund._fundamentals_cache_ts.clear()
    fund._fundamentals_cache_ttl.clear()
    out = fund.fetch_fundamentals("AAPL")
    assert out["earnings_ts"] == 1785441600
    assert out["earnings_date"] == "2026-07-30"
    assert out["earnings_next_date"] == "2026-10-29"
    assert out["earnings_estimated"] is False
