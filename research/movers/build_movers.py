"""Build the day movers index (ADR 050) from the Massive day and minute bars.

One row per stock per session that moved, written whole per session through ``backend/day_movers/store.py``
into ``<NOVA_MARKET_DATA_DIR>/movers/day_movers.sqlite3``. Every definition is in research/movers/README.md and
AGENTS.md section 3 ("Agents find stock-days and show them in the Sim").

Usage (from the repo root):
    py -3 research/movers/build_movers.py                       # every session not built yet, newest first
    py -3 research/movers/build_movers.py --date 2026-09-25     # one session, built again
    py -3 research/movers/build_movers.py --start 2026-09-01 --end 2026-09-30 --rebuild
    py -3 research/movers/build_movers.py --avoid-session       # stop before 03:45 ET on a weekday
    py -3 research/movers/build_movers.py --status

Idempotent and resumable: a session is replaced whole in one transaction, and a session already built by this
builder (with its minute bars, when the minute file is on disk) is skipped unless ``--rebuild``.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "research" / "leaderboard"))
sys.path.insert(0, str(REPO / "backend"))

import pandas as pd  # noqa: E402
from lb_config import (  # noqa: E402
    AVOID_FROM_MIN_ET,
    AVOID_UNTIL_MIN_ET,
    CSV_COLUMNS,
    DATA_ROOT,
    DAY_SUBDIR,
    MINUTE_SUBDIR,
    REFERENCE_SUBDIR,
    RESEARCH_DB,
)
from lb_io import (  # noqa: E402
    Split,
    et_ts,
    files_by_date,
    load_reference,
    load_splits,
    open_research_db,
    split_factor,
    splits_by_ticker,
)

from constants_day_movers import (  # noqa: E402
    DAY_MOVERS_BUILDER_VERSION,
    DAY_MOVERS_DB_FILENAME,
    DAY_MOVERS_DOWN_MARKS,
    DAY_MOVERS_KEEP_CLOSE_ABS,
    DAY_MOVERS_KEEP_GAP_ABS,
    DAY_MOVERS_KEEP_HIGH_PCT,
    DAY_MOVERS_KEEP_LOW_PCT,
    DAY_MOVERS_KEEP_NO_PRIOR_RANGE,
    DAY_MOVERS_REGULAR_CLOSE_MIN_ET,
    DAY_MOVERS_REGULAR_OPEN_MIN_ET,
    DAY_MOVERS_SESSION_END_MIN_ET,
    DAY_MOVERS_SESSION_START_MIN_ET,
    DAY_MOVERS_SPLIT_SUSPECT_DOWN,
    DAY_MOVERS_SPLIT_SUSPECT_UP,
    DAY_MOVERS_SUBDIR,
    DAY_MOVERS_UP_MARKS,
)
from day_movers import store  # noqa: E402

ET = ZoneInfo("America/New_York")
DEFAULT_DB = DATA_ROOT / DAY_MOVERS_SUBDIR / DAY_MOVERS_DB_FILENAME
DUCKDB_THREADS_DEFAULT = 4
DUCKDB_MEMORY_LIMIT = "3GB"
_BELOW_NORMAL_PRIORITY_CLASS = 0x00004000


# ── Reads ───────────────────────────────────────────────────────────────────

def work_db(threads: int):
    import duckdb

    con = duckdb.connect()
    con.execute(f"SET threads TO {int(threads)}")
    con.execute(f"SET memory_limit = '{DUCKDB_MEMORY_LIMIT}'")
    return con


def day_bars(con, path: Path | None) -> dict[str, tuple[float, float, float, float, float]]:
    """``ticker -> (open, high, low, close, volume)`` from one day-bar file (regular hours, official close)."""
    if path is None or not Path(path).is_file():
        return {}
    rows = con.execute(
        "SELECT ticker, open, high, low, close, volume"
        f" FROM read_csv('{Path(path).as_posix()}', header = true, columns = {CSV_COLUMNS})"
    ).fetchall()
    return {str(t): (float(o), float(h), float(lo), float(c), float(v)) for t, o, h, lo, c, v in rows if t}


def _mark_sql(marks: dict[str, float], column: str, op: str) -> str:
    return ", ".join(
        f"min(m.ts) FILTER (WHERE p.pc > 0 AND m.{column} {op} p.pc * {mult!r}) AS {name}"
        for name, mult in marks.items()
    )


def minute_aggregates(con, path: Path, session: date, prev_close: dict[str, float]) -> dict[str, dict[str, Any]]:
    """Per ticker, from one minute-bar file: the premarket / after-hours / whole-day highs and lows with the first
    minute that printed them, volume by part of the day, dollar volume and the first minute each mark was reached."""
    t0400 = et_ts(session, DAY_MOVERS_SESSION_START_MIN_ET)
    t0930 = et_ts(session, DAY_MOVERS_REGULAR_OPEN_MIN_ET)
    t1600 = et_ts(session, DAY_MOVERS_REGULAR_CLOSE_MIN_ET)
    t2000 = et_ts(session, DAY_MOVERS_SESSION_END_MIN_ET)
    con.register("pc_df", pd.DataFrame({
        "ticker": pd.Series(list(prev_close), dtype="object"),
        "pc": pd.Series(list(prev_close.values()), dtype="float64"),
    }))
    con.execute(
        "CREATE OR REPLACE TEMP TABLE m AS"
        " SELECT ticker, window_start // 1000000000 AS ts, high, low, close, volume"
        f" FROM read_csv('{Path(path).as_posix()}', header = true, columns = {CSV_COLUMNS})"
        f" WHERE window_start // 1000000000 >= {t0400} AND window_start // 1000000000 < {t2000}"
    )
    rows = con.execute(
        "WITH agg AS ("
        " SELECT m.ticker, min(m.ts) AS first_ts, max(m.ts) AS last_ts,"
        f" max(m.high) FILTER (WHERE m.ts < {t0930}) AS pm_high,"
        f" min(m.low) FILTER (WHERE m.ts < {t0930}) AS pm_low,"
        f" sum(m.volume) FILTER (WHERE m.ts < {t0930}) AS pm_volume,"
        f" max(m.high) FILTER (WHERE m.ts >= {t1600}) AS ah_high,"
        f" min(m.low) FILTER (WHERE m.ts >= {t1600}) AS ah_low,"
        f" sum(m.volume) FILTER (WHERE m.ts >= {t1600}) AS ah_volume,"
        " max(m.high) AS mhigh, min(m.low) AS mlow, sum(m.close * m.volume) AS dollar_volume,"
        f" {_mark_sql(DAY_MOVERS_UP_MARKS, 'high', '>=')}, {_mark_sql(DAY_MOVERS_DOWN_MARKS, 'low', '<=')}"
        " FROM m LEFT JOIN pc_df p ON p.ticker = m.ticker GROUP BY m.ticker"
        "), times AS ("
        " SELECT m.ticker, min(m.ts) FILTER (WHERE m.high = a.mhigh) AS mhigh_ts,"
        " min(m.ts) FILTER (WHERE m.low = a.mlow) AS mlow_ts"
        " FROM m JOIN agg a ON a.ticker = m.ticker GROUP BY m.ticker"
        ") SELECT agg.*, times.mhigh_ts, times.mlow_ts FROM agg JOIN times ON times.ticker = agg.ticker"
    )
    names = [d[0] for d in rows.description]
    out = {str(r[0]): dict(zip(names, r, strict=True)) for r in rows.fetchall()}
    con.execute("DROP TABLE m")
    con.unregister("pc_df")
    return out


# ── One session ─────────────────────────────────────────────────────────────

def _pct(value: float | None, base: float | None) -> float | None:
    if value is None or base is None or base <= 0 or value <= 0:
        return None
    return value / base - 1.0


def _int(value: Any) -> int | None:
    return None if value is None else int(value)


def mover_row(
    session: date, ticker: str, bar: tuple[float, float, float, float, float], *, kind: str | None,
    prev_date: date | None, prior: tuple[float, float] | None, splits: list[Split], mins: dict[str, Any] | None,
) -> dict[str, Any]:
    """One stock's session, every figure on the session's own share basis."""
    o, h, lo, c, v = bar
    factor = split_factor(splits, prev_date, session, prices=True) if prev_date else 1.0
    pc = prior[0] * factor if prior and prior[0] > 0 else None
    pv = prior[1] / factor if prior and factor else None
    listed = factor != 1.0
    ratio = (o / pc) if pc and o > 0 else None
    suspect = bool(not listed and ratio is not None
                   and (ratio >= DAY_MOVERS_SPLIT_SUSPECT_UP or ratio <= DAY_MOVERS_SPLIT_SUSPECT_DOWN))
    row: dict[str, Any] = {
        "session_date": session.isoformat(), "symbol": ticker, "kind": kind,
        "prev_date": prev_date.isoformat() if prev_date and prior else None,
        "prev_close": pc, "prev_volume": pv, "split_factor": factor, "split_listed": int(listed),
        "split_suspect": int(suspect), "open": o, "high": h, "low": lo, "close": c, "volume": v,
    }
    day_high, day_low = h, lo
    high_ts = low_ts = None
    for key in ("pm_high", "pm_low", "pm_volume", "ah_high", "ah_low", "ah_volume", "dollar_volume", "first_ts",
                "last_ts", *DAY_MOVERS_UP_MARKS, *DAY_MOVERS_DOWN_MARKS):
        row[key] = None
    if mins:
        for key in ("pm_high", "pm_low", "pm_volume", "ah_high", "ah_low", "ah_volume", "dollar_volume"):
            row[key] = None if mins.get(key) is None else float(mins[key])
        for key in (*DAY_MOVERS_UP_MARKS, *DAY_MOVERS_DOWN_MARKS):
            row[key] = _int(mins.get(key))
        row["first_ts"], row["last_ts"] = _int(mins.get("first_ts")), _int(mins.get("last_ts"))
        mhigh, mlow = mins.get("mhigh"), mins.get("mlow")
        if mhigh is not None:
            day_high = max(day_high, float(mhigh))
            high_ts = _int(mins.get("mhigh_ts")) if float(mhigh) >= day_high else None
        if mlow is not None:
            day_low = min(day_low, float(mlow)) if day_low > 0 else float(mlow)
            low_ts = _int(mins.get("mlow_ts")) if float(mlow) <= day_low else None
    row.update({
        "day_high": day_high, "day_high_ts": high_ts, "day_low": day_low, "day_low_ts": low_ts,
        "high_pct": _pct(day_high, pc), "low_pct": _pct(day_low, pc),
        "close_pct": _pct(c, pc), "gap_pct": _pct(o, pc),
    })
    return row


def keep(row: dict[str, Any]) -> bool:
    """A stock that moved (AGENTS.md section 3): the rest of the market is counted, not stored."""
    if row["prev_close"] is None:
        low, high = row["day_low"], row["day_high"]
        return bool(low and low > 0 and high / low - 1.0 >= DAY_MOVERS_KEEP_NO_PRIOR_RANGE)
    hp, lp, cp, gp = row["high_pct"], row["low_pct"], row["close_pct"], row["gap_pct"]
    return bool(
        row["split_suspect"]
        or (hp is not None and hp >= DAY_MOVERS_KEEP_HIGH_PCT)
        or (lp is not None and lp <= DAY_MOVERS_KEEP_LOW_PCT)
        or (cp is not None and abs(cp) >= DAY_MOVERS_KEEP_CLOSE_ABS)
        or (gp is not None and abs(gp) >= DAY_MOVERS_KEEP_GAP_ABS)
    )


def build_session(
    con, session: date, *, prev_date: date | None, day_file: Path, prev_file: Path | None, minute_file: Path | None,
    types: dict[str, str | None], by_ticker: dict[str, list[Split]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    today = day_bars(con, day_file)
    before = {t: (b[3], b[4]) for t, b in day_bars(con, prev_file).items()}
    prev_close = {}
    for t in today:
        prior = before.get(t)
        if prior and prior[0] > 0 and prev_date:
            prev_close[t] = prior[0] * split_factor(by_ticker.get(t, []), prev_date, session, prices=True)
    minutes = minute_aggregates(con, minute_file, session, prev_close) if minute_file else {}
    rows = []
    for t, bar in today.items():
        row = mover_row(session, t, bar, kind=types.get(t), prev_date=prev_date, prior=before.get(t),
                        splits=by_ticker.get(t, []), mins=minutes.get(t))
        if keep(row):
            rows.append(row)
    meta = {
        "session_date": session.isoformat(), "prev_date": prev_date.isoformat() if prev_date else None,
        "tickers": len(today), "rows": len(rows), "minute_bars": int(minute_file is not None),
        "builder": DAY_MOVERS_BUILDER_VERSION, "built_ts": time.time(),
        "note": None if minute_file else "no minute file: premarket and after hours unknown",
    }
    return meta, rows


# ── The run ─────────────────────────────────────────────────────────────────

def in_desk_session(now: datetime | None = None) -> bool:
    """03:45-20:05 ET on a weekday: leave the machine and the Massive drive to the desk."""
    at = (now or datetime.now(ET)).astimezone(ET)
    minutes = at.hour * 60 + at.minute
    return at.weekday() < 5 and AVOID_FROM_MIN_ET <= minutes < AVOID_UNTIL_MIN_ET


def _below_normal() -> None:
    if sys.platform == "win32":
        import ctypes

        kernel = ctypes.windll.kernel32
        kernel.SetPriorityClass(kernel.GetCurrentProcess(), _BELOW_NORMAL_PRIORITY_CLASS)


def reference_db():
    """The research store for the reference, unless its JSON dump is newer (a recent split must be known)."""
    ref_dir = DATA_ROOT / REFERENCE_SUBDIR
    dumps = [ref_dir / name for name in ("tickers.json", "splits.json") if (ref_dir / name).is_file()]
    if dumps and RESEARCH_DB.is_file() and min(p.stat().st_mtime for p in dumps) > RESEARCH_DB.stat().st_mtime:
        return None, f"reference from {ref_dir} (newer than {RESEARCH_DB.name})"
    return open_research_db(RESEARCH_DB)


def built(db) -> dict[str, dict[str, Any]]:
    return {row["session_date"]: row for row in store.sessions(db)}


def write_session(db, meta: dict[str, Any], rows: list[dict[str, Any]], attempts: int = 5) -> int:
    """``store.replace_session``, waiting out another writer (``export_sec_shares.py``) that holds the store."""
    for attempt in range(attempts):
        try:
            return store.replace_session(db, meta, rows)
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc) or attempt == attempts - 1:
                raise
            print(f"{meta['session_date']}  the store is busy; trying again", flush=True)
            time.sleep(10)
    return 0


def wanted(dates: list[date], done: dict[str, dict[str, Any]], minute: dict[date, Path], rebuild: bool) -> list[date]:
    """Sessions not built by this builder, or built before their minute file was on disk."""
    if rebuild:
        return dates
    out = []
    for d in dates:
        row = done.get(d.isoformat())
        if row is None or row["builder"] != DAY_MOVERS_BUILDER_VERSION or (not row["minute_bars"] and d in minute):
            out.append(d)
    return out


def status(db_path: Path, daily: dict[date, Path]) -> int:
    with store.connect(db_path) as db:
        done = built(db)
        rows = db.execute("SELECT count(*) FROM movers").fetchone()[0]
    have = sorted(done)
    print(f"store {db_path}")
    print(f"sessions built {len(done)} of {len(daily)} day files; rows {rows:,}")
    if have:
        print(f"first {have[0]}  last {have[-1]}")
    missing = [d for d in daily if d.isoformat() not in done]
    print(f"not built {len(missing)}" + (f" (newest {max(missing)})" if missing else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", type=date.fromisoformat)
    ap.add_argument("--start", type=date.fromisoformat)
    ap.add_argument("--end", type=date.fromisoformat)
    ap.add_argument("--oldest-first", action="store_true", help="build the oldest sessions first")
    ap.add_argument("--rebuild", action="store_true", help="build sessions already built")
    ap.add_argument("--avoid-session", action="store_true", help="stop before 03:45 ET on a weekday")
    ap.add_argument("--limit", type=int, default=0, help="build at most this many sessions")
    ap.add_argument("--threads", type=int, default=DUCKDB_THREADS_DEFAULT)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args(argv)

    daily = files_by_date(DATA_ROOT / DAY_SUBDIR)
    minute = files_by_date(DATA_ROOT / MINUTE_SUBDIR)
    if args.status:
        return status(args.db, daily)
    _below_normal()
    calendar = list(daily)
    dates = calendar
    if args.date:
        dates, args.rebuild = [args.date], True
    elif args.start or args.end:
        dates = [d for d in calendar if (not args.start or d >= args.start) and (not args.end or d <= args.end)]
    dates = sorted(dates, reverse=not args.oldest_first)

    research, note = reference_db()
    try:
        reference = load_reference(research, DATA_ROOT / REFERENCE_SUBDIR)
        splits = load_splits(research, DATA_ROOT / REFERENCE_SUBDIR)
    finally:
        if research is not None:
            research.close()
    by_ticker = splits_by_ticker(splits)
    print(f"{note}; reference {len(reference.types):,} tickers ({reference.source}); splits {len(splits):,}", flush=True)

    con = work_db(args.threads)
    built_count = 0
    with store.connect(args.db) as db:
        store.replace_splits(db, [
            {"symbol": s.ticker, "execution_date": s.execution_date.isoformat(), "split_from": s.split_from,
             "split_to": s.split_to} for s in {(s.ticker, s.execution_date): s for s in splits}.values()
        ])
        todo = wanted(dates, built(db), minute, args.rebuild)
        print(f"store {args.db}; {len(todo)} sessions to build", flush=True)
        for d in todo:
            if args.avoid_session and in_desk_session():
                print("stopped: the desk's session is near -- run again after 20:05 ET", flush=True)
                break
            if d not in daily:
                print(f"{d}  no day file", flush=True)
                continue
            i = calendar.index(d)
            prev = calendar[i - 1] if i else None
            started = time.time()
            meta, rows = build_session(
                con, d, prev_date=prev, day_file=daily[d], prev_file=daily.get(prev) if prev else None,
                minute_file=minute.get(d), types=reference.types, by_ticker=by_ticker,
            )
            write_session(db, meta, rows)
            built_count += 1
            print(f"{d}  tickers {meta['tickers']:>6}  kept {meta['rows']:>5}  "
                  f"minutes {'yes' if meta['minute_bars'] else 'no '}  {time.time() - started:5.1f} s", flush=True)
            if args.limit and built_count >= args.limit:
                break
    print(f"done: {built_count} sessions built", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
