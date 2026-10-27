"""Trading halts by symbol and day through the front door (ADR 059), from the leaderboard's halt log.

``<NOVA_LEADERBOARD_DIR>/leaderboard.sqlite3`` (default ``F:\\Nova\\leaderboard``), table ``halt_events``
(``backend/leaderboard/schema.py``): one row per halt start or end, ``ts`` in epoch seconds, ``session_date`` the
ET calendar day of ``ts``. Read-only. Two sources, each under its own name, never merged into one row:

  nasdaq_trade_halt_rss  Nasdaq Trader's Trade Halt RSS: the official halt time (start) and trade resumption
                         (end), each row carrying the halt's code. 2021-09-21 .. 2026-09-21 is a backfill of
                         Nasdaq's history pages (``research/catalysts/backfill_halts.py``); from 2026-09-22 on the
                         live desk's own poll (``leaderboard/halts.py``). History pages show a halt's FINAL code: a
                         news halt that opened as T1 reads T3 once resolved. One stray 2019-02-22 start (a T12 still
                         listed years later) predates the backfill. Market-wide circuit breaker rows are not logged.
  ibkr_ticker_halted     IBKR's ``ticker.halted`` transitions the live desk saw (2026-09-23 on), only for symbols
                         the desk held a Level 1 line on; an end carries no code. Code ``2`` = LULD, ``1`` =
                         general / news (``ibkr/halt_eta.py``).

Nasdaq's pages from 2026-03-12 to 2026-09-18 (and single rows on 2025-09-26 .. 2026-03-11) pad the halt time
(``"06:55:00      .000"``); ``ibkr/nasdaq_halt_rss.py`` parses it since #1069 and those 8,030 starts were reloaded
2026-10-18. A halt whose start the log still lacks is answered with ``start_ts`` None: its resumption is real, its
start is unknown -- never invented.

Codes, only as the repo describes them: T1 news pending, T2 news released, T3 news and resumption times, T12 the
other news-pending code (T1 / T12: ``CATALYST_NEWS_PENDING_CODES``); T1-T3 and T12 are news halts
(``MOVE_NEWS_HALT_CODES``); LUDP a LULD pause, M a volatility pause (``MOVE_VOLATILITY_HALT_CODES``); LUDP, LUDS
and M are the LULD pauses ``luld/records.py`` counts. D, H11, T8 and the rest: Nasdaq's, not described in the repo.

Rule: a halt counts at its start ``ts`` (its ``session_date``); times are ET. A start is paired with the next end of
the same symbol and source, even on a later day. A day before 2021-09-21 is not covered: no row is not "no halt".
"""
from __future__ import annotations

import os
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from market_reads import REPO  # noqa: F401  (REPO puts backend/ on sys.path)

from constants_catalysts import CATALYST_NEWS_PENDING_CODES
from constants_leaderboard import (
    LEADERBOARD_DB_FILENAME,
    LEADERBOARD_DEFAULT_ROOT_WIN,
    LEADERBOARD_DIR_ENV,
    LEADERBOARD_HALT_EVENT_END,
    LEADERBOARD_HALT_EVENT_START,
    LEADERBOARD_HALT_SOURCE_IBKR,
    LEADERBOARD_HALT_SOURCE_NASDAQ,
)
from constants_move_reason import MOVE_LULD_HALT_KINDS, MOVE_NEWS_HALT_CODES, MOVE_VOLATILITY_HALT_CODES

ET = ZoneInfo("America/New_York")
SOURCES = (LEADERBOARD_HALT_SOURCE_NASDAQ, LEADERBOARD_HALT_SOURCE_IBKR)
COVERED_FROM = "2021-09-21"          # the first Nasdaq history page backfilled
LULD = {c.upper() for c in (*MOVE_LULD_HALT_KINDS, *MOVE_VOLATILITY_HALT_CODES, "LUDS")}
RULE = "a halt counts at its start ts (its session_date); times ET"
COVERAGE = (f"Nasdaq Trade Halt RSS: backfilled history {COVERED_FROM}..2026-09-21, the live desk's poll after; "
            "a resumption whose start is not logged has start_ts None. IBKR ticker.halted: live desk "
            f"only, 2026-09-23 on, desk-streamed symbols only. Before {COVERED_FROM}: not covered (no row is not "
            "'no halt').")
