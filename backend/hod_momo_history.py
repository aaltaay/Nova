"""HOD Momo's alert history for a day: the alerts Nova kept, or that it kept none.

A day with no snapshot on file is an absence -- Nova kept no HOD Momo record
that day -- never "no alerts raised" (operator rule: a missing fact is stated,
never styled as real data; 2026-10-12, a Massive-rebuilt Sim day). A day whose
snapshot is on file but unreadable says so instead of reading as empty.
"""
from __future__ import annotations

from typing import Any

import cache as _cache
from hod_momo_models import restored_change_pct


def _history_rows(rows: list[Any]) -> list[Any]:
    # A past day's archive keeps the pre-fix "CHG 0.0%" fill-in on disk; it is
    # read as unknown here, like today's restore (QA C33).
    return [
        {**raw, "change_pct": restored_change_pct(raw)} if isinstance(raw, dict) else raw
        for raw in rows
    ]


def get_history_alerts(date_str: str) -> list[Any]:
    """The day's alerts; empty both when none were raised and when none were kept."""
    return _history_rows(_cache.load_hod_momo_snapshot_for_date(date_str).get("alerts", []))


def get_history_day(date_str: str) -> dict[str, Any]:
    """``{recorded, alerts, error}``: ``recorded`` is False when Nova holds no snapshot for the day."""
    if not _cache.hod_momo_snapshot_on_file(date_str):
        return {"recorded": False, "alerts": [], "error": None}
    rows = _cache.load_hod_momo_snapshot_for_date(date_str).get("alerts")
    if not isinstance(rows, list):
        return {
            "recorded": True,
            "alerts": [],
            "error": f"Nova holds HOD alert history for {date_str} but could not read it.",
        }
    return {"recorded": True, "alerts": _history_rows(rows), "error": None}
