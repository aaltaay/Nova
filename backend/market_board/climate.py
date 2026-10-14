"""The small-cap climate (ADR 053): runners, gappers, halts and themes from Nova's leaderboard store (ADR 023).

One lens: the recorded Gainers board within its first ``MARKET_CLIMATE_RANK_MAX`` ranks, at or above
``SCANNER_MIN_PRICE``. A rebuilt day's ``market`` board is left out (``MARKET_CLIMATE_USE_REBUILT``): it ranks every
listed stock's minute bars, not IBKR's scan, and counted about 40% more runners a session (61 against 42 over the
weeks either side of 2026-09-23), so mixing them would call every recorded week cold. A runner is a symbol whose ``change_pct``
reached 20 / 50 / 100% that session by the close (today: by now). A gapper is a symbol seen after 09:30 with an
open gap (``gap_pct``) of 20%+; it held when it was still on the board at the period's last minute at or above its
open (``prev_close x (1 + gap_pct)``), failed when on the board below it, and is ``gone`` (unknown) when it left the
board. Halts are the Nasdaq halt feed's starts. A past session is read once per process; today again each turn.

A past session with no board in the lens is filled from the Massive day movers index (ADR 053 amendment 2026-10-14):
a common stock whose minute bars first reached +20 / 50 / 100% over the prior close before the close, priced at
``SCANNER_MIN_PRICE`` or more at +20%. ``source`` is ``massive`` and the day draws on the chart only (its lens has
no top-50 rank), so it never enters a count, baseline, temperature, theme share, gapper rate or the runners tab.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from constants_leaderboard import (
    LEADERBOARD_SOURCE_RECONSTRUCTED,
    LEADERBOARD_SOURCE_RECORDED,
)
from constants_market_board import (
    MARKET_CLIMATE_BASELINE_DAYS,
    MARKET_CLIMATE_BASELINE_DAYS_1D,
    MARKET_CLIMATE_CHART_SESSIONS,
    MARKET_CLIMATE_COLD_X,
    MARKET_CLIMATE_GAPPER_MIN,
    MARKET_CLIMATE_HALT_SOURCE,
    MARKET_CLIMATE_HOT_X,
    MARKET_CLIMATE_MASSIVE_KINDS,
    MARKET_CLIMATE_MASSIVE_SOURCE,
    MARKET_CLIMATE_RANK_MAX,
    MARKET_CLIMATE_REBUILT_BOARD,
    MARKET_CLIMATE_RECORDED_BOARD,
    MARKET_CLIMATE_THRESHOLDS,
    MARKET_CLIMATE_TOP,
    MARKET_CLIMATE_USE_REBUILT,
    MARKET_PERIOD_SESSIONS,
    MARKET_UNCLASSIFIED,
)
from constants_scanner import SCANNER_MIN_PRICE, SESSION_RTH_OPEN_MIN_ET
from market_board import clock, industries

logger = logging.getLogger(__name__)

SOURCE = "leaderboard"
_KEYS = tuple(MARKET_CLIMATE_THRESHOLDS)   # up20, up50, up100


@dataclass
class Day:
    date: str
    source: str | None = None                       # recorded | reconstructed | massive | None (no board)
    runners: dict[str, dict[str, Any]] = field(default_factory=dict)  # symbol -> {mx, t: {up20: ts}, last...}
    gappers: dict[str, str] = field(default_factory=dict)          # symbol -> held | failed | gone
    halts: list[tuple[str, float]] = field(default_factory=list)


_lock = threading.Lock()
_days: dict[str, Day] = {}


def _board_for(db: Any, day: str) -> tuple[str | None, str | None]:
    rows = db.execute("SELECT source, GROUP_CONCAT(DISTINCT board) FROM coverage WHERE session_date = ?"
                      " GROUP BY source", (day,)).fetchall()
    boards = {src: set((b or "").split(",")) for src, b in rows}
    if MARKET_CLIMATE_RECORDED_BOARD in boards.get(LEADERBOARD_SOURCE_RECORDED, set()):
        return LEADERBOARD_SOURCE_RECORDED, MARKET_CLIMATE_RECORDED_BOARD
    if MARKET_CLIMATE_USE_REBUILT and MARKET_CLIMATE_REBUILT_BOARD in boards.get(LEADERBOARD_SOURCE_RECONSTRUCTED, set()):
        return LEADERBOARD_SOURCE_RECONSTRUCTED, MARKET_CLIMATE_REBUILT_BOARD
    return None, None


def _counted(day: Day | None) -> bool:
    """A day in the climate's own lens (a board Nova holds); a Massive-filled day is on the chart only."""
    return day is not None and day.source in (LEADERBOARD_SOURCE_RECORDED, LEADERBOARD_SOURCE_RECONSTRUCTED)


