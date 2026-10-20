"""Reads of the signal table (``signals_store.py``; schema: ``architecture/schema/agent-desk.md``, "The Trader's
signals on past days, and mixing them"): one stock-day minute by minute (``series``), every in-play stock at a minute
(``scan``), and the first minute a mix of signals all held (``entries``, which ``signal_outcomes`` scores).

A condition (``signal_registry.check``) is ``{signal, is}`` -- one value or a list -- or ``{signal, min?, max?}`` for a
number; its column and values come only from the registry, so a query never carries text it did not list.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from market_reads import rvol
from market_reads import signal_registry as reg
from market_reads import signals_store as ss

FILTERS = ("date_from", "date_to", "symbol", "price_min", "price_max")
CHUNK_DAYS = 366


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return "'" + str(value).replace("'", "''") + "'"


def predicate(conditions: list[dict[str, Any]]) -> str:
    """The SQL test that every condition holds on a row of ``x`` (minutes) joined with ``t`` (tape)."""
    parts = []
    for c in conditions:
        column = ("t." if c["signal"] in reg.TAPE_COLUMNS else "x.") + c["signal"]
        if "is" in c:
            parts.append(f"{column} IN ({', '.join(_literal(v) for v in c['is'])})")
            continue
        if c.get("min") is not None:
            parts.append(f"{column} >= {float(c['min'])!r}")
        if c.get("max") is not None:
            parts.append(f"{column} <= {float(c['max'])!r}")
    return " AND ".join(f"({p})" for p in parts) or "true"


def uses_tape(conditions: list[dict[str, Any]]) -> bool:
    return any(c["signal"] in reg.TAPE_COLUMNS for c in conditions)


def check_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    filters = {k: v for k, v in dict(filters or {}).items() if v is not None}
    unknown = sorted(set(filters) - set(FILTERS))
    if unknown:
        raise ValueError(f"unknown filters {unknown}: the signal table takes {', '.join(FILTERS)}")
    if not (filters.get("symbol") or (filters.get("date_from") and filters.get("date_to"))):
        raise ValueError("name date_from and date_to, or a symbol")
    if "symbol" in filters:
        filters["symbol"] = str(filters["symbol"]).strip().upper()
    for key in ("price_min", "price_max"):
        if key in filters:
            filters[key] = float(filters[key])
    return filters


def day_sql(filters: dict[str, Any]) -> str:
    """The stock-day filters on ``d`` (the days file)."""
    where = ["true"]
    if filters.get("symbol"):
        where.append(f"d.symbol = {_literal(filters['symbol'])}")
    if filters.get("price_min") is not None:
        where.append(f"d.prev_close >= {filters['price_min']!r}")
    if filters.get("price_max") is not None:
        where.append(f"d.prev_close <= {filters['price_max']!r}")
    return " AND ".join(where)


def chunks(filters: dict[str, Any], tape: bool) -> tuple[list[list[str]], dict[str, Any], int]:
    """The built sessions asked for (only those the tape stage reached, when a condition reads the tape), a year at a
    time; the manifest; and how many asked-for sessions the tape stage had not reached."""
    manifest = ss.load_manifest(required=True)
    days = ss.built_days(manifest, filters.get("date_from"), filters.get("date_to"))
    skipped = 0
    if tape:
        reached = ss.tape_days(manifest)
        skipped = sum(1 for d in days if d not in reached)
        days = [d for d in days if d in reached]
    if not days:
        span = ss.built_days(manifest)
        raise LookupError(f"no built session in {filters.get('date_from')}..{filters.get('date_to')}"
                          f"{' that the tape stage reached' if tape else ''}: the table covers "
                          f"{span[0] if span else None}..{span[-1] if span else None} (build_signals.py)")
    out, current = [], []
    for day in days:
        if current and ss.rs.ordinal(day) - ss.rs.ordinal(current[0]) >= CHUNK_DAYS:
            out.append(current)
            current = []
        current.append(day)
    out.append(current)
    return out, manifest, skipped


def _from(days: list[str], tape: bool) -> tuple[str, dict[str, Any]]:
    args = {"mfiles": rvol.posix(ss.minutes_path(d) for d in days), "dfiles": rvol.posix(ss.days_path(d) for d in days)}
    sql = ("read_parquet($mfiles) x JOIN read_parquet($dfiles) d ON d.date = x.date AND d.symbol = x.symbol")
    if tape:
        args["tfiles"] = rvol.posix(ss.tape_path(d) for d in days)
        sql += " LEFT JOIN read_parquet($tfiles) t ON t.date = x.date AND t.symbol = x.symbol AND t.m = x.m"
    return sql, args


def _tape_columns(tape: bool) -> str:
    if not tape:
        return ""
    return (", coalesce(t.tape, 'not_built') AS tape, t.tape_score, t.tape_flush, t.tape_burst")


def series(symbol: str, day: str, signals: list[str] | None = None) -> pd.DataFrame:
    """One stock-day's rows, minute by minute (``time_et`` the minute's start; each value as of its end)."""
    manifest = ss.load_manifest(required=True)
    if day not in manifest["days"]:
        raise LookupError(f"{day} is not in the signal table (build_signals.py --start {day} --end {day})")
    wanted = list(signals or reg.MINUTE_COLUMNS + reg.TAPE_COLUMNS)
    unknown = [s for s in wanted if s not in reg.BY_COLUMN]
    if unknown:
        raise ValueError(f"unknown signals {unknown}; signal_catalog lists them")
    tape = day in ss.tape_days(manifest) and any(s in reg.TAPE_COLUMNS for s in wanted)
    source, args = _from([day], tape)
    cols = ", ".join(f"x.{c}" for c in wanted if c not in reg.TAPE_COLUMNS)
    con = rvol.connect()
    try:
        frame = con.execute(f"SELECT x.m, d.in_play_m{', ' + cols if cols else ''}{_tape_columns(tape)} FROM {source} "
                            f"WHERE x.symbol = {_literal(symbol.strip().upper())} ORDER BY x.m", args).df()
    finally:
        con.close()
    if not len(frame):
        raise LookupError(f"{symbol.upper()} was not in play on {day} (signal_scan lists who was)")
    if not tape:
        for c in (c for c in wanted if c in reg.TAPE_COLUMNS):
            frame[c] = "not_built" if c == "tape" else None
    frame.insert(0, "time_et", frame.pop("m").map(rvol.hhmm))
    frame.insert(1, "in_play_et", frame.pop("in_play_m").map(rvol.hhmm))
    return frame


def scan(day: str, at: str, when: list[dict[str, Any]] | None = None) -> pd.DataFrame:
    """Every stock in play by ``at`` (ET HH:MM: the minute before it, as of its end) on ``day``, with its signals;
    only those meeting every condition of ``when`` when given."""
    conditions = reg.check(when) if when else []
    manifest = ss.load_manifest(required=True)
    if day not in manifest["days"]:
        raise LookupError(f"{day} is not in the signal table")
    m = rvol.minute_of(at, "at") - 1
    tape = day in ss.tape_days(manifest)
    if uses_tape(conditions) and not tape:
        raise LookupError(f"the tape stage has not reached {day} (build_signals.py --stage tape)")
    source, args = _from([day], tape)
    con = rvol.connect()
    try:
        frame = con.execute(f"SELECT x.symbol, d.prev_close, d.in_play_m, x.* EXCLUDE (date, symbol, m)"
                            f"{_tape_columns(tape)} FROM {source} WHERE x.m = {int(m)} AND {predicate(conditions)} "
                            "ORDER BY x.rvol DESC NULLS LAST, x.symbol", args).df()
    finally:
        con.close()
    frame.insert(2, "in_play_et", frame.pop("in_play_m").map(rvol.hhmm))
    return frame


def entries_sql(conditions: list[dict[str, Any]], w0: int, w1: int, filters: dict[str, Any], tape: bool) -> str:
    """Per in-play stock-day: the first minute in ``[w0, w1)`` where every condition held (``trigger_m``), its price,
    and whether they all held at a minute before ``w0`` (``held_before``)."""
    test = predicate(conditions)
    return f"""
SELECT x.date, x.symbol, any_value(d.prev_close) AS prev_close, any_value(d.in_play_m) AS in_play_m,
       any_value(d.epoch) AS epoch, any_value(d.basis) AS basis,
       min(x.m) FILTER (WHERE x.m >= {w0} AND x.m < {w1} AND {test}) AS trigger_m,
       arg_min(x.price, x.m) FILTER (WHERE x.m >= {w0} AND x.m < {w1} AND {test}) AS price,
       coalesce(bool_or({test}) FILTER (WHERE x.m < {w0}), false) AS held_before
FROM {_from([], tape)[0]} WHERE {day_sql(filters)} GROUP BY x.date, x.symbol"""


def run(days: list[str], sql: str, tape: bool) -> pd.DataFrame:
    _, args = _from(days, tape)
    con = rvol.connect()
    try:
        return con.execute(sql, args).df()
    finally:
        con.close()
