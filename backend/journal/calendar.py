"""
Journal P&L calendar aggregates (TraderVue-style year/month day buckets).

Pure functions over closed trade dicts. Calendar days use America/New_York
so US equity session days match the trader's mental model. Bucket key is
closed_ts (realized P&L day), not opened_ts.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


def et_date_from_ts(ts: float) -> date:
    """Unix timestamp → calendar date in America/New_York."""
    return datetime.fromtimestamp(float(ts), tz=_ET).date()


def day_result(pnl: float) -> str:
    if pnl > 0:
        return "win"
    if pnl < 0:
        return "loss"
    return "flat"


def aggregate_daily_pnl(trades: list[dict]) -> dict[str, dict[str, Any]]:
    """
    Sum P&L and count closed trades per ET calendar day.

    Only rows with non-None pnl and a closed_ts (or opened_ts fallback) are
    included. Returns map keyed by ISO date YYYY-MM-DD:
      {date, pnl, trade_count, result}
    """
    buckets: dict[str, dict[str, Any]] = {}
    for trade in trades:
        pnl = trade.get("pnl")
        if pnl is None:
            continue
        ts = trade.get("closed_ts")
        if ts is None:
            ts = trade.get("opened_ts")
        if ts is None:
            continue
        day = et_date_from_ts(float(ts))
        key = day.isoformat()
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {"date": key, "pnl": 0.0, "trade_count": 0}
            buckets[key] = bucket
        bucket["pnl"] = round(bucket["pnl"] + float(pnl), 2)
        bucket["trade_count"] += 1
    for bucket in buckets.values():
        bucket["result"] = day_result(bucket["pnl"])
    return buckets


def _empty_day(day: date) -> dict[str, Any]:
    return {
        "date": day.isoformat(),
        "pnl": 0.0,
        "trade_count": 0,
        "result": "flat",
    }


def _month_summary(
    year: int,
    month: int,
    daily: dict[str, dict[str, Any]],
    *,
    include_empty_days: bool,
) -> dict[str, Any]:
    _, last_day = monthrange(year, month)
    days_out: list[dict[str, Any]] = []
    month_pnl = 0.0
    month_trades = 0
    win_days = loss_days = flat_days = 0

    for day_num in range(1, last_day + 1):
        day = date(year, month, day_num)
        key = day.isoformat()
        bucket = daily.get(key)
        if bucket is None:
            if include_empty_days:
                days_out.append(_empty_day(day))
            continue
        days_out.append(dict(bucket))
        month_pnl = round(month_pnl + bucket["pnl"], 2)
        month_trades += bucket["trade_count"]
        result = bucket["result"]
        if result == "win":
            win_days += 1
        elif result == "loss":
            loss_days += 1
        else:
            flat_days += 1

    return {
        "year": year,
        "month": month,
        "pnl": month_pnl,
        "trade_count": month_trades,
        "winning_days": win_days,
        "losing_days": loss_days,
        "flat_days": flat_days,
        "days": days_out,
    }


def _week_totals(year: int, month: int, daily: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Sunday-start weeks matching TraderVue month grid (Sun–Sat + Total)."""
    _, last_day = monthrange(year, month)
    first = date(year, month, 1)
    # Back up to Sunday of the first visible week
    start = first - timedelta(days=(first.weekday() + 1) % 7)
    last = date(year, month, last_day)
    # Saturday on or after the last day of the month (Sun–Sat weeks).
    end = last + timedelta(days=(5 - last.weekday()) % 7)

    weeks: list[dict[str, Any]] = []
    cursor = start
    week_index = 1
    while cursor <= end:
        week_pnl = 0.0
        week_trades = 0
        week_days: list[str] = []
        for _ in range(7):
            key = cursor.isoformat()
            week_days.append(key)
            bucket = daily.get(key)
            if bucket and cursor.month == month and cursor.year == year:
                week_pnl = round(week_pnl + bucket["pnl"], 2)
                week_trades += bucket["trade_count"]
            cursor += timedelta(days=1)
        weeks.append({
            "week_index": week_index,
            "pnl": week_pnl,
            "trade_count": week_trades,
            "days": week_days,
        })
        week_index += 1
    return weeks


def build_year_calendar(
    trades: list[dict],
    year: int,
    *,
    include_mock: bool = False,
) -> dict[str, Any]:
    """Year rollup: 12 months with per-day activity (days with trades only)."""
    daily = aggregate_daily_pnl(trades)
    # Restrict to this calendar year in ET
    year_daily = {
        k: v for k, v in daily.items()
        if k.startswith(f"{year}-")
    }
    months = [
        _month_summary(year, m, year_daily, include_empty_days=False)
        for m in range(1, 13)
    ]
    year_pnl = round(sum(m["pnl"] for m in months), 2)
    year_trades = sum(m["trade_count"] for m in months)
    winning_days = sum(m["winning_days"] for m in months)
    losing_days = sum(m["losing_days"] for m in months)
    flat_days = sum(m["flat_days"] for m in months)

    best_day = None
    worst_day = None
    if year_daily:
        best_day = max(year_daily.values(), key=lambda d: d["pnl"])
        worst_day = min(year_daily.values(), key=lambda d: d["pnl"])

    return {
        "year": year,
        "timezone": "America/New_York",
        "includes_mock_data": include_mock,
        "year_pnl": year_pnl,
        "year_trade_count": year_trades,
        "winning_days": winning_days,
        "losing_days": losing_days,
        "flat_days": flat_days,
        "best_day": None if best_day is None else {
            "date": best_day["date"],
            "pnl": best_day["pnl"],
            "trade_count": best_day["trade_count"],
        },
        "worst_day": None if worst_day is None else {
            "date": worst_day["date"],
            "pnl": worst_day["pnl"],
            "trade_count": worst_day["trade_count"],
        },
        "months": months,
    }


def build_month_calendar(
    trades: list[dict],
    year: int,
    month: int,
    *,
    include_mock: bool = False,
) -> dict[str, Any]:
    """Full month detail: every day filled + week totals."""
    if month < 1 or month > 12:
        raise ValueError(f"month must be 1..12, got {month}")
    daily = aggregate_daily_pnl(trades)
    summary = _month_summary(year, month, daily, include_empty_days=True)
    summary["timezone"] = "America/New_York"
    summary["includes_mock_data"] = include_mock
    summary["weeks"] = _week_totals(year, month, daily)
    return summary
