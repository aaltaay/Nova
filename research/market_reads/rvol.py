"""Relative volume across every stock (#1100): reads of the relative-volume table (``rvol_store``) through DuckDB.

Three measures, each as of the end of a minute (bars starting at or before it; at a clock time ``HH:MM``, the bars
starting before it), each against the symbol's baseline sessions (``rvol_store.RULES``):
  cumulative   ``rvol``       volume since 04:00 / the baseline sessions' mean volume to the same minute
  five_minute  ``rvol_5m``    volume of the last five minutes / the baseline sessions' mean of the same five minutes
  daily_rate   ``rvol_daily`` volume since 04:00 / the mean whole-session volume of up to 50 sessions
A zero or missing baseline is a null measure, never infinite. Prices are raw; ``prev_close`` is on the day's share
basis (listed splits); ``change_pct`` is percent points.

``scan`` answers every stock-day as of one clock time. At a minute where a stock had no bar the table holds no
baseline for it, so the baseline is computed here from the baseline sessions' own bars before that time -- the same
rule the builder uses, so at a bar minute both agree. ``triggers`` finds the first bar in a window where a measure
crosses a line, from the baselines the table stores. Reads go a year at a time (bounded memory beside the desk) under
one heavy-read slot.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.compute as pc

from market_reads import rvol_store as rs
from market_reads import slots

MEASURES = {"cumulative": "rvol", "five_minute": "rvol_5m", "daily_rate": "rvol_daily"}
SCAN_FILTERS = ("date_from", "date_to", "symbol", "price_min", "price_max", "rvol_min", "rvol_max", "volume_min",
                "change_min", "change_max")
TRIGGER_FILTERS = ("date_from", "date_to", "symbol", "price_min", "price_max", "volume_min", "change_min",
                   "change_max")
DEFAULT_KINDS = ("CS", "ADRC")
SPLITS = ("exclude_likely", "include", "only_suspects")
INLINE = 200
LIMIT_MAX = 1_000_000
CHUNK_DAYS = 366                 # one year of sessions per DuckDB pass
DUCKDB_THREADS = 4
DUCKDB_MEMORY = "2GB"
OUT_COLUMNS = ("date, symbol, kind, prev_close, price, price_et, change_pct, volume, base_volume, rvol, volume_5m, "
               "base_5m, rvol_5m, day_avg_volume, rvol_daily, base_sessions, day_avg_sessions, split")
UNITS = ("prices raw dollars (prev_close on the day's share basis); volume shares (Massive's minute file); "
         "change_pct percent points; *_et ET HH:MM (a bar's start); rvol* are ratios (5.0 = 5x)")


def minute_of(hhmm: str, what: str = "time") -> int:
    try:
        hh, mm = (int(p) for p in str(hhmm).split(":"))
    except ValueError:
        raise ValueError(f"{what} must be ET HH:MM, not {hhmm!r}") from None
    m = hh * 60 + mm
    if not rs.SESSION_START_M <= m <= rs.SESSION_END_M:
        raise ValueError(f"{what} {hhmm} is outside the table's session, 04:00-20:00 ET")
    return m


def hhmm(m) -> str | None:
    return None if m is None or pd.isna(m) else f"{int(m) // 60:02d}:{int(m) % 60:02d}"


def connect():
    import duckdb
    con = duckdb.connect()
    spill = Path(tempfile.gettempdir()) / "nova-rvol-duckdb"
    spill.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET threads TO {_env_threads()}")
    con.execute(f"SET memory_limit = '{DUCKDB_MEMORY}'")
    con.execute(f"SET temp_directory = '{spill.as_posix()}'")
    con.execute("SET preserve_insertion_order = false")
    con.execute("SET enable_progress_bar = false")     # it writes to the process's stdout: the MCP protocol
    return con


def posix(paths) -> list[str]:
    return [Path(p).as_posix() for p in paths]


def check(filters: dict[str, Any], known: tuple[str, ...], kinds, splits: str, measure: str) -> dict[str, Any]:
    filters = {k: v for k, v in (filters or {}).items() if v is not None}
    unknown = set(filters) - set(known)
    if unknown:
        raise ValueError(f"unknown filter(s) {sorted(unknown)}; known: {', '.join(known)}")
    if not (filters.get("symbol") or (filters.get("date_from") and filters.get("date_to"))):
        raise ValueError("name date_from and date_to, or a symbol (the table is every stock-day since 2016)")
    if splits not in SPLITS:
        raise ValueError(f"splits must be one of {', '.join(SPLITS)}")
    if measure not in MEASURES:
        raise ValueError(f"measure must be one of {', '.join(MEASURES)}")
    bad = [k for k in kinds or () if k not in rs.KINDS]
    if bad:
        raise ValueError(f"kinds {bad}: the table holds {', '.join(rs.KINDS)}")
    if filters.get("symbol"):
        filters["symbol"] = str(filters["symbol"]).strip().upper()
    return filters


def chunks(filters: dict[str, Any]) -> tuple[list[list[str]], dict[str, Any]]:
    """The built sessions asked for, a year at a time, and the table's manifest."""
    manifest = rs.load_manifest(required=True)
    days = rs.built_days(manifest, filters.get("date_from"), filters.get("date_to"))
    if not days:
        span = rs.built_days(manifest)
        raise LookupError(f"no built session in {filters.get('date_from')}..{filters.get('date_to')}: the table "
                          f"covers {span[0] if span else None}..{span[-1] if span else None} (build_rvol.py)")
    out, current = [], []
    for day in days:
        if current and rs.ordinal(day) - rs.ordinal(current[0]) >= CHUNK_DAYS:
            out.append(current)
            current = []
        current.append(day)
    out.append(current)
    return out, manifest