def massive_day(mv: Any, day: date, close_ts: float) -> Day | None:
    """A past session's runners from the Massive day movers index, or ``None`` when the index has not built it."""
    from day_movers.query import _kinds_sql

    iso = day.isoformat()
    if mv.execute("SELECT 1 FROM sessions WHERE session_date = ?", (iso,)).fetchone() is None:
        return None
    kinds, kind_args = _kinds_sql(MARKET_CLIMATE_MASSIVE_KINDS)
    out = Day(date=iso, source=MARKET_CLIMATE_MASSIVE_SOURCE)
    for sym, pc, pm_high, high, close, *marks in mv.execute(
            "SELECT symbol, prev_close, pm_high, high, close, up20_ts, up50_ts, up100_ts FROM movers"
            " WHERE session_date = ? AND up20_ts IS NOT NULL AND up20_ts < ? AND NOT COALESCE(split_suspect, 0)"
            f" AND prev_close * ? >= ? AND {kinds}",
            (iso, int(close_ts), 1.0 + MARKET_CLIMATE_THRESHOLDS["up20"], SCANNER_MIN_PRICE, *kind_args)):
        top = max((v for v in (pm_high, high) if v is not None), default=None)
        out.runners[sym] = {"mx": top / pc - 1.0 if top and pc else MARKET_CLIMATE_THRESHOLDS["up20"],
                            "t": {k: v for k, v in zip(_KEYS, marks, strict=True) if v is not None and v < close_ts},
                            "price": close}
    return out


def _massive_store() -> Any:
    """The day movers index read-only, or ``None`` (not built, its drive absent, another schema)."""
    try:
        from day_movers import store as movers_store

        return movers_store.read_only()
    except Exception as exc:  # noqa: BLE001 -- a missing index only leaves the chart's gaps hatched
        logger.warning("market_board.climate: Massive day movers index unreadable: %s", exc)
        return None


def read_day(db: Any, day: date, end_ts: float) -> Day:
    """One session's runners, gappers and halts up to ``end_ts`` (a past session: its close)."""
    iso = day.isoformat()
    out = Day(date=iso)
    source, board = _board_for(db, iso)
    out.source = source
    if source is not None:
        cases = ", ".join(f"MIN(CASE WHEN change_pct >= {MARKET_CLIMATE_THRESHOLDS[k]} THEN minute_ts END)"
                          for k in _KEYS)
        rows = db.execute(
            f"SELECT symbol, MAX(change_pct), {cases} FROM rows WHERE session_date = ? AND source = ?"
            " AND board = ? AND rank <= ? AND price >= ? AND minute_ts <= ? GROUP BY symbol HAVING MAX(change_pct) >= ?",
            (iso, source, board, MARKET_CLIMATE_RANK_MAX, SCANNER_MIN_PRICE, int(end_ts),
             MARKET_CLIMATE_THRESHOLDS["up20"])).fetchall()
        for sym, mx, *firsts in rows:
            out.runners[sym] = {"mx": mx, "t": {k: v for k, v in zip(_KEYS, firsts, strict=True) if v is not None}}
        if out.runners:
            marks = ",".join("?" for _ in out.runners)
            for sym, price, float_shares, news_at in db.execute(
                f"SELECT symbol, price, float_shares, news_first_seen_ts FROM (SELECT symbol, price, float_shares,"
                " news_first_seen_ts, ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY minute_ts DESC) rn FROM rows"
                f" WHERE session_date = ? AND source = ? AND board = ? AND minute_ts <= ? AND symbol IN ({marks}))"
                " WHERE rn = 1", (iso, source, board, int(end_ts), *out.runners)).fetchall():
                out.runners[sym].update(price=price, float_shares=float_shares, news_at=news_at)
        open_ts = clock.at(day, SESSION_RTH_OPEN_MIN_ET)
        if end_ts > open_ts:
            last_minute = db.execute(
                "SELECT MAX(minute_ts) FROM rows WHERE session_date = ? AND source = ? AND board = ? AND minute_ts <= ?",
                (iso, source, board, int(end_ts))).fetchone()[0]
            for sym, gap, prev_close, price, minute_ts in db.execute(
                "SELECT symbol, gap_pct, prev_close, price, minute_ts FROM (SELECT symbol, gap_pct, prev_close,"
                " price, minute_ts, ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY minute_ts DESC) rn FROM rows"
                " WHERE session_date = ? AND source = ? AND board = ? AND minute_ts >= ? AND minute_ts <= ?"
                " AND gap_pct >= ? AND price >= ?) WHERE rn = 1",
                (iso, source, board, int(open_ts), int(end_ts), MARKET_CLIMATE_GAPPER_MIN, SCANNER_MIN_PRICE)):
                if last_minute is None or minute_ts < last_minute or not prev_close or price is None:
                    out.gappers[sym] = "gone"
                else:
                    out.gappers[sym] = "held" if price >= prev_close * (1.0 + gap) else "failed"
    out.halts = [(s, float(t)) for s, t in db.execute(
        "SELECT symbol, ts FROM halt_events WHERE session_date = ? AND source = ? AND event = 'start' AND ts <= ?"
        " GROUP BY symbol, ts ORDER BY ts", (iso, MARKET_CLIMATE_HALT_SOURCE, float(end_ts))).fetchall()]
    return out


