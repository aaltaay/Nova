"""The chosen setup's entry rules at Strategy (ADR 027): the material's window and one trade a day.

Only entries (``BOT_BUY_KINDS``) are gated; exits, cancels and protective
sources never are. The clock is the venue's (``execution.session_gate``: the
replay playhead on Sim). A bot entry counts toward the day once it was sent
(its audit row says ``ok``); the day is the venue's ET date stamped on the row
(``venue_day``), else the row's own ET date.

Owner: this module (no state; the count is read from the bot audit stream).

ADR 029: the window and the daily cap are the template in play's own
(``bot_window_start`` / ``bot_window_end`` / ``bot_entries_per_day``) for the
chosen setup; a setup whose parameters carry none, or a template store that
cannot be read, keeps the material's 07:00-10:00 and one a day.
"""
from __future__ import annotations

from datetime import datetime, time as dtime
from typing import Any, Callable

from bot.errors import BotError
import logging

from constants_bot import (
    BOT_BUY_KINDS,
    BOT_ENTRIES_PER_DAY,
    BOT_ENTRY_WINDOW_END_ET,
    BOT_ENTRY_WINDOW_START_ET,
    BOT_REASON_DAY_TRADE_CAP,
    BOT_REASON_OUTSIDE_WINDOW,
    BOT_SETUP_DEFAULT,
    BOT_TZ,
)

logger = logging.getLogger(__name__)
_now_for_tests: Callable[[], datetime] | None = None


def rules() -> dict[str, Any]:
    """``{start, end, max_entries, template}`` for the chosen setup's template in play."""
    fallback = {"start": BOT_ENTRY_WINDOW_START_ET, "end": BOT_ENTRY_WINDOW_END_ET,
                "max_entries": BOT_ENTRIES_PER_DAY, "template": None}
    try:
        from bot.persist import load_session
        from setup_templates.store import get_store

        setup = load_session().get("setup") or BOT_SETUP_DEFAULT
        t = get_store().in_play(setup)
    except Exception:
        logger.warning("bot entry rules: the template in play could not be read -- keeping 07:00-10:00, one a day",
                       exc_info=True)
        return fallback
    v = t.values
    if not {"bot_window_start", "bot_window_end", "bot_entries_per_day"} <= set(v):
        return {**fallback, "template": {"id": t.id, "rev": t.rev, "name": t.name}}
    return {"start": str(v["bot_window_start"]), "end": str(v["bot_window_end"]),
            "max_entries": int(v["bot_entries_per_day"]), "template": {"id": t.id, "rev": t.rev, "name": t.name}}


def _hm(text: str) -> dtime:
    hour, minute = text.split(":")
    return dtime(int(hour), int(minute))


def venue_now() -> datetime:
    if _now_for_tests is not None:
        return _now_for_tests()
    from execution.session_gate import venue_now_et

    return venue_now_et()


def in_window(now: datetime | None = None, *, r: dict[str, Any] | None = None) -> bool:
    r = r or rules()
    current = (now or venue_now()).time()
    return _hm(r["start"]) <= current < _hm(r["end"])


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
    r = rules()
    if not in_window(now, r=r):
        raise BotError(
            f"entries only {r['start']}-{r['end']} ET (venue clock {now.strftime('%H:%M')})",
            409,
            BOT_REASON_OUTSIDE_WINDOW,
        )
    cap = int(r["max_entries"])
    if entries_today(now) >= cap:
        raise BotError(
            f"{cap} trade{'' if cap == 1 else 's'} a day -- {cap} bot entr{'y' if cap == 1 else 'ies'} "
            "already sent today",
            409,
            BOT_REASON_DAY_TRADE_CAP,
        )


def venue_day() -> str:
    return venue_now().date().isoformat()


def status(now: datetime | None = None) -> dict[str, Any]:
    now = now or venue_now()
    r = rules()
    return {"start": r["start"], "end": r["end"], "open": in_window(now, r=r), "entries_today": entries_today(now),
            "max_entries": int(r["max_entries"]), "venue_time": now.strftime("%H:%M"), "template": r["template"]}


def set_clock_for_tests(fn: Callable[[], datetime] | None) -> None:
    global _now_for_tests
    _now_for_tests = fn