def universe_sql(filters: dict[str, Any], kinds, splits: str, sessions_column: str | None,
                 min_sessions: int, alias: str = "") -> str:
    """The stock-day filters every read shares (on a days row; ``alias`` prefixes the columns)."""
    a = f"{alias}." if alias else ""
    parts = [f"{a}kind IN (" + ", ".join(f"'{k}'" for k in (kinds or DEFAULT_KINDS)) + ")"]
    if splits == "exclude_likely":
        parts.append(f"coalesce({a}split, '') <> 'likely_split'")
    elif splits == "only_suspects":
        parts.append(f"{a}split IN ('likely_split', 'suspect')")
    if filters.get("price_min") is not None:
        parts.append(f"{a}prev_close >= {float(filters['price_min'])!r}")
    if filters.get("price_max") is not None:
        parts.append(f"{a}prev_close <= {float(filters['price_max'])!r}")
    if filters.get("symbol"):
        parts.append(f"{a}symbol = '{filters['symbol'].replace(chr(39), '')}'")
    if sessions_column and min_sessions:
        parts.append(f"{a}{sessions_column} >= {int(min_sessions)}")
    return " AND ".join(parts)


def sessions_column(measure: str) -> str:
    return "day_avg_sessions" if measure == "daily_rate" else "base_sessions"