def refresh(now: float, *, sessions_needed: int) -> list[str]:
    """Read every needed session not yet held (and today again); the symbols that ran, for their industries."""
    from leaderboard import store

    today = clock.trading_date(now)
    days = clock.sessions_back(today, sessions_needed)
    db = store.read_only()
    if db is None:
        raise FileNotFoundError("Nova's leaderboard store does not exist yet")
    mv = None
    try:
        for d in days:
            iso = d.isoformat()
            with _lock:
                kept = _days.get(iso)
            close_ts = clock.at(d, clock.close_minute(d))
            if kept is not None and d != today:
                if kept.source is not None:
                    continue
                got = kept                  # no board: the Massive index may have built the session since
            else:
                got = read_day(db, d, min(now, close_ts) if d == today else close_ts)
            if got.source is None and d != today:
                mv = mv or _massive_store()
                filled = massive_day(mv, d, close_ts) if mv is not None else None
                if filled is not None:
                    filled.halts = got.halts
                    got = filled
            with _lock:
                _days[iso] = got
    finally:
        db.close()
        if mv is not None:
            mv.close()
    with _lock:
        return sorted({s for d in days for s in (_days.get(d.isoformat()) or Day("")).runners})


def _count(day: Day, key: str, by_ts: float | None = None) -> int:
    return sum(1 for r in day.runners.values() if key in r["t"] and (by_ts is None or r["t"][key] <= by_ts))