CODES = {"T1": "news pending", "T2": "news released", "T3": "news and resumption times (a resolved news halt)",
         "T12": "news pending", "LUDP": "LULD pause", "LUDS": "LULD pause", "M": "volatility pause",
         "luld / 2 (IBKR)": "LULD", "regulatory / 1 (IBKR)": "general / news",
         "other (D, H11, T8, ...)": "Nasdaq's code, not described in the repo"}
SOURCE_ALIASES = {"nasdaq": LEADERBOARD_HALT_SOURCE_NASDAQ, "ibkr": LEADERBOARD_HALT_SOURCE_IBKR}
EVENT_COLUMNS = ["symbol", "session_date", "source", "event", "code", "kind", "ts", "et", "recorded_ts"]
HALT_COLUMNS = ["symbol", "session_date", "source", "code", "kind", "start_ts", "start_et", "end_ts", "end_date",
                "end_et", "duration_s", "resumed"]
_PARAM_CHUNK = 900


def db_path() -> Path:
    return Path(os.environ.get(LEADERBOARD_DIR_ENV) or LEADERBOARD_DEFAULT_ROOT_WIN) / LEADERBOARD_DB_FILENAME


def _connect() -> sqlite3.Connection:
    path = db_path()
    if not path.is_file():
        raise LookupError(f"{path} is not on disk (the leaderboard store; {LEADERBOARD_DIR_ENV} moves it)")
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=30.0)


def _et(ts: float | None, fmt: str = "%H:%M:%S") -> str | None:
    return None if ts is None else datetime.fromtimestamp(float(ts), ET).strftime(fmt)


def is_luld(code: Any, kind: Any) -> bool:
    return str(code or "").upper() in LULD or str(kind or "").upper() in LULD


def is_news(code: Any) -> bool:
    return any(part in MOVE_NEWS_HALT_CODES for part in str(code or "").upper().split("/"))


def _bounds(symbol, day, date_from, date_to) -> tuple[str | None, str | None]:
    if day and (date_from or date_to):
        raise ValueError("pass day= or date_from= / date_to=, not both")
    if day:
        return day, day
    if not symbol and not (date_from or date_to):
        raise ValueError("a halt read needs a symbol, a day or a date range (date_from / date_to): the whole log "
                         "is not one answer")
    return date_from, date_to


def _rows(db: sqlite3.Connection, symbol, lo, hi, source) -> list[dict[str, Any]]:
    sql, args = "SELECT symbol, ts, event, kind, code, source, session_date, recorded_ts FROM halt_events WHERE 1=1", []
    if symbol:
        sql, args = sql + " AND symbol = ?", [*args, symbol.strip().upper()]
    if lo:
        sql, args = sql + " AND session_date >= ?", [*args, lo]
    if hi:
        sql, args = sql + " AND session_date <= ?", [*args, hi]
    if source:
        source = SOURCE_ALIASES.get(source.lower(), source)
        if source not in SOURCES:
            raise ValueError(f"source {source!r}: one of {', '.join(SOURCES)} (or nasdaq / ibkr)")
        sql, args = sql + " AND source = ?", [*args, source]
    cols = ("symbol", "ts", "event", "kind", "code", "source", "session_date", "recorded_ts")
    return [dict(zip(cols, r, strict=True)) for r in db.execute(sql + " ORDER BY symbol, source, ts", args)]


def _neighbour(db: sqlite3.Connection, symbol: str, source: str, ts: float, after: bool) -> dict[str, Any] | None:
    """The event of ``symbol`` / ``source`` just after (or just before) ``ts``, any day."""
    op, order = (">", "ASC") if after else ("<", "DESC")
    row = db.execute(f"SELECT event, ts, session_date FROM halt_events WHERE symbol = ? AND source = ? AND ts {op} ?"
                     f" ORDER BY ts {order} LIMIT 1", [symbol, source, float(ts)]).fetchone()
    return None if row is None else {"event": row[0], "ts": float(row[1]), "session_date": row[2]}


