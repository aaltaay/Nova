"""One session's inputs for the signal table, read once for every in-play stock-day of the day: the universe (from
the relative-volume table), the minute bars with their opens (the Massive minute file), each stock's relative volume by
minute, its prior sessions (for "has it run before"), its catalyst items, the boards, the halt log, SEC's share count
and a rebuilt HOD Momo day's alerts. Every reader is the store's own owner or the front door; nothing here judges --
``evaluate.py`` runs the desk's rules over what this read.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from market_reads import inventory, rvol
from market_reads import rvol_store as rs
from market_reads import signals_store as ss

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
MINUTES = "minute_aggs_v1"
BAR_COLUMNS = {"ticker": pa.string(), "volume": pa.float64(), "open": pa.float64(), "close": pa.float64(),
               "high": pa.float64(), "low": pa.float64(), "window_start": pa.int64()}
HISTORY_SESSIONS = 260           # STOCK_READ_HISTORY_READ_DAYS: the daily bars the desk reads for its runs
LINE_EPS = 1e-9

UNIVERSE_SQL = f"""
WITH d AS (
  SELECT symbol, kind, prev_close, epoch, basis, day_avg_volume, day_avg_sessions, base_sessions
  FROM read_parquet($dfile)
  WHERE kind IN ({", ".join(f"'{k}'" for k in ss.KINDS)}) AND prev_close BETWEEN {ss.PRICE_MIN} AND {ss.PRICE_MAX}
    AND coalesce(split, '') <> 'likely_split' AND base_sessions >= {ss.MIN_BASE_SESSIONS})
SELECT d.*, min(x.m) FILTER (WHERE x.m <= {ss.LAST_M} AND x.cum >= {ss.IN_PLAY_VOLUME} AND (
         x.close >= d.prev_close * {1 + ss.IN_PLAY_CHANGE} * {1 - LINE_EPS}
         OR (x.base > 0 AND x.cum >= {ss.IN_PLAY_RVOL} * x.base))) AS in_play_m
