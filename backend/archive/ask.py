"""
Ask helpers — find trades / archive index rows by symbol and day (P9).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from archive.health import list_local_cold_days
from archive.replay import load_table_rows, symbols_for_day
from constants import JOURNAL_TRADES_DEFAULT_LIMIT
from journal import store as journal_store

_ET = ZoneInfo("America/New_York")


def _ts_to_session_date(ts: float | None) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=_ET).date().isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def find_trades(
    *,
    symbol: str | None = None,
    session_date: str | None = None,
    limit: int = JOURNAL_TRADES_DEFAULT_LIMIT,
    include_mock: bool = False,
) -> list[dict[str, Any]]:
    """Filter journal trades by symbol and/or ET session day."""
    rows = journal_store.get_trades(limit=max(limit, 500), include_mock=include_mock)
    out: list[dict[str, Any]] = []
    sym = symbol.upper() if symbol else None
    for row in rows:
        if sym and str(row.get("symbol", "")).upper() != sym:
            continue
        day = _ts_to_session_date(row.get("opened_ts"))
        row = dict(row)
        row["session_date"] = day
        if session_date and day != session_date:
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


def archive_index(
    *,
    cold_dir: Path | None = None,
    symbol: str | None = None,
    session_date: str | None = None,
) -> dict[str, Any]:
    """
    Lightweight index of local cold days (+ optional per-day symbols).

    When ``session_date`` is set, also lists symbols present in bars/tape.
    When ``symbol`` is set without a day, returns days that mention the symbol
    (from bars_1m / tape_ibkr when present).
    """
    days = list_local_cold_days(cold_dir=cold_dir)
    if session_date:
        days = [d for d in days if d == session_date]

    entries: list[dict[str, Any]] = []
    sym = symbol.upper() if symbol else None
    for day in days:
        day_symbols = symbols_for_day(day, cold_dir=cold_dir)
        if sym and sym not in day_symbols:
            continue
        entry: dict[str, Any] = {
            "session_date": day,
            "symbol_count": len(day_symbols),
        }
        if session_date or sym:
            entry["symbols"] = day_symbols if not sym else [s for s in day_symbols if s == sym]
        entries.append(entry)

    return {
        "days": entries,
        "day_count": len(entries),
        "symbol_filter": sym,
        "session_date_filter": session_date,
    }


def ask(
    *,
    symbol: str | None = None,
    session_date: str | None = None,
    include_mock: bool = False,
    limit: int = JOURNAL_TRADES_DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Combined ask: journal trades + archive index for symbol/day."""
    trades = find_trades(symbol=symbol, session_date=session_date, limit=limit, include_mock=include_mock)
    index = archive_index(symbol=symbol, session_date=session_date)
    tape_sample: list[dict[str, Any]] = []
    if session_date and symbol:
        try:
            rows = load_table_rows(session_date, "tape_ibkr")
            tape_sample = [
                r for r in rows
                if str(r.get("symbol", "")).upper() == symbol.upper()
            ][:20]
        except Exception as exc:
            tape_sample = [{"error": str(exc)}]
    return {
        "symbol": symbol.upper() if symbol else None,
        "session_date": session_date,
        "trades": trades,
        "trade_count": len(trades),
        "archive": index,
        "tape_sample": tape_sample,
    }
