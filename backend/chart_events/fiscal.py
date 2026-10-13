"""Fiscal periods named as the registrant names them. Pure.

SEC's own fiscal year and period (``fy`` / ``fp``) name a report's period ("2026 Q3"); a six-month 6-K period
is a half and a nine-month one ``9M``. A release that no report claims is named from the registrant's
``fiscalYearEnd`` in the submissions file and how it numbers its years, read from its annual reports
(``_naming_offset``): MNDR's six months to December 31, 2025 with a June year end is "2026 H1", as Webull
shows it. A quarter the company names ("Second Quarter 2026") gets its nominal end (``quarter_end``).
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any, Mapping

from chart_events.facts import DAYS_PER_MONTH, YEAR_END_SLACK_DAYS


def period_label(fiscal_year: Any, fiscal_period: Any, months: int | None) -> str | None:
    """``2026 Q3``, ``2026 FY``; a six-month 6-K period is ``H1`` / ``H2`` and a nine-month one ``9M``."""
    if not fiscal_year or not fiscal_period:
        return None
    fp = str(fiscal_period)
    if months == 6 and fp == "Q2":
        fp = "H1"
    elif months == 6 and fp in ("Q4", "FY"):
        fp = "H2"
    elif months == 9 and fp == "Q3":
        fp = "9M"
    return f"{fiscal_year} {fp}"


def fiscal_year_end(submissions: Mapping[str, Any] | None) -> tuple[int, int] | None:
    """The registrant's fiscal year end as (month, day), from ``fiscalYearEnd`` ("0630")."""
    raw = str((submissions or {}).get("fiscalYearEnd") or "")
    if len(raw) != 4 or not raw.isdigit():
        return None
    month, day = int(raw[:2]), int(raw[2:])
    return (month, day) if 1 <= month <= 12 and 1 <= day <= 31 else None


def year_end_after(end: date, fye: tuple[int, int]) -> date:
    """The first fiscal year end on or after ``end``, give or take a 52-53 week year's few days."""
    month, day = fye
    for year in (end.year - 1, end.year, end.year + 1):
        try:
            stop = date(year, month, day)
        except ValueError:          # "0229", or a day the month lacks: its last day
            stop = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
        if stop >= end - timedelta(days=YEAR_END_SLACK_DAYS):
            return stop
    return date(end.year + 1, month, min(day, 28))


def fiscal_label(end: date, months: int, fye: tuple[int, int] | None, offset: int) -> str | None:
    """The fiscal period a span of ``months`` ending ``end`` is, numbered as the registrant numbers its
    years (``offset``: its fiscal year number less the calendar year that year ends in)."""
    if fye is None or months not in (3, 6, 9, 12):
        return None
    stop = year_end_after(end, fye)
    into = 12 - round((stop - end).days / DAYS_PER_MONTH)
    year = stop.year + offset
    if months == 12 and into == 12:
        return f"{year} FY"
    if months == 3 and into in (3, 6, 9, 12):
        return f"{year} Q{into // 3}"
    if months == 6 and into in (6, 12):
        return f"{year} H{into // 6}"
    if months == 9 and into == 9:
        return f"{year} 9M"
    return None


def quarter_end(named: str, fye: tuple[int, int] | None, offset: int) -> date | None:
    """The nominal last day of a quarter the company names ("2026 Q2"), from its fiscal year end; a 52-53
    week year's quarter ends within days of it. None when the year end is unknown."""
    try:
        year_text, quarter_text = named.split()
        number, quarter = int(year_text), int(quarter_text.lstrip("Q"))
    except ValueError:
        return None
    if fye is None or not 1 <= quarter <= 4:
        return None
    month, year = fye[0] - 3 * (4 - quarter), number - offset
    while month < 1:
        month, year = month + 12, year - 1
    last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
    # A year that ends on a month's last day ends its quarters on theirs.
    return date(year, month, last if fye[1] >= 28 else min(fye[1], last))


def naming_offset(reports: list[dict[str, Any]], fye: tuple[int, int] | None) -> int:
    """How the registrant numbers its fiscal years against the calendar year each ends in (0 for most):
    read from its annual reports' own ``fy``."""
    if fye is None:
        return 0
    seen: Counter = Counter()
    for rep in reports:
        first = rep["facts"][0] if rep["facts"] else {}
        if isinstance(first.get("fy"), int) and first.get("fp") == "FY" and rep["period"]:
            seen[first["fy"] - year_end_after(rep["period"][1], fye).year] += 1
    return seen.most_common(1)[0][0] if seen else 0