def _themes(days: list[Day]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in days:
        for sym, r in d.runners.items():
            if "up20" in r["t"]:
                name = industries.theme(sym)
                out[name] = out.get(name, 0) + 1
    return out


def _gappers(days: list[Day]) -> tuple[int, int, int]:
    held = sum(1 for d in days for v in d.gappers.values() if v == "held")
    failed = sum(1 for d in days for v in d.gappers.values() if v == "failed")
    gone = sum(1 for d in days for v in d.gappers.values() if v == "gone")
    return held, failed, gone


def _rate(held: int, failed: int) -> float | None:
    return round(100.0 * held / (held + failed), 1) if held + failed else None


def compose(period: str, now: float) -> dict[str, Any]:
    """The wire's ``climate`` block for ``period``."""
    n = MARKET_PERIOD_SESSIONS[period]
    today = clock.trading_date(now)
    with _lock:
        held = dict(_days)
    span = clock.sessions_back(today, n + max(MARKET_CLIMATE_BASELINE_DAYS, MARKET_CLIMATE_CHART_SESSIONS))
    period_days = [held.get(d.isoformat()) or Day(d.isoformat()) for d in span[-n:]]
    prev_days = [held.get(d.isoformat()) or Day(d.isoformat()) for d in span[-2 * n:-n]]
    covered = [d for d in period_days if _counted(d)]
    counts = {k: sum(_count(d, k) for d in covered) for k in _KEYS}
    baseline = None
    if period == "1D":
        minute = min(clock.minute_of_day(now), clock.close_minute(today))
        prior = [held.get(d.isoformat()) for d in span[:-1]][-MARKET_CLIMATE_BASELINE_DAYS_1D:]
        prior = [d for d in prior if _counted(d)]
        if prior:
            avg = {k: round(sum(_count(d, k, clock.at(date.fromisoformat(d.date), minute)) for d in prior)
                            / len(prior), 1) for k in _KEYS}
            baseline = {**avg, "per_day": avg["up20"], "days": len(prior), "basis": "same_minute"}
        per_day = float(counts["up20"]) if covered else None
    else:
        prior = [held.get(d.isoformat()) for d in span[:-n]][-MARKET_CLIMATE_BASELINE_DAYS:]
        prior = [d for d in prior if _counted(d)]
        if prior:
            avg = {k: round(sum(_count(d, k) for d in prior) / len(prior), 1) for k in _KEYS}
            baseline = {**avg, "per_day": avg["up20"], "days": len(prior), "basis": "per_session"}
        per_day = round(counts["up20"] / len(covered), 1) if covered else None
    temperature = None
    if baseline and baseline["per_day"] and per_day is not None:
        x = per_day / baseline["per_day"]
        temperature = "hot" if x >= MARKET_CLIMATE_HOT_X else "cold" if x <= MARKET_CLIMATE_COLD_X else "normal"
    themes_now, themes_prev = _themes(covered), _themes([d for d in prev_days if _counted(d)])
    names = sorted(set(themes_now) | set(themes_prev), key=lambda k: (-themes_now.get(k, 0), k))
    total, prev_total = sum(themes_now.values()), sum(themes_prev.values())
    lead = next((k for k in names if k != MARKET_UNCLASSIFIED and themes_now.get(k)), None)
    g_held, g_failed, g_gone = _gappers(covered)
    base_held, base_failed, _ = _gappers([d for d in (held.get(x.isoformat()) for x in span[:-n]) if _counted(d)]
                                         [-MARKET_CLIMATE_BASELINE_DAYS:])
    halts = [(s, t) for d in covered for s, t in d.halts]
    chart = [held.get(d.isoformat()) or Day(d.isoformat()) for d in span[-MARKET_CLIMATE_CHART_SESSIONS:]]
    tops = sorted(((sym, r, d.date) for d in covered for sym, r in d.runners.items()),
                  key=lambda x: x[1]["mx"], reverse=True)[:MARKET_CLIMATE_TOP]
    return {
        "period": period, "from": period_days[0].date, "to": period_days[-1].date, "sessions": n,
        "covered": len(covered),
        "lens": {"board": MARKET_CLIMATE_RECORDED_BOARD, "rank_max": MARKET_CLIMATE_RANK_MAX,
                 "price_min": SCANNER_MIN_PRICE},
        "counts": counts if covered else {k: None for k in _KEYS}, "per_day": per_day, "baseline": baseline,
        "temperature": temperature,
        "days": [{"date": d.date, "source": d.source, "total": _count(d, "up20") if d.source else None,
                  "themes": _themes([d]) if d.source else {}} for d in chart],
        "theme": ({"name": lead, "count": themes_now[lead], "total": total,
                   "share_pct": round(100.0 * themes_now[lead] / total, 1) if total else None,
                   "prev_share_pct": round(100.0 * themes_prev.get(lead, 0) / prev_total, 1) if prev_total else None}
                  if lead else None),
        "themes": [{"name": k, "count": themes_now.get(k, 0), "prev_count": themes_prev.get(k, 0)} for k in names],
        "gappers": {"held": g_held, "total": g_held + g_failed, "gone": g_gone, "rate_pct": _rate(g_held, g_failed),
                    "baseline_rate_pct": _rate(base_held, base_failed)},
        "halts": {"count": len(halts), "last": ({"symbol": halts[-1][0], "at": halts[-1][1]} if halts else None),
                  "by_side": None, "by_side_why": "the halt log does not record whether a halt was up or down"},
        "top": [{"symbol": sym, "change_pct": round(100.0 * r["mx"], 1), "date": day, "price": r.get("price"),
                 "float_shares": r.get("float_shares"), "theme": industries.theme(sym), "news_at": r.get("news_at")}
                for sym, r, day in tops],
    }


def runners_by_theme(period: str, now: float) -> list[tuple[str, list[dict[str, Any]]]]:
    """The period's runners grouped by theme, biggest groups first, each group's best first (the Top stocks tab)."""
    n = MARKET_PERIOD_SESSIONS[period]
    today = clock.trading_date(now)
    with _lock:
        days = [_days.get(d.isoformat()) for d in clock.sessions_back(today, n)]
    best: dict[str, dict[str, Any]] = {}
    for d in days:
        for sym, r in (d.runners if _counted(d) else {}).items():
            if sym not in best or r["mx"] > best[sym]["mx"]:
                best[sym] = {"mx": r["mx"], "price": r.get("price"), "date": d.date}
    groups: dict[str, list[dict[str, Any]]] = {}
    for sym, r in best.items():
        groups.setdefault(industries.theme(sym), []).append(
            {"symbol": sym, "last": r["price"], "change_pct": round(100.0 * r["mx"], 1), "date": r["date"]})
    for rows in groups.values():
        rows.sort(key=lambda x: x["change_pct"], reverse=True)
    return sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))


def today_numbers(now: float) -> dict[str, Any]:
    """The day read's two climate checks: today's 20%+ runners against the same-minute average, gappers holding."""
    block = compose("1D", now)
    return {"runners": block["counts"]["up20"], "runners_avg": (block["baseline"] or {}).get("up20"),
            "gappers_held": block["gappers"]["held"], "gappers_total": block["gappers"]["total"],
            "covered": block["covered"]}


def reset_for_tests() -> None:
    with _lock:
        _days.clear()
