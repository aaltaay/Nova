"""The hot list's auto feed (ADR 044 decision 4): the leaders rule's top N of the live Gainers board.

Every ``HOT_LIST_AUTO_TICK_SEC``, all day, the loop first makes today's list today's (``service.today``: the
04:00 ET rollover happens here when nothing else wrote first). Then, from ``HOT_LIST_AUTO_START_ET`` to
``HOT_LIST_AUTO_END_ET`` on exchange days, it reads the live Gainers board as auto-record does
(``scanner_surface.surface_rows``, each row as a leaderboard row, ``leaderboard.ranking.rank_rows`` with
``LEADERS_RULES``) and takes its top ``auto_n`` (``pick``, pure): each name not listed yet is added, sticky
for the day, never past ``HOT_LIST_CAP``, and takes the list's default Buy / Sell (``stock_tie``). The feed
adds a name once a day: one the operator took off is not added back while it still leads (``_added_on``:
memory, seeded after a restart from the day's ``hot_list`` auto lines on the audit stream).

``status()['error']`` says why the feed is not adding names when it should be (the list unreadable, the
board not live, a failed tick); it is None outside the window and while ``auto_n`` is 0 (off is a choice).
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from datetime import datetime
from typing import Any

from constants_hot_list import (
    HOT_LIST_AUDIT_ACTION,
    HOT_LIST_AUTO_END_ET,
    HOT_LIST_AUTO_SEED_BYTES,
    HOT_LIST_AUTO_START_ET,
    HOT_LIST_AUTO_TICK_SEC,
    HOT_LIST_BOARD_GAINERS,
    HOT_LIST_CAP,
    HOT_LIST_EVENT_AUTO,
    HOT_LIST_HOW_AUTO,
)
from constants_leaderboard import LEADERBOARD_BOARD_GAINERS
from hot_list import service, store
from hot_list.errors import HotListError
from leaderboard.ranking import LEADERS_RULES, rank_rows
from leaderboard.rows import ET, from_desk_row

logger = logging.getLogger(__name__)

_error: str | None = None
_last_tick: float | None = None
_added: dict[str, set[str]] = {}         # trading day -> the names the feed added that day


def _minutes(text: str) -> int:
    hour, minute = text.split(":")
    return int(hour) * 60 + int(minute)


def in_window(now: float) -> bool:
    """07:00-16:00 ET on an exchange day."""
    from leaderboard.recorder import exchange_day

    when = datetime.fromtimestamp(now, ET)
    minute = when.hour * 60 + when.minute
    return exchange_day(when) and _minutes(HOT_LIST_AUTO_START_ET) <= minute < _minutes(HOT_LIST_AUTO_END_ET)


def rule_text(n: int) -> str:
    """The rule in words, for the Bots page."""
    if n <= 0:
        return "off: Nova adds no names by itself -- star the ones you want"
    r = LEADERS_RULES
    return (f"the top {n} of the live Gainers board by the leaders rule -- ${r.min_price:g} to ${r.max_price:g}, a "
            f"float of {(r.max_float or 0) / 1e6:g}M or less (or unknown), {(r.min_volume or 0) / 1e3:g}K shares or "
            f"more, up on the day -- from {HOT_LIST_AUTO_START_ET} to {HOT_LIST_AUTO_END_ET} ET; a name stays for "
            "the day")


def pick(rows: list[dict[str, Any]], *, now: float, n: int, listed: set[str] | list[str],
         room: int) -> list[dict[str, Any]]:
    """The hot-list entries the board's top ``n`` adds: names not ``listed``, at most ``room``. Pure.

    The same ranking playback and auto-record apply (``LEADERS_RULES``), taking the top ``n`` instead of
    its three; a name already listed keeps its place and is not replaced by the next one."""
    if n <= 0 or room <= 0:
        return []
    minute_ts = int(now) // 60 * 60
    recorded = []
    for position, raw in enumerate(rows, start=1):
        try:
            recorded.append(from_desk_row(raw, minute_ts=minute_ts, board=LEADERBOARD_BOARD_GAINERS, rank=position))
        except (TypeError, ValueError):
            logger.debug("hot list: Gainers row %d could not be read as a leaderboard row", position, exc_info=True)
    have = set(listed)
    out: list[dict[str, Any]] = []
    for row in rank_rows(recorded, dataclasses.replace(LEADERS_RULES, top_n=n)):
        sym = store.valid_symbol(row["symbol"])
        if sym is None or sym in have:
            continue
        out.append({"symbol": sym, "how": HOT_LIST_HOW_AUTO, "at": round(float(now), 3),
                    "board": HOT_LIST_BOARD_GAINERS, "rank": int(row["rank"]), "change_pct": row.get("change_pct")})
        if len(out) >= room:
            break
    return out


def _audit_tail_since(day_start: float) -> list[dict[str, Any]]:
    """The audit lines back to ``day_start``: the file's tail, read back far enough."""
    from bot.persist import read_audit_tail

    size = HOT_LIST_AUTO_SEED_BYTES
    while True:
        rows, whole = read_audit_tail(size)
        oldest = next((float(r["timestamp"]) for r in rows if isinstance(r.get("timestamp"), (int, float))), None)
        if whole or (oldest is not None and oldest < day_start):
            return rows
        size *= 4


