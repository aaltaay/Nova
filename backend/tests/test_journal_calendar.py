"""Hard numeric tests for journal calendar day/month/year P&L aggregation."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from journal.calendar import (
    aggregate_daily_pnl,
    build_month_calendar,
    build_year_calendar,
    day_result,
    et_date_from_ts,
)

_ET = ZoneInfo("America/New_York")


def _ts(year: int, month: int, day: int, hour: int = 12) -> float:
    return datetime(year, month, day, hour, 0, 0, tzinfo=_ET).timestamp()


def _trade(pnl: float, closed_ts: float, *, opened_ts: float | None = None) -> dict:
    return {
        "pnl": pnl,
        "closed_ts": closed_ts,
        "opened_ts": opened_ts if opened_ts is not None else closed_ts - 600,
        "symbol": "TEST",
    }


class TestDayResult:
    def test_win_loss_flat(self):
        assert day_result(1.0) == "win"
        assert day_result(-0.01) == "loss"
        assert day_result(0.0) == "flat"


class TestEtDateFromTs:
    def test_utc_evening_is_next_et_day(self):
        # 2026-07-10 23:30 UTC = 2026-07-10 19:30 ET (EDT)
        utc = datetime(2026, 7, 10, 23, 30, tzinfo=__import__("datetime").timezone.utc)
        assert et_date_from_ts(utc.timestamp()).isoformat() == "2026-07-10"

    def test_utc_early_morning_is_previous_et_day(self):
        # 2026-07-11 03:30 UTC = 2026-07-10 23:30 ET
        utc = datetime(2026, 7, 11, 3, 30, tzinfo=__import__("datetime").timezone.utc)
        assert et_date_from_ts(utc.timestamp()).isoformat() == "2026-07-10"


class TestAggregateDailyPnl:
    def test_same_day_sum_and_count(self):
        trades = [
            _trade(50.0, _ts(2026, 7, 11)),
            _trade(-20.0, _ts(2026, 7, 11, 15)),
            _trade(10.25, _ts(2026, 7, 11, 16)),
        ]
        daily = aggregate_daily_pnl(trades)
        assert list(daily.keys()) == ["2026-07-11"]
        assert daily["2026-07-11"]["pnl"] == 40.25
        assert daily["2026-07-11"]["trade_count"] == 3
        assert daily["2026-07-11"]["result"] == "win"

    def test_loss_day(self):
        trades = [_trade(-15.0, _ts(2026, 3, 5)), _trade(-5.0, _ts(2026, 3, 5))]
        daily = aggregate_daily_pnl(trades)
        assert daily["2026-03-05"]["pnl"] == -20.0
        assert daily["2026-03-05"]["result"] == "loss"

    def test_flat_day_exactly_zero(self):
        trades = [_trade(10.0, _ts(2026, 1, 2)), _trade(-10.0, _ts(2026, 1, 2))]
        daily = aggregate_daily_pnl(trades)
        assert daily["2026-01-02"]["pnl"] == 0.0
        assert daily["2026-01-02"]["result"] == "flat"

    def test_skips_open_trades_without_pnl(self):
        trades = [
            {"pnl": None, "closed_ts": None, "opened_ts": _ts(2026, 7, 1)},
            _trade(5.0, _ts(2026, 7, 1)),
        ]
        daily = aggregate_daily_pnl(trades)
        assert daily["2026-07-01"]["trade_count"] == 1
        assert daily["2026-07-01"]["pnl"] == 5.0

    def test_penny_rounding_stable(self):
        trades = [
            _trade(0.1, _ts(2026, 4, 1)),
            _trade(0.2, _ts(2026, 4, 1)),
        ]
        daily = aggregate_daily_pnl(trades)
        assert daily["2026-04-01"]["pnl"] == 0.3


class TestYearMonthRollups:
    def test_month_equals_sum_of_days(self):
        trades = [
            _trade(100.0, _ts(2026, 7, 1)),
            _trade(-40.0, _ts(2026, 7, 2)),
            _trade(25.5, _ts(2026, 7, 15)),
            _trade(10.0, _ts(2026, 6, 30)),  # other month
        ]
        month = build_month_calendar(trades, 2026, 7)
        day_sum = round(sum(d["pnl"] for d in month["days"]), 2)
        assert month["pnl"] == 85.5
        assert day_sum == 85.5
        assert month["trade_count"] == 3
        assert month["winning_days"] == 2
        assert month["losing_days"] == 1
        assert len(month["days"]) == 31  # full July grid
        assert len(month["weeks"]) >= 5

    def test_year_equals_sum_of_months(self):
        trades = [
            _trade(50.0, _ts(2026, 1, 5)),
            _trade(-20.0, _ts(2026, 2, 10)),
            _trade(30.0, _ts(2026, 2, 11)),
            _trade(100.0, _ts(2025, 12, 31)),  # prior year ignored
        ]
        year = build_year_calendar(trades, 2026)
        assert year["year_pnl"] == 60.0
        assert year["year_trade_count"] == 3
        assert round(sum(m["pnl"] for m in year["months"]), 2) == 60.0
        assert year["winning_days"] == 2
        assert year["losing_days"] == 1
        assert year["best_day"]["date"] == "2026-01-05"
        assert year["best_day"]["pnl"] == 50.0
        assert year["worst_day"]["date"] == "2026-02-10"
        assert year["worst_day"]["pnl"] == -20.0
        assert year["months"][0]["month"] == 1
        assert year["months"][0]["pnl"] == 50.0
        assert year["months"][1]["pnl"] == 10.0

    def test_empty_year(self):
        year = build_year_calendar([], 2026)
        assert year["year_pnl"] == 0.0
        assert year["year_trade_count"] == 0
        assert year["best_day"] is None
        assert year["worst_day"] is None
        assert all(m["pnl"] == 0.0 and m["trade_count"] == 0 for m in year["months"])

    def test_week_totals_match_in_month_days(self):
        trades = [
            _trade(10.0, _ts(2026, 1, 5)),   # Monday
            _trade(20.0, _ts(2026, 1, 6)),
            _trade(-5.0, _ts(2026, 1, 12)),
        ]
        month = build_month_calendar(trades, 2026, 1)
        week_pnl_sum = round(sum(w["pnl"] for w in month["weeks"]), 2)
        assert week_pnl_sum == month["pnl"] == 25.0


class TestCalendarRouteIntegration:
    @pytest.fixture(autouse=True)
    def isolated_db(self, tmp_path, monkeypatch):
        import journal.db as db

        monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
        db.init_db()
        yield

    def test_endpoint_excludes_mock_by_default(self):
        from journal.store import record_trade
        from routes.journal import journal_calendar

        record_trade(
            symbol="REAL", setup="gap_and_go", side="long", qty=10,
            entry_price=1.0, stop_price=0.9, target_price=1.2,
            exit_price=1.2, pnl=20.0, adherent=True,
            opened_ts=_ts(2026, 7, 11), closed_ts=_ts(2026, 7, 11),
            is_mock=False,
        )
        record_trade(
            symbol="MOCK", setup="gap_and_go", side="long", qty=10,
            entry_price=1.0, stop_price=0.9, target_price=1.2,
            exit_price=1.2, pnl=999.0, adherent=True,
            opened_ts=_ts(2026, 7, 11), closed_ts=_ts(2026, 7, 11),
            is_mock=True,
        )
        real = journal_calendar(year=2026, month=None, include_mock=False)
        assert real["year_pnl"] == 20.0
        assert real["includes_mock_data"] is False
        with_mock = journal_calendar(year=2026, month=None, include_mock=True)
        assert with_mock["year_pnl"] == 1019.0
        assert with_mock["includes_mock_data"] is True