def _halt(start: dict | None, end: dict | None) -> dict[str, Any]:
    first = start or end
    s_ts = None if start is None else float(start["ts"])
    e_ts = None if end is None else float(end["ts"])
    code = (start or {}).get("code") or (end or {}).get("code")
    kind = (start or {}).get("kind") or (end or {}).get("kind")
    return {"symbol": first["symbol"], "session_date": first["session_date"], "source": first["source"],
            "code": code, "kind": kind, "start_ts": s_ts, "start_et": _et(s_ts), "end_ts": e_ts,
            "end_date": None if end is None else end["session_date"], "end_et": _et(e_ts),
            "duration_s": None if s_ts is None or e_ts is None else round(e_ts - s_ts, 3), "resumed": end is not None}


def _pair(db: sqlite3.Connection, events: list[dict[str, Any]], *, look_ahead: bool) -> list[dict[str, Any]]:
    """Events of one symbol and source, oldest first, as halts. An end whose start is an earlier day's (the event
    before it is a start) belongs to that day and is dropped; an end with no start before it is a halt whose start
    is unknown. ``look_ahead`` finds the end of a halt still open at the last event, on a later day."""
    out: list[dict[str, Any]] = []
    open_start: dict[str, Any] | None = None
    for i, ev in enumerate(events):
        if ev["event"] == LEADERBOARD_HALT_EVENT_START:
            if open_start is not None:
                out.append(_halt(open_start, None))
            open_start = ev
        elif ev["event"] == LEADERBOARD_HALT_EVENT_END:
            if open_start is not None:
                out.append(_halt(open_start, ev))
                open_start = None
            elif i > 0:
                out.append(_halt(None, ev))
            else:
                before = _neighbour(db, ev["symbol"], ev["source"], ev["ts"], after=False)
                if before is None or before["event"] != LEADERBOARD_HALT_EVENT_START:
                    out.append(_halt(None, ev))
    if open_start is not None:
        nxt = _neighbour(db, open_start["symbol"], open_start["source"], open_start["ts"], after=True) \
            if look_ahead else None
        end = None if nxt is None or nxt["event"] != LEADERBOARD_HALT_EVENT_END else \
            {**open_start, "event": nxt["event"], "ts": nxt["ts"], "session_date": nxt["session_date"]}
        out.append(_halt(open_start, end))
    return out