def _added_on(day: str, day_start: float) -> set[str]:
    """The names the feed already added on ``day`` (it never adds one twice): memory, seeded once a day."""
    seen = _added.get(day)
    if seen is not None:
        return seen
    seen = set()
    try:
        rows = _audit_tail_since(day_start)
    except Exception:
        logger.warning("hot list: the audit stream could not be read -- a name the feed added today and you took "
                       "off may come back once", exc_info=True)
        rows = []
    for row in rows:
        inputs = row.get("inputs") or {}
        if row.get("action") == HOT_LIST_AUDIT_ACTION and inputs.get("event") == HOT_LIST_EVENT_AUTO                 and float(row.get("timestamp") or 0) >= day_start and inputs.get("symbol"):
            seen.add(str(inputs["symbol"]))
    _added.clear()                       # only today's
    _added[day] = seen
    return seen


def live_gainers() -> tuple[list[dict[str, Any]], str | None]:
    """The live Gainers board as every client sees it, or why there is none (auto-record's read)."""
    from runtime_state import get_runtime_state
    from scanner_surface import surface_rows

    state = get_runtime_state()
    table = getattr(state.gainer_table, "state", None)
    if table != "live":
        return [], f"the Gainers board is not live ({table or 'unknown'}): the auto feed adds no name until it is"
    return surface_rows(list(state.gainer_cache or []), LEADERBOARD_BOARD_GAINERS), None


async def tick(now: float | None = None) -> list[str]:
    """One pass (see the module): the names it added."""
    global _error, _last_tick
    from hot_list import stock_tie

    ts = time.time() if now is None else float(now)
    _last_tick = ts
    try:
        doc = service.today(ts)
    except HotListError as exc:
        _error = exc.message
        return []
    n = int(doc.get("auto_n") or 0)
    if n <= 0 or not in_window(ts):
        _error = None
        return []
    rows, why = live_gainers()
    if why is not None:
        _error = why
        return []
    from practice.clock import day_start_ts

    done = _added_on(str(doc["date"]), day_start_ts(ts))
    picked = pick(rows, now=ts, n=n, listed=set(service.listed(doc)) | done, room=HOT_LIST_CAP - len(doc["entries"]))
    try:
        added = service.add_auto(picked, now=ts) if picked else []
    except HotListError as exc:
        _error = exc.message
        return []
    done.update(added)
    _error = None
    for sym in added:
        await stock_tie.apply_default(sym, now=ts)
    return added


async def run() -> None:
    """Background task (``app_runtime_tasks``)."""
    global _error
    while True:
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _error = f"the auto feed's last pass failed ({type(exc).__name__}: {exc})"
            logger.exception("hot list: the auto feed's tick failed")
        await asyncio.sleep(HOT_LIST_AUTO_TICK_SEC)


def status() -> dict[str, Any]:
    return {"error": _error, "last_tick": _last_tick}


def reset_for_tests() -> None:
    global _error, _last_tick
    _error = None
    _last_tick = None
    _added.clear()