def _scan_sql(at: int, filters: dict[str, Any], kinds, splits: str, measure: str, min_sessions: int) -> str:
    where = [universe_sql(filters, kinds, splits, sessions_column(measure), min_sessions)]
    ratio = MEASURES[measure]
    if filters.get("rvol_min") is not None:
        where.append(f"{ratio} >= {float(filters['rvol_min'])!r}")
    if filters.get("rvol_max") is not None:
        where.append(f"{ratio} <= {float(filters['rvol_max'])!r}")
    if filters.get("volume_min") is not None:
        where.append(f"volume >= {float(filters['volume_min'])!r}")
    if filters.get("change_min") is not None:
        where.append(f"change_pct >= {float(filters['change_min'])!r}")
    if filters.get("change_max") is not None:
        where.append(f"change_pct <= {float(filters['change_max'])!r}")
    n = rs.BASE_SESSIONS
    return f"""
WITH d AS (SELECT date, symbol, kind, prev_close, split, epoch, basis, base_sessions, day_avg_volume,
                  day_avg_sessions FROM read_parquet($dfiles)),
a AS (SELECT date, symbol, max(cum) AS cum_at, max(cum) - coalesce(max(cum) FILTER (WHERE m < {at - 5}), 0) AS vol5_at,
             arg_max(close, m) AS price, max(m) AS price_m
      FROM read_parquet($mfiles) WHERE m < {at} GROUP BY date, symbol),
j AS (SELECT d.*, coalesce(a.cum_at, 0) AS cum_at, coalesce(a.vol5_at, 0) AS vol5_at, a.price, a.price_m,
             coalesce(a.cum_at, 0) / d.basis AS c, coalesce(a.vol5_at, 0) / d.basis AS v
      FROM d LEFT JOIN a USING (date, symbol)),
w AS (SELECT *, sum(c) OVER r20 AS s20, sum(v) OVER r20 AS v20, count(*) OVER r20 AS k20,
             sum(c) OVER r100 AS s100, sum(v) OVER r100 AS v100, count(*) OVER r100 AS k100
      FROM j WINDOW r20 AS (PARTITION BY symbol, epoch ORDER BY date ROWS BETWEEN {n} PRECEDING AND 1 PRECEDING),
                    r100 AS (PARTITION BY symbol, epoch ORDER BY date
                             RANGE BETWEEN INTERVAL {rs.BASE_MAX_AGE_DAYS} DAYS PRECEDING AND INTERVAL 1 DAYS PRECEDING)),
x AS (SELECT *, least(k20, k100) AS k,
             CASE WHEN k100 < k20 THEN s100 ELSE s20 END * basis / nullif(least(k20, k100), 0) AS base_volume,
             CASE WHEN k100 < k20 THEN v100 ELSE v20 END * basis / nullif(least(k20, k100), 0) AS base_5m
      FROM w WHERE date BETWEEN $first AND $last),
y AS (SELECT date, symbol, kind, prev_close, price, price_m, (price / nullif(prev_close, 0) - 1) * 100 AS change_pct,
             cum_at AS volume, base_volume, cum_at / nullif(base_volume, 0) AS rvol, vol5_at AS volume_5m, base_5m,
             vol5_at / nullif(base_5m, 0) AS rvol_5m, day_avg_volume, cum_at / nullif(day_avg_volume, 0) AS rvol_daily,
             base_sessions, day_avg_sessions, split, epoch, basis FROM x)
SELECT * FROM y WHERE {' AND '.join(where)}"""


def _prefix(days: list[str], manifest: dict) -> list[str]:
    """The built sessions in the ``BASE_MAX_AGE_DAYS`` before ``days`` (a baseline reads them)."""
    since = (date.fromisoformat(days[0]) - timedelta(days=rs.BASE_MAX_AGE_DAYS)).isoformat()
    return [d for d in rs.built_days(manifest, since) if d < days[0]]


def _finish(parts: list[pd.DataFrame], sort_column: str | None, ascending: bool, limit: int | None) -> pd.DataFrame:
    frame = pd.concat([p for p in parts if len(p)], ignore_index=True) if any(len(p) for p in parts) else (
        parts[0] if parts else pd.DataFrame())
    if sort_column and len(frame):
        frame = frame.sort_values([sort_column, "date", "symbol"], ascending=[ascending, True, True],
                                  na_position="last", kind="stable")
    else:
        frame = frame.sort_values(["date", "symbol"], kind="stable") if len(frame) else frame
    return (frame.head(limit) if limit else frame).reset_index(drop=True)