FROM d JOIN read_parquet($mfile) x USING (symbol)
GROUP BY ALL HAVING in_play_m IS NOT NULL ORDER BY symbol"""


@dataclass
class DayInputs:
    day: str
    universe: pd.DataFrame
    bars: dict[str, pd.DataFrame]                 # symbol -> m, open, high, low, close, volume (04:00-20:00)
    rvol: dict[str, pd.DataFrame]                 # symbol -> m, cum, base, vol5, base5
    history: dict[str, list[dict[str, Any]]]      # symbol -> prior sessions [{d, h, c, state}] on today's basis
    catalysts: dict[str, tuple[list[dict], list[str]]] = field(default_factory=dict)
    boards: dict[str, list[tuple[float, str]]] = field(default_factory=dict)   # symbol -> [(minute_ts, board)]
    board_minutes: list[float] = field(default_factory=list)
    halt_events: list[dict[str, Any]] | None = None
    halt_prior: list[dict[str, Any]] | None = None
    floats: dict[str, dict[str, Any]] = field(default_factory=dict)
    hod: dict[str, list[dict[str, Any]]] | None = None
    coverage: dict[str, Any] = field(default_factory=dict)


def ts_of(day: str, m: int | float) -> float:
    """Epoch seconds of minute ``m`` (minutes after ET midnight) on ``day``."""
    return datetime.combine(date.fromisoformat(day), dtime(0, 0), ET).timestamp() + float(m) * 60.0


def minute_file(day: str) -> Path | None:
    found = inventory.day_files(MINUTES, day, day)
    return found[0] if found else None


def universe(con, day: str) -> pd.DataFrame:
    frame = con.execute(UNIVERSE_SQL, {"dfile": rvol.posix([rs.days_path(day)])[0],
                                       "mfile": rvol.posix([rs.minutes_path(day)])[0]}).df()
    frame["in_play_m"] = frame["in_play_m"].astype(np.int64)
    return frame


def read_bars(path: Path, day: str, symbols: list[str]) -> dict[str, pd.DataFrame]:
    """The minute file's bars 04:00-20:00 ET for ``symbols`` (m = the bar's start, minutes after ET midnight)."""
    table = pacsv.read_csv(path, convert_options=pacsv.ConvertOptions(
        include_columns=list(BAR_COLUMNS), column_types=BAR_COLUMNS, strings_can_be_null=False))
    table = table.filter(pc.is_in(table.column("ticker"), value_set=pa.array(symbols)))
    midnight = int(datetime.combine(date.fromisoformat(day), dtime(0, 0), ET).timestamp())
    frame = table.to_pandas()
    frame["m"] = (frame["window_start"] // 10**9 - midnight) // 60
    frame = frame[(frame["m"] >= rs.SESSION_START_M) & (frame["m"] < rs.SESSION_END_M)]
    frame = frame.sort_values(["ticker", "m"])
    cols = ["m", "open", "high", "low", "close", "volume"]
    return {s: g[cols].reset_index(drop=True) for s, g in frame.groupby("ticker", sort=False)}


def read_rvol(con, day: str, symbols: list[str]) -> dict[str, pd.DataFrame]:
    con.register("want", pd.DataFrame({"symbol": symbols}))
    frame = con.execute("SELECT symbol, m, cum, base, vol5, base5 FROM read_parquet($mfile) JOIN want USING (symbol) "
                        "ORDER BY symbol, m", {"mfile": rvol.posix([rs.minutes_path(day)])[0]}).df()
    return {s: g.drop(columns="symbol").reset_index(drop=True) for s, g in frame.groupby("symbol", sort=False)}


def read_history(con, day: str, uni: pd.DataFrame, built: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Each stock's prior sessions in the table (at most ``HISTORY_SESSIONS``, the same epoch), oldest first, on
    today's share basis: ``{d, h, c, state: 'final'}`` with ``h`` the 04:00-20:00 high and ``c`` the last trade -- the
    desk's stored daily bars close on the last extended-hours trade too (``stock_read/history.runs``)."""
    at = built.index(day) if day in built else len(built)
    prior = built[max(0, at - HISTORY_SESSIONS):at]
    out: dict[str, list[dict[str, Any]]] = {s: [] for s in uni["symbol"]}
    if not prior:
        return out
    con.register("want", uni[["symbol", "epoch", "basis"]].rename(columns={"basis": "basis_now"}))
    frame = con.execute(
        "SELECT x.symbol, CAST(x.date AS VARCHAR) AS d, x.hi * x.basis / w.basis_now AS h, "
        "x.last_close * x.basis / w.basis_now AS c FROM read_parquet($files) x JOIN want w "
        "ON x.symbol = w.symbol AND x.epoch = w.epoch WHERE x.hi IS NOT NULL ORDER BY x.symbol, x.date",
        {"files": rvol.posix(rs.days_path(d) for d in prior)}).df()
    for s, g in frame.groupby("symbol", sort=False):
        out[s] = [{"d": d, "h": float(h), "c": float(c), "state": "final"}
                  for d, h, c in zip(g["d"], g["h"], g["c"], strict=True)]
    return out


def read_catalysts(day: str, symbols: list[str]) -> dict[str, tuple[list[dict], list[str]]]:
    from catalysts import windows

    from market_reads import catalysts
    start = windows.window_start(ts_of(day, rs.SESSION_START_M))
    try:
        return catalysts.day_items(day, symbols, start, ts_of(day, rs.RTH_CLOSE_M))
    except Exception as exc:     # no catalyst store: every catalyst reads not_checked, said in coverage
        logger.warning("signals %s: catalyst items unread: %s", day, exc)
        return {s: ([], []) for s in symbols}


