"""The chosen setup's entry rules at Strategy (ADR 027): the material's window and one trade a day.

Only entries (``BOT_BUY_KINDS``) are gated; exits, cancels and protective
sources never are. The clock is the venue's (``execution.session_gate``: the
replay playhead on Sim). A bot entry counts toward the day once it was sent
(its audit row says ``ok``); the day is the venue's ET date stamped on the row
(``venue_day``), else the row's own ET date.

Owner: this module (no state; the count is read from the bot audit stream).
"""
from __future__ import annotations

from datetime import datetime, time as dtime
from typing import Any, Callable

from bot.errors import BotError
from constants_bot import (
    BOT_BUY_KINDS,
    BOT_ENTRIES_PER_DAY,
    BOT_ENTRY_WINDOW_END_ET,
    BOT_ENTRY_WINDOW_START_ET,
    BOT_REASON_DAY_TRADE_CAP,
    BOT_REASON_OUTSIDE_WINDOW,
    BOT_TZ,
)

_now_for_tests: Callable[[], datetime] | None = None


def _hm(text: str) -> dtime:
    hour, minute = text.split(":")
    return dtime(int(hour), int(minute))


def venue_now() -> datetime:
    if _now_for_tests is not None:
        return _now_for_tests()
    from execution.session_gate import venue_now_et

    return venue_now_et()


def in_window(now: datetime | None = None) -> bool:
    current = (now or venue_now()).time()
    return _hm(BOT_ENTRY_WINDOW_START_ET) <= current < _hm(BOT_ENTRY_WINDOW_END_ET)


def _row_day(row: dict[str, Any]) -> str | None:
    day = (row.get("inputs") or {}).get("venue_day")
    if day:
        return str(day)
    ts = row.get("timestamp")
    if not isinstance(ts, (int, float)):
        return None
    from zoneinfo import ZoneInfo

    return datetime.fromtimestamp(float(ts), ZoneInfo(BOT_TZ)).date().isoformat()


def entries_today(now: datetime | None = None, *, rows: list[dict[str, Any]] | None = None) -> int:
    from bot.audit import list_entries

    day = (now or venue_now()).date().isoformat()
    rows = list_entries(limit=500) if rows is None else rows
    return sum(1 for r in rows
               if r.get("action") in BOT_BUY_KINDS and r.get("outcome") == "ok" and _row_day(r) == day)


def assert_entry_allowed(kind: str) -> None:
    """Refuse an entry outside the window or past the day's cap; anything else passes."""
    if kind not in BOT_BUY_KINDS:
        return
    now = venue_now()
    if not in_window(now):
        raise BotError(
            f"entries only {BOT_ENTRY_WINDOW_START_ET}-{BOT_ENTRY_WINDOW_END_ET} ET "
            f"(venue clock {now.strftime('%H:%M')})",
            409,
            BOT_REASON_OUTSIDE_WINDOW,
        )
    if entries_today(now) >= BOT_ENTRIES_PER_DAY:
        raise BotError(
            f"one trade a day -- {BOT_ENTRIES_PER_DAY} bot entry already sent today",
            409,
            BOT_REASON_DAY_TRADE_CAP,
        )


def venue_day() -> str:
    return venue_now().date().isoformat()


def status(now: datetime | None = None) -> dict[str, Any]:
    now = now or venue_now()
    return {"start": BOT_ENTRY_WINDOW_START_ET, "end": BOT_ENTRY_WINDOW_END_ET,
            "open": in_window(now), "entries_today": entries_today(now),
            "max_entries": BOT_ENTRIES_PER_DAY, "venue_time": now.strftime("%H:%M")}


def set_clock_for_tests(fn: Callable[[], datetime] | None) -> None:
    global _now_for_tests
    _now_for_tests = fn