def write_parts(parts_iter, out: Path | None, shape=None):
    """Stream each chunk's arrow table to ``out`` (when asked; ``shape`` -- default ``_shape`` -- makes the rows
    what the answer shows) and yield it on as a DataFrame."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    shape = shape or _shape
    writer, wrote, last = None, False, None
    if out is not None and out.exists():
        out.unlink()                         # the file holds this answer only, never an earlier one's rows
    try:
        for table in parts_iter:
            frame = table.to_pandas() if hasattr(table, "to_pandas") else table
            last = frame
            if out is not None and len(frame):
                shown = shape(frame)
                if out.suffix == ".csv":
                    shown.to_csv(out, mode="a", index=False, header=not wrote)
                else:
                    arrow = pa.Table.from_pandas(shown, preserve_index=False)
                    writer = writer or pq.ParquetWriter(out, arrow.schema, compression="zstd")
                    writer.write_table(arrow.cast(writer.schema))
                wrote = True
            yield frame
    finally:
        if writer is not None:
            writer.close()
        if out is not None and not wrote and last is not None:
            empty = shape(last.head(0))
            empty.to_csv(out, index=False) if out.suffix == ".csv" else empty.to_parquet(out, index=False)


INTERNAL = ("epoch", "basis")      # carried for the outcome reads, not answered


def _shape(frame: pd.DataFrame) -> pd.DataFrame:
    """Rows as answered: ``date`` ISO, each ``*_m`` minute as ``*_et`` ET HH:MM, internal columns dropped."""
    frame = frame.drop(columns=[c for c in INTERNAL if c in frame.columns])
    clocks = [c for c in frame.columns if c.endswith("_m")]
    if not len(frame):
        return frame.rename(columns={c: c[:-2] + "_et" for c in clocks})
    frame = frame.copy()
    frame["date"] = frame["date"].astype(str)
    for column in clocks:
        frame[column[:-2] + "_et"] = frame[column].map(hhmm)
    return frame.drop(columns=clocks)


def scan_tables(at: str, filters: dict[str, Any], measure: str, kinds, splits: str, min_base_sessions: int):
    """``(filters, groups, tables)``: the checked filters, the year chunks, and a generator of ``(days, arrow
    table)`` per chunk -- every matching stock-day as of ``at`` (``rvol_outcomes`` reads the same)."""
    at_m = minute_of(at, "at")
    if at_m <= rs.SESSION_START_M:
        raise ValueError("at must be after 04:00: nothing has traded by then")
    filters = check(filters, SCAN_FILTERS, kinds, splits, measure)
    groups, manifest = chunks(filters)
    sql = _scan_sql(at_m, filters, kinds, splits, measure, min_base_sessions)

    def tables():
        con = connect()
        try:
            for days in groups:
                prefix = _prefix(days, manifest)
                yield days, con.execute(sql, {"dfiles": posix(rs.days_path(d) for d in prefix + days),
                                              "mfiles": posix(rs.minutes_path(d) for d in prefix + days),
                                              "first": date.fromisoformat(days[0]),
                                              "last": date.fromisoformat(days[-1])}).to_arrow_table()
        finally:
            con.close()
    return filters, groups, tables


def scan(at: str, *, filters: dict[str, Any], measure: str = "cumulative", kinds=None, splits: str = "exclude_likely",
         min_base_sessions: int = rs.BASE_SESSIONS, sort: str | None = None, limit: int | None = None,
         to_file: Path | None = None) -> pd.DataFrame:
    """Every stock-day's three measures as of ``at`` (see the module docstring); ``attrs`` holds ``rows`` (all that
    matched), the rules and the units. Rows come sorted by ``sort`` (default the chosen measure, largest first); at
    most ``limit`` (default ``INLINE`` unless ``to_file``, which receives every row)."""
    if limit is not None and not 1 <= int(limit) <= LIMIT_MAX:
        raise ValueError(f"limit must be 1-{LIMIT_MAX:,}")
    filters, groups, tables = scan_tables(at, filters, measure, kinds, splits, min_base_sessions)
    sort_column = sort or MEASURES[measure]
    keep = int(limit) if limit else (None if to_file else INLINE)
    rows, parts = 0, []
    with slots.heavy(f"rvol scan {at}"):
        for part in write_parts((t for _days, t in tables()), to_file):
            rows += len(part)
            if keep and len(part) > keep:
                part = part.sort_values(sort_column, ascending=False, na_position="last").head(keep)
            parts.append(part)
    frame = _shape(_finish(parts, sort_column, False, keep))
    frame.attrs.update(rows=rows, at=at, measure=measure, filters=filters, kinds=list(kinds or DEFAULT_KINDS),
                       splits=splits, min_base_sessions=min_base_sessions, sorted_by=sort_column, units=UNITS,
                       rules={**rs.RULES, "at": f"bars starting before {at}; price is the last one's close "
                                                 "(price_et its start)",
                              "five_minute": "bars starting in the five minutes before at"},
                       sessions=sum(len(g) for g in groups))
    return frame


def _trigger_sql(rvol_min: float, measure: str, w0: int, w1: int, filters: dict[str, Any], kinds, splits: str,
                 min_sessions: int) -> str:
    cond = {"cumulative": f"x.base > 0 AND x.cum >= {rvol_min!r} * x.base",
            "five_minute": f"x.base5 > 0 AND x.vol5 >= {rvol_min!r} * x.base5",
            "daily_rate": f"d.day_avg_volume > 0 AND x.cum >= {rvol_min!r} * d.day_avg_volume"}[measure]
    hit = [cond, f"x.m >= {w0}"]
    if filters.get("volume_min") is not None:
        hit.append(f"x.cum >= {float(filters['volume_min'])!r}")
    if filters.get("change_min") is not None:
        hit.append(f"x.close >= d.prev_close * (1 + {float(filters['change_min']) / 100.0!r})")
    if filters.get("change_max") is not None:
        hit.append(f"x.close <= d.prev_close * (1 + {float(filters['change_max']) / 100.0!r})")
    universe = universe_sql(filters, kinds, splits, sessions_column(measure), min_sessions)
    return f"""