def read_boards(day: str, symbols: set[str]) -> tuple[dict[str, list[tuple[float, str]]], list[float], str | None]:
    """Each symbol's board at every covered minute, as ``find_board_row`` would pick it from that minute's rows
    (``BOARD_ORDER``), the covered minutes, and the store's source for the day."""
    from leaderboard import playback
    from leaderboard import store as lb_store
    from strategy.symbol_pillars import BOARD_ORDER

    db = lb_store.read_only()
    if db is None:
        return {}, [], None
    try:
        source = playback._default_source(db, day)
        covered = sorted({float(r[0]) for r in db.execute(
            "SELECT DISTINCT minute_ts FROM coverage WHERE session_date = ? AND source = ?", (day, source))})
        rows = db.execute("SELECT minute_ts, board, symbol FROM rows WHERE session_date = ? AND source = ?",
                          (day, source)).fetchall()
    finally:
        db.close()
    # A rebuilt day's top-50 ``market`` board is not one the desk names: kept under its own name, after the desk's.
    rank = {name: i for i, name in enumerate((*BOARD_ORDER, "market"))}
    best: dict[tuple[str, float], str] = {}
    for minute_ts, board, symbol in rows:
        name = board
        if symbol not in symbols or name not in rank:
            continue
        key = (symbol, float(minute_ts))
        if key not in best or rank[name] < rank[best[key]]:
            best[key] = name
    out: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for (symbol, minute_ts), name in sorted(best.items(), key=lambda kv: kv[0][1]):
        out[symbol].append((minute_ts, name))
    return dict(out), covered, source


def read_halts(day: str, built: list[str]) -> tuple[list[dict] | None, list[dict] | None]:
    from leaderboard import store as lb_store

    db = lb_store.read_only()
    if db is None:
        return None, None
    import sqlite3
    db.row_factory = sqlite3.Row
    try:
        today = [dict(r) for r in lb_store.halt_events(db, day)]
        at = built.index(day) if day in built else 0
        prior = [dict(r) for r in lb_store.halt_events(db, built[at - 1])] if at > 0 else []
    finally:
        db.close()
    return today, prior


def read_floats(day: str, symbols: list[str]) -> dict[str, dict[str, Any]]:
    from day_movers import floats
    from day_movers import store as dm_store

    db = dm_store.read_only()
    if db is None:
        return {}
    # Filed by the day before: a count filed during the day (a 10-Q at 16:05) is not known at its 09:30.
    before = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    try:
        got = floats.sec_shares(db, [(before, s) for s in symbols])
    finally:
        db.close()
    return {s: v for (_d, s), v in got.items()}


def read_hod(day: str, symbols: set[str]) -> dict[str, list[dict[str, Any]]] | None:
    """A rebuilt HOD Momo day's alerts by symbol (oldest first), or None when the day was not rebuilt."""
    try:
        from hod_momo_rebuild import store as hod_store
        path = hod_store.data_path(day)
    except Exception:
        return None
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for a in data.get("alerts") or []:
        if a.get("ticker") in symbols:
            out[a["ticker"]].append({"ts": float(a.get("created_ts") or 0.0), "price": a.get("price"),
                                     "strategy": a.get("strategy_name") or a.get("strategy_id")})
    return dict(out)


def load(con, day: str, built: list[str]) -> DayInputs:
    """Everything one session needs (``built``: the relative-volume table's sessions, oldest first)."""
    uni = universe(con, day)
    symbols = uni["symbol"].tolist()
    path = minute_file(day)
    bars = read_bars(path, day, symbols) if path is not None and symbols else {}
    keep = [s for s in symbols if s in bars]
    uni = uni[uni["symbol"].isin(keep)].reset_index(drop=True)
    if not keep:
        return DayInputs(day, uni, {}, {}, {}, coverage={"stock_days": 0})
    inputs = DayInputs(day, uni, bars, read_rvol(con, day, keep), read_history(con, day, uni, built))
    inputs.catalysts = read_catalysts(day, keep)
    inputs.boards, inputs.board_minutes, board_source = read_boards(day, set(keep))
    inputs.halt_events, inputs.halt_prior = read_halts(day, built)
    inputs.floats = read_floats(day, keep)
    inputs.hod = read_hod(day, set(keep))
    inputs.coverage = {
        "stock_days": len(keep), "board": board_source if inputs.board_minutes else None,
        "board_minutes": len(inputs.board_minutes),
        "halts": inputs.halt_events is not None and day >= "2021-09-21",
        "catalyst_checked": sum(1 for s in keep if inputs.catalysts.get(s, ([], []))[1]),
        "float_known": len(inputs.floats), "hod_rebuilt": inputs.hod is not None}
    return inputs
