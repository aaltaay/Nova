"""
Journal P&L calendar aggregates (TraderVue-style year/month day buckets).

Pure functions over closed trade dicts. Calendar days use America/New_York
so US equity session days match the trader's mental model. Bucket key is
closed_ts (realized P&L day), not opened_ts.

``split_books`` (Paper's All view, ADR 069 decision 6) adds ``by_owner`` --
yours and the bots' ``{pnl, trade_count}`` -- to every day, week and month,
the year and its best and worst day; ``everyone`` adds the year's ``holders``.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from constants_owners import OWNERS
from journal import split

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


def trade_day(trade: dict) -> date | None:
    """The ET day a trade's P&L lands on: its close, else its open; None without either."""
    ts = trade.get("closed_ts")
    if ts is None:
        ts = trade.get("opened_ts")
    return None if ts is None else et_date_from_ts(float(ts))


def _no_split() -> dict[str, dict[str, Any]]:
    return {book: {"pnl": 0.0, "trade_count": 0} for book in OWNERS}


def _add_split(into: dict[str, dict[str, Any]], other: dict[str, dict[str, Any]]) -> None:
    for book, sums in other.items():
        into[book]["pnl"] = round(into[book]["pnl"] + sums["pnl"], 2)
        into[book]["trade_count"] += sums["trade_count"]


def aggregate_daily_pnl(trades: list[dict], *, split_books: bool = False) -> dict[str, dict[str, Any]]:
    """
    Sum P&L and count closed trades per ET calendar day.

    Only rows with non-None pnl and a closed_ts (or opened_ts fallback) are
    included. Returns map keyed by ISO date YYYY-MM-DD:
      {date, pnl, trade_count, result} (+ by_owner with ``split_books``)
    """
    buckets: dict[str, dict[str, Any]] = {}
    for trade in trades:
        pnl = trade.get("pnl")
        if pnl is None:
            continue
        day = trade_day(trade)
        if day is None:
            continue
        key = day.isoformat()
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {"date": key, "pnl": 0.0, "trade_count": 0}
            if split_books:
                bucket["by_owner"] = _no_split()
            buckets[key] = bucket
        bucket["pnl"] = round(bucket["pnl"] + float(pnl), 2)
        bucket["trade_count"] += 1
        if split_books:
            _add_split(bucket["by_owner"], {split.book_of_trade(trade): {"pnl": float(pnl), "trade_count": 1}})
    for bucket in buckets.values():
        bucket["result"] = day_result(bucket["pnl"])
    return buckets


def _empty_day(day: date, *, split_books: bool = False) -> dict[str, Any]:
    out = {
        "date": day.isoformat(),
        "pnl": 0.0,
        "trade_count": 0,
        "result": "flat",
    }
    if split_books:
        out["by_owner"] = _no_split()
    return out


def _month_summary(
    year: int,
    month: int,
    daily: dict[str, dict[str, Any]],
    *,
    include_empty_days: bool,
    split_books: bool = False,
) -> dict[str, Any]:
    _, last_day = monthrange(year, month)
    days_out: list[dict[str, Any]] = []
    month_pnl = 0.0
    month_trades = 0
    month_split = _no_split()
    win_days = loss_days = flat_days = 0

    for day_num in range(1, last_day + 1):
        day = date(year, month, day_num)
        key = day.isoformat()
        bucket = daily.get(key)
        if bucket is None:
            if include_empty_days:
                days_out.append(_empty_day(day, split_books=split_books))
            continue
        days_out.append(dict(bucket))
        month_pnl = round(month_pnl + bucket["pnl"], 2)
        month_trades += bucket["trade_count"]
        if split_books:
            _add_split(month_split, bucket["by_owner"])
        result = bucket["result"]
        if result == "win":
            win_days += 1
        elif result == "loss":
            loss_days += 1
        else:
            flat_days += 1

    out = {
        "year": year,
        "month": month,
        "pnl": month_pnl,
        "trade_count": month_trades,
        "winning_days": win_days,
        "losing_days": loss_days,
        "flat_days": flat_days,
        "days": days_out,
    }
    if split_books:
        out["by_owner"] = month_split
    return out


def _week_totals(year: int, month: int, daily: dict[str, dict[str, Any]], *,
                 split_books: bool = False) -> list[dict[str, Any]]:
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
        week_split = _no_split()
        week_days: list[str] = []
        for _ in range(7):
            key = cursor.isoformat()
            week_days.append(key)
            bucket = daily.get(key)
            if bucket and cursor.month == month and cursor.year == year:
                week_pnl = round(week_pnl + bucket["pnl"], 2)
                week_trades += bucket["trade_count"]
                if split_books:
                    _add_split(week_split, bucket["by_owner"])
            cursor += timedelta(days=1)
        week = {
            "week_index": week_index,
            "pnl": week_pnl,
            "trade_count": week_trades,
            "days": week_days,
        }
        if split_books:
            week["by_owner"] = week_split
        weeks.append(week)
        week_index += 1
    return weeks


def _day_brief(day: dict[str, Any]) -> dict[str, Any]:
    brief = {"date": day["date"], "pnl": day["pnl"], "trade_count": day["trade_count"]}
    if "by_owner" in day:
        brief["by_owner"] = day["by_owner"]
    return brief


def build_year_calendar(
    trades: list[dict],
    year: int,
    *,
    include_mock: bool = False,
    split_books: bool = False,
    everyone: list[dict] | None = None,
) -> dict[str, Any]:
    """Year rollup: 12 months with per-day activity (days with trades only). ``everyone``: the venue's trades
    whatever the view, for the year's ``holders``."""
    daily = aggregate_daily_pnl(trades, split_books=split_books)
    # Restrict to this calendar year in ET
    year_daily = {
        k: v for k, v in daily.items()
        if k.startswith(f"{year}-")
    }
    months = [
        _month_summary(year, m, year_daily, include_empty_days=False, split_books=split_books)
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

    out = {
        "year": year,
        "timezone": "America/New_York",
        "includes_mock_data": include_mock,
        "year_pnl": year_pnl,
        "year_trade_count": year_trades,
        "winning_days": winning_days,
        "losing_days": losing_days,
        "flat_days": flat_days,
        "best_day": None if best_day is None else _day_brief(best_day),
        "worst_day": None if worst_day is None else _day_brief(worst_day),
        "months": months,
    }
    if split_books:
        year_split = _no_split()
        for month_row in months:
            _add_split(year_split, month_row["by_owner"])
        out["by_owner"] = year_split
    if everyone is not None:
        out["holders"] = split.holders(
            t for t in everyone if t.get("pnl") is not None and (d := trade_day(t)) is not None and d.year == year
        )
    return out


def build_month_calendar(
    trades: list[dict],
    year: int,
    month: int,
    *,
    include_mock: bool = False,
    split_books: bool = False,
) -> dict[str, Any]:
    """Full month detail: every day filled + week totals."""
    if month < 1 or month > 12:
        raise ValueError(f"month must be 1..12, got {month}")
    daily = aggregate_daily_pnl(trades, split_books=split_books)
    summary = _month_summary(year, month, daily, include_empty_days=True, split_books=split_books)
    summary["timezone"] = "America/New_York"
    summary["includes_mock_data"] = include_mock
    summary["weeks"] = _week_totals(year, month, daily, split_books=split_books)
    return summary