WITH d AS (SELECT date, symbol, kind, prev_close, split, base_sessions, day_avg_volume, day_avg_sessions, epoch, basis
           FROM read_parquet($dfiles) WHERE {universe}),
h AS (SELECT x.date, x.symbol,
             arg_min({{'m': x.m, 'close': x.close, 'cum': x.cum, 'base': x.base, 'vol5': x.vol5, 'base5': x.base5}},
                     x.m) FILTER (WHERE {' AND '.join(hit)}) AS t,
             bool_or({cond}) FILTER (WHERE x.m < {w0}) AS above_before
      FROM read_parquet($mfiles) x JOIN d ON x.date = d.date AND x.symbol = d.symbol
      WHERE x.m < {w1} GROUP BY x.date, x.symbol)
SELECT d.date, d.symbol, d.kind, d.prev_close, h.t.m AS trigger_m, h.t.m + 1 AS entry_m, h.t.close AS price,
       (h.t.close / nullif(d.prev_close, 0) - 1) * 100 AS change_pct, h.t.cum AS volume, h.t.base AS base_volume,
       h.t.cum / nullif(h.t.base, 0) AS rvol, h.t.vol5 AS volume_5m, h.t.base5 AS base_5m,
       h.t.vol5 / nullif(h.t.base5, 0) AS rvol_5m, d.day_avg_volume, h.t.cum / nullif(d.day_avg_volume, 0) AS rvol_daily,
       coalesce(h.above_before, false) AS above_before, d.base_sessions, d.day_avg_sessions, d.split, d.epoch, d.basis