def _grouped(events: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for ev in events:
        groups[(ev["symbol"], ev["source"])].append(ev)
    return groups


def _attrs(frame: pd.DataFrame, **asked: Any) -> pd.DataFrame:
    early = asked.get("date_from") is None or asked["date_from"] < COVERED_FROM
    frame.attrs.update(asked=asked, rule=RULE, units="ts / start_ts / end_ts epoch seconds; *_et HH:MM:SS ET; "
                       "duration_s seconds", coverage=COVERAGE, covered_from=COVERED_FROM, codes=CODES,
                       source=str(db_path()), news_pending_codes=list(CATALYST_NEWS_PENDING_CODES),
                       warning=f"days before {COVERED_FROM} are not covered: no row there is unknown, not 'no halt'"
                       if early else None)
    return frame


def events(symbol: str | None = None, day: str | None = None, date_from: str | None = None,
           date_to: str | None = None, source: str | None = None) -> pd.DataFrame:
    """The raw halt log: one row per start or end (``EVENT_COLUMNS``), by symbol, source and time."""
    lo, hi = _bounds(symbol, day, date_from, date_to)
    with closing(_connect()) as db:
        rows = _rows(db, symbol, lo, hi, source)
    for row in rows:
        row["et"] = _et(row["ts"])
    frame = pd.DataFrame(rows, columns=EVENT_COLUMNS)
    return _attrs(frame, symbol=symbol, date_from=lo, date_to=hi, source=source)


def code_matches(code: Any, kind: Any, wanted: set[str]) -> bool:
    """Whether a halt is one of ``wanted``: codes as Nasdaq / IBKR write them (``T1``, ``LUDP`` ...), or the group
    words ``news`` (T1-T3, T12) and ``luld`` (LULD and volatility pauses)."""
    if ("news" in wanted and is_news(code)) or ("luld" in wanted and is_luld(code, kind)):
        return True
    return bool({str(code or "").upper(), str(kind or "").upper()} & {w.upper() for w in wanted})


def halts(symbol: str | None = None, day: str | None = None, date_from: str | None = None,
          date_to: str | None = None, source: str | None = None, codes: list[str] | None = None) -> pd.DataFrame:
    """One row per halt (``HALT_COLUMNS``) that started in the range, oldest first. A halt still open at the range's
    end gets its resumption from a later day when the log has one (``end_date`` says which); ``resumed`` False
    means none is logged. ``start_ts`` None: a resumption whose start the log lacks. Since 2026-09-23 one halt can
    appear twice, once per source. ``codes`` keeps the halts of those codes (``code_matches``)."""
    lo, hi = _bounds(symbol, day, date_from, date_to)
    wanted = {str(c).strip().lower() for c in codes or () if str(c).strip()}
    with closing(_connect()) as db:
        out = [h for evs in _grouped(_rows(db, symbol, lo, hi, source)).values()
               for h in _pair(db, evs, look_ahead=True)]
    if wanted:
        out = [h for h in out if code_matches(h["code"], h["kind"], wanted)]
    frame = pd.DataFrame(out, columns=HALT_COLUMNS)
    if len(frame):
        frame = frame.assign(_t=frame["start_ts"].fillna(frame["end_ts"])).sort_values(["_t", "symbol"]) \
            .drop(columns="_t").reset_index(drop=True)
    return _attrs(frame, symbol=symbol, date_from=lo, date_to=hi, source=source, codes=sorted(wanted) or None)


def _chunks(by_day: dict[str, set[str]]):
    days, symbols = [], set()
    for d in sorted(by_day):
        if days and len(days) + len(symbols | by_day[d]) + 1 > _PARAM_CHUNK:
            yield days, symbols
            days, symbols = [], set()
        days.append(d)
        symbols |= by_day[d]
    if days:
        yield days, symbols


def for_pairs(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
    """``(day, symbol)`` -> ``{halts, first_halt_et, codes, luld, news, start_unknown, source, covered}`` for many
    stock-days in chunked reads. One source per stock-day: Nasdaq's when it logged any event that day, else IBKR's.
    ``halts`` counts the halts that started that day (``start_unknown`` of them a resumption with no logged start);
    ``luld`` those that were LULD / volatility pauses, ``news`` the news halts. A day the log does not cover
    (before 2021-09-21, or after its newest day) answers ``halts`` None, never 0."""
    by_day: dict[str, set[str]] = defaultdict(set)
    for day, symbol in pairs:
        by_day[str(day)[:10]].add(str(symbol).strip().upper())
    found: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    with closing(_connect()) as db:
        newest = db.execute("SELECT max(session_date) FROM halt_events").fetchone()[0] or ""
        cols = ("symbol", "ts", "event", "kind", "code", "source", "session_date", "recorded_ts")
        for days, symbols in _chunks(by_day):
            sql = (f"SELECT {', '.join(cols)} FROM halt_events WHERE session_date IN ({', '.join('?' * len(days))})"
                   f" AND symbol IN ({', '.join('?' * len(symbols))}) ORDER BY symbol, source, ts")
            for row in db.execute(sql, [*days, *sorted(symbols)]):
                ev = dict(zip(cols, row, strict=True))
                if ev["symbol"] in by_day.get(ev["session_date"], ()):
                    found[(ev["session_date"], ev["symbol"])].append(ev)
        for day, symbols in by_day.items():
            covered = COVERED_FROM <= day <= newest
            for symbol in symbols:
                evs = found.get((day, symbol), [])
                pick = LEADERBOARD_HALT_SOURCE_NASDAQ if any(e["source"] == LEADERBOARD_HALT_SOURCE_NASDAQ
                                                             for e in evs) else LEADERBOARD_HALT_SOURCE_IBKR
                mine = [h for h in _pair(db, [e for e in evs if e["source"] == pick], look_ahead=False)
                        if h["session_date"] == day]
                starts = sorted(h["start_ts"] for h in mine if h["start_ts"] is not None)
                out[(day, symbol)] = {
                    "halts": len(mine) if covered or mine else None,
                    "first_halt_et": _et(starts[0]) if starts else None,
                    "codes": sorted({str(h["code"] or h["kind"]) for h in mine if h["code"] or h["kind"]}),
                    "luld": sum(is_luld(h["code"], h["kind"]) for h in mine),
                    "news": sum(is_news(h["code"]) for h in mine),
                    "start_unknown": sum(h["start_ts"] is None for h in mine),
                    "source": pick if mine else None, "covered": covered}
    return out
