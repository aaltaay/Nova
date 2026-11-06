"""Whole-day relative volume per stock-day, for joins (#1100 table, ``rvol_store``): the day's volume over the mean
whole-session volume of its baseline sessions -- ``rvol_scan``'s ``rvol_daily`` at the end of the session ("5x the
50-day average"), read straight from the table's day rows instead of a scan over every stock.

``for_pairs`` answers every ``(day, symbol)`` asked: a dict, or None when it is unknown -- the table does not hold the
day (not built, or the table was never built) or the symbol (ETFs, warrants and the like are not in it). A row with
fewer than ``MIN_SESSIONS`` baseline sessions, or a zero average, has ``rvol_daily`` None: too little history to say.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from market_reads import rvol_store as rs

MIN_SESSIONS = rs.BASE_SESSIONS        # rvol_scan's own min_base_sessions default
COLUMNS = ("symbol", "volume", "day_avg_volume", "day_avg_sessions")
RULE = (f"rvol_daily = the day's volume 04:00-20:00 (Massive minute bars) / the mean whole-session volume of up to "
        f"{rs.DAY_AVG_SESSIONS} earlier sessions (the relative-volume table's day_avg_volume); null when the table "
        f"does not hold the stock-day or it has fewer than {MIN_SESSIONS} earlier sessions -- unknown, never low")


def _built() -> set[str]:
    try:
        return set(rs.built_days(rs.load_manifest(required=True)))
    except LookupError:                 # the table was never built: every pair is unknown
        return set()


def for_pairs(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any] | None]:
    """``(day, symbol)`` -> ``{rvol_daily, rvol_volume, rvol_day_avg_volume, rvol_day_avg_sessions}`` or None."""
    import pyarrow.parquet as pq

    by_day: dict[str, set[str]] = defaultdict(set)
    for day, symbol in pairs:
        by_day[str(day)[:10]].add(str(symbol).strip().upper())
    out: dict[tuple[str, str], dict[str, Any] | None] = {(d, s): None for d, ss in by_day.items() for s in ss}
    built = _built()
    for day, symbols in by_day.items():
        if day not in built:
            continue
        table = pq.read_table(rs.days_path(day), columns=list(COLUMNS), filters=[("symbol", "in", sorted(symbols))])
        for row in table.to_pylist():
            sessions, avg = row["day_avg_sessions"], row["day_avg_volume"]
            known = sessions is not None and sessions >= MIN_SESSIONS and avg
            out[(day, row["symbol"])] = {
                "rvol_daily": round(row["volume"] / avg, 2) if known and row["volume"] is not None else None,
                "rvol_volume": row["volume"], "rvol_day_avg_volume": avg, "rvol_day_avg_sessions": sessions}
    return out