FROM h JOIN d ON h.date = d.date AND h.symbol = d.symbol WHERE h.t IS NOT NULL OR coalesce(h.above_before, false)"""


def trigger_frames(rvol_min: float, measure: str, window: tuple[str, str], filters: dict[str, Any], kinds,
                   splits: str, min_base_sessions: int):
    """``(groups, filters, sql)``: the year chunks, the checked filters and the trigger query for them
    (``rvol_outcomes`` reads all three). Every row says ``above_before``; a stock-day over the line before the
    window with no hit inside it comes back too (``trigger_m`` null: the control's "already crossed"), so callers
    keep ``trigger_m`` rows as triggers, and apply ``fresh``."""
    w0, w1 = minute_of(window[0], "window_from"), minute_of(window[1], "window_to")
    if w1 <= w0:
        raise ValueError(f"window_to {window[1]} is not after window_from {window[0]}")
    if float(rvol_min) <= 0:
        raise ValueError("rvol_min is a ratio above 0 (5 = five times the baseline)")
    filters = check(filters, TRIGGER_FILTERS, kinds, splits, measure)
    groups, _manifest = chunks(filters)
    return groups, filters, _trigger_sql(float(rvol_min), measure, w0, w1, filters, kinds, splits,
                                         min_base_sessions)


def run_chunks(groups: list[list[str]], sql: str):
    """Each chunk's ``(days, rows of sql)`` (``$dfiles`` / ``$mfiles`` of the chunk's days) as an arrow table."""
    con = connect()
    try:
        for days in groups:
            yield days, con.execute(sql, {"dfiles": posix(rs.days_path(d) for d in days),
                                          "mfiles": posix(rs.minutes_path(d) for d in days)}).to_arrow_table()
    finally:
        con.close()


def triggers(rvol_min: float, *, measure: str = "cumulative", window_from: str = "04:00", window_to: str = "16:00",
             filters: dict[str, Any], kinds=None, splits: str = "exclude_likely",
             min_base_sessions: int = rs.BASE_SESSIONS, fresh: bool = False, limit: int | None = None,
             to_file: Path | None = None) -> pd.DataFrame:
    """The first bar each stock-day is at or above ``rvol_min`` on ``measure`` inside the window (every filter
    holding at that bar), oldest day first; ``attrs['rows']`` counts them all. ``above_before`` says the measure was
    already over the line before the window opened (so the window's first bar triggers); ``fresh`` leaves those
    stock-days out."""
    if limit is not None and not 1 <= int(limit) <= LIMIT_MAX:
        raise ValueError(f"limit must be 1-{LIMIT_MAX:,}")
    groups, filters, sql = trigger_frames(rvol_min, measure, (window_from, window_to), filters, kinds, splits,
                                          min_base_sessions)
    keep = int(limit) if limit else (None if to_file else INLINE)
    rows, parts, held = 0, [], 0
    with slots.heavy(f"rvol triggers {rvol_min}"):
        def hits(t):                    # triggers only (rows over the line before the window with no hit drop)
            keep = pc.is_valid(t.column("trigger_m"))
            return t.filter(pc.and_(keep, pc.invert(t.column("above_before"))) if fresh else keep)
        tables = (hits(t) for _days, t in run_chunks(groups, sql))
        for part in write_parts(tables, to_file):
            rows += len(part)
            if keep is None or held < keep:
                part = part.sort_values(["date", "symbol"], kind="stable")
                parts.append(part if keep is None else part.head(keep - held))
                held += len(parts[-1])
    frame = _shape(_finish(parts, None, True, keep))
    frame.attrs.update(rows=rows, rvol_min=rvol_min, fresh=bool(fresh),
                       measure=measure, window=f"{window_from}-{window_to}", filters=filters,
                       kinds=list(kinds or DEFAULT_KINDS), splits=splits, min_base_sessions=min_base_sessions,
                       units=UNITS, rules={**rs.RULES, "trigger": "the first bar starting in the window where the "
                                           "measure (at the end of that bar) is at least rvol_min and every filter "
                                           "holds; entry_et is its end, the first moment it is known",
                                           "above_before": "the measure was over the line on a bar before the "
                                           "window opened, so the window's first bar triggers (fresh=true leaves "
                                           "these out)"})
    return frame


def _env_threads() -> int:
    try:
        return max(1, int(os.environ.get("NOVA_RVOL_THREADS") or DUCKDB_THREADS))
    except ValueError:
        return DUCKDB_THREADS
