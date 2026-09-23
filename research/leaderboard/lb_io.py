"""Reads for the leaderboard rebuild: flat files, reference, splits, news, float.

Heavy lifting (one minute file for the day, twenty for the RVOL profile) runs in an
in-memory DuckDB; results come back as numpy arrays keyed by an integer symbol id.
The research store ``orb.duckdb`` is opened read-only and only for reference data;
when a writer holds it the JSON reference dump is read instead.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import pandas as pd

from lb_config import (
    CSV_COLUMNS,
    DUCKDB_MEMORY_LIMIT,
    DUCKDB_THREADS,
    MIC_TO_EXCHANGE,
    PRIOR_CLOSE_HOUR_ET,
    SESSION_MINUTES,
    SESSION_START_MIN_ET,
    TZ_NAME,
    UNIVERSE_TYPES,
)

ET = ZoneInfo(TZ_NAME)
_DAY_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\.csv\.gz$")


@dataclass
class Reference:
    types: dict[str, str | None]
    mic: dict[str, str | None]
    source: str

    def universe(self) -> list[str]:
        return sorted(t for t, kind in self.types.items() if kind in UNIVERSE_TYPES)

    def exchange(self, ticker: str) -> str | None:
        return MIC_TO_EXCHANGE.get(self.mic.get(ticker) or "")


@dataclass
class Split:
    ticker: str
    execution_date: date
    split_from: float
    split_to: float


@dataclass
class News:
    known: bool
    articles: list[tuple[str, float]] = field(default_factory=list)   # (ticker, published epoch)
    note: str = ""


# ── Calendar ────────────────────────────────────────────────────────────────

def files_by_date(folder: Path) -> dict[date, Path]:
    """Every ``YYYY-MM-DD.csv.gz`` under ``folder/YYYY/MM`` keyed by date."""
    out: dict[date, Path] = {}
    for p in Path(folder).glob("*/*/*.csv.gz"):
        m = _DAY_RE.search(p.name)
        if m:
            out[date.fromisoformat(m.group(1))] = p
    return dict(sorted(out.items()))


def et_ts(d: date, minutes_after_midnight: int) -> int:
    base = datetime.combine(d, time(0, 0), tzinfo=ET)
    local = base.replace(hour=minutes_after_midnight // 60, minute=minutes_after_midnight % 60)
    return int(local.timestamp())


def open_ts(d: date) -> int:
    """Epoch second of 04:00 ET on ``d`` (DST-aware)."""
    return et_ts(d, SESSION_START_MIN_ET)


def news_window(prev: date | None, d: date) -> tuple[float, float] | None:
    """(prior session's 16:00 ET, this session's 20:00 ET) as epoch seconds."""
    if prev is None:
        return None
    return float(et_ts(prev, PRIOR_CLOSE_HOUR_ET * 60)), float(et_ts(d, SESSION_START_MIN_ET + SESSION_MINUTES))


# ── Reference, splits, news, float ──────────────────────────────────────────

def open_research_db(path: Path) -> tuple[duckdb.DuckDBPyConnection | None, str]:
    try:
        return duckdb.connect(str(path), read_only=True), f"reference from {path} (read-only)"
    except duckdb.Error as exc:   # a writer holds the file lock
        return None, f"{path} unavailable ({type(exc).__name__}: {exc}); reading the JSON reference dump"


def load_reference(research: duckdb.DuckDBPyConnection | None, ref_dir: Path) -> Reference:
    if research is not None:
        rows = research.execute("SELECT ticker, type, primary_exchange FROM tickers").fetchall()
        return Reference({t: k for t, k, _ in rows}, {t: m for t, _, m in rows}, "orb.duckdb:tickers")
    rows = json.loads((ref_dir / "tickers.json").read_text(encoding="utf-8"))
    return Reference(
        {r["ticker"]: r.get("type") for r in rows if r.get("ticker")},
        {r["ticker"]: r.get("primary_exchange") for r in rows if r.get("ticker")},
        "reference/tickers.json",
    )


def load_splits(research: duckdb.DuckDBPyConnection | None, ref_dir: Path) -> list[Split]:
    if research is not None:
        rows = research.execute("SELECT ticker, execution_date, split_from, split_to FROM splits").fetchall()
    else:
        raw = json.loads((ref_dir / "splits.json").read_text(encoding="utf-8"))
        rows = [(r.get("ticker"), date.fromisoformat(r["execution_date"]), r.get("split_from"), r.get("split_to"))
                for r in raw if r.get("execution_date")]
    return [Split(t, d, float(f), float(to)) for t, d, f, to in rows if t and d and f and to]


def splits_by_ticker(splits: list[Split]) -> dict[str, list[Split]]:
    out: dict[str, list[Split]] = {}
    for s in splits:
        out.setdefault(s.ticker, []).append(s)
    return out


def split_factor(splits: list[Split], after: date, through: date, *, prices: bool) -> float:
    """Unadjusted -> as of ``through``, for one ticker's splits executing in (after, through].

    A 1-for-23 reverse split (split_from 23, split_to 1) multiplies a price from
    before it by 23 and divides a share volume by 23.
    """
    factor = 1.0
    for s in splits:
        if after < s.execution_date <= through:
            factor *= (s.split_from / s.split_to) if prices else (s.split_to / s.split_from)
    return factor


def _utc_naive(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None)


def _months(start: datetime, end: datetime) -> list[str]:
    out, cur = [], date(start.year, start.month, 1)
    while cur <= end.date():
        out.append(f"{cur:%Y-%m}")
        cur = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
    return out


@dataclass
class NewsArchive:
    """Articles loaded once for a whole build range, so the research store is not held open."""

    months: set[str]
    reach: datetime | None                   # newest published_utc in the archive (naive UTC)
    articles: list[tuple[str, float]]        # (ticker, published epoch), one per (article, ticker)
    loaded: tuple[float, float]              # the (start, end] the articles were loaded for

    def for_window(self, window: tuple[float, float] | None) -> News:
        """Known only when the archive holds every month the window spans and reaches past its end."""
        if window is None:
            return News(False, note="no prior session: news window undefined")
        start, end = _utc_naive(window[0]), _utc_naive(window[1])
        missing = [m for m in _months(start, end) if m not in self.months]
        if window[0] < self.loaded[0] or window[1] > self.loaded[1]:
            raise ValueError(f"news window {window} outside the loaded range {self.loaded}")
        if missing or self.reach is None or self.reach < end:
            return News(False, note=f"news archive does not cover the window (missing {missing}, reach {self.reach})")
        inside = [(t, ts) for t, ts in self.articles if window[0] < ts <= window[1]]
        return News(True, inside, note=f"{len(inside)} ticker-articles in window")


def load_news_archive(
    research: duckdb.DuckDBPyConnection | None, ref_dir: Path, start_ts: float, end_ts: float,
) -> NewsArchive:
    """``news_tickers`` (deduplicated per article and ticker) published in (start_ts, end_ts]."""
    start, end = _utc_naive(start_ts), _utc_naive(end_ts)
    if research is not None:
        months = {r[0] for r in research.execute("SELECT month FROM news_months").fetchall()}
        reach = research.execute("SELECT max(published_utc) FROM news_tickers").fetchone()[0]
        rows = research.execute(
            "SELECT DISTINCT ticker, article_id, published_utc FROM news_tickers"
            " WHERE published_utc > ? AND published_utc <= ?", [start, end],
        ).fetchall()
        articles = [(t, p.replace(tzinfo=timezone.utc).timestamp()) for t, _, p in rows if t and p]
        return NewsArchive(months, reach, articles, (start_ts, end_ts))
    files = sorted((ref_dir / "news").glob("*.jsonl"))
    months, reach, seen, articles = {f.stem for f in files}, None, set(), []
    wanted = set(_months(start, end))
    for path in [f for f in files if f.stem in wanted or f == files[-1]]:   # the window, and the newest for reach
        for line in path.read_text(encoding="utf-8").splitlines():
            art = json.loads(line) if line.strip() else {}
            if not art.get("published_utc"):
                continue
            pub = datetime.fromisoformat(str(art["published_utc"]).replace("Z", "+00:00")).astimezone(timezone.utc)
            pub_n = pub.replace(tzinfo=None)
            reach = pub_n if reach is None or pub_n > reach else reach
            if not start < pub_n <= end:
                continue
            for ticker in set(art.get("tickers") or ()):
                if (ticker, art.get("id")) not in seen:
                    seen.add((ticker, art.get("id")))
                    articles.append((ticker, pub.timestamp()))
    return NewsArchive(months, reach, articles, (start_ts, end_ts))


def load_floats(archive_db: Path, session_date: date) -> tuple[dict[str, float], str]:
    """Float as Nova's enrichment snapshot knew it that session (2026-07-28 on); read-only."""
    if not Path(archive_db).exists():
        return {}, f"{archive_db} missing: float unknown"
    uri = f"file:{Path(archive_db).as_posix()}?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    try:
        rows = db.execute(
            "SELECT symbol, float_shares FROM enrichment_snapshots"
            " WHERE session_date = ? AND float_shares IS NOT NULL AND float_shares > 0",
            (session_date.isoformat(),),
        ).fetchall()
    finally:
        db.close()
    return {str(s).upper(): float(f) for s, f in rows}, f"{len(rows)} float snapshots"


# ── Flat files (in-memory DuckDB) ───────────────────────────────────────────

def work_db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"SET threads TO {DUCKDB_THREADS}")
    con.execute(f"SET memory_limit = '{DUCKDB_MEMORY_LIMIT}'")
    return con


def _minute_sql(path: Path, day_open: int, extra: str = "") -> str:
    j = f"(window_start // 1000000000 - {int(day_open)}) // 60"
    return (
        f"SELECT ticker, {j} AS j, open, close, volume{extra}"
        f" FROM read_csv('{Path(path).as_posix()}', header = true, columns = {CSV_COLUMNS})"
        f" WHERE {j} BETWEEN 0 AND {SESSION_MINUTES - 1}"
    )


def read_day_bars(con: duckdb.DuckDBPyConnection, path: Path, day_open: int, universe: list[str]) -> dict:
    """The session's universe bars sorted by (symbol, j), plus what was left out."""
    con.register("universe_df", pd.DataFrame({"ticker": universe}))
    con.execute(f"CREATE OR REPLACE TEMP TABLE day_bars AS {_minute_sql(path, day_open)}")
    left_out = con.execute(
        "SELECT count(DISTINCT ticker) FROM day_bars WHERE ticker NOT IN (SELECT ticker FROM universe_df)"
    ).fetchone()[0]
    data = con.execute(
        "SELECT dense_rank() OVER (ORDER BY b.ticker) - 1 AS sid, b.ticker, b.j, b.open, b.close, b.volume"
        " FROM day_bars b JOIN universe_df u ON u.ticker = b.ticker ORDER BY b.ticker, b.j"
    ).fetchnumpy()
    con.execute("DROP TABLE day_bars")
    con.unregister("universe_df")
    sid = np.asarray(data["sid"], dtype=np.int64)
    tickers = np.asarray(data["ticker"], dtype=object)
    symbols = [str(t) for t in tickers[np.unique(sid, return_index=True)[1]]] if len(sid) else []
    return {
        "symbols": symbols, "sid": sid, "j": np.asarray(data["j"], dtype=np.int64),
        "open": np.asarray(data["open"], dtype=np.float64), "close": np.asarray(data["close"], dtype=np.float64),
        "volume": np.asarray(data["volume"], dtype=np.float64), "left_out": int(left_out),
    }


def read_day_closes(con: duckdb.DuckDBPyConnection, path: Path | None) -> dict[str, float]:
    if path is None or not Path(path).exists():
        return {}
    rows = con.execute(
        f"SELECT ticker, close FROM read_csv('{Path(path).as_posix()}', header = true, columns = {CSV_COLUMNS})"
        " WHERE close > 0"
    ).fetchall()
    return {t: float(c) for t, c in rows}


def read_prior_profile(
    con: duckdb.DuckDBPyConnection,
    sessions: list[tuple[date, Path]],
    symbols: list[str],
    volume_factors: dict[tuple[str, date], float],
) -> tuple[np.ndarray, np.ndarray]:
    """(n_sym x SESSION_MINUTES split-adjusted volume summed over ``sessions``,
    per-symbol count of sessions in which it printed)."""
    n = len(symbols)
    matrix = np.zeros((n, SESSION_MINUTES), dtype=np.float64)
    counts = np.zeros(n, dtype=np.int64)
    if not sessions or not n:
        return matrix, counts
    con.register("syms_df", pd.DataFrame({"sid": np.arange(n, dtype=np.int64), "ticker": symbols}))
    factors = pd.DataFrame(
        {"ticker": [t for t, _ in volume_factors], "s": [s.isoformat() for _, s in volume_factors],
         "f": list(volume_factors.values())}
    ).astype({"ticker": str, "s": str, "f": float})
    con.register("factors_df", factors)
    union = " UNION ALL ".join(
        _minute_sql(p, open_ts(s), extra=f", '{s.isoformat()}' AS s") for s, p in sessions
    )
    df = con.execute(
        "SELECT sid, j, s, SUM(v) AS v FROM ("
        " SELECT y.sid, p.j, p.s, p.volume * COALESCE(f.f, 1.0) AS v"
        f" FROM ({union}) p JOIN syms_df y ON y.ticker = p.ticker"
        " LEFT JOIN factors_df f ON f.ticker = p.ticker AND f.s = p.s"
        ") GROUP BY GROUPING SETS ((sid, j), (sid, s))"
    ).df()
    con.unregister("syms_df")
    con.unregister("factors_df")
    by_minute = df[df["s"].isna()]
    matrix[by_minute["sid"].to_numpy(np.int64), by_minute["j"].to_numpy(np.int64)] = by_minute["v"].to_numpy(np.float64)
    by_session = df[df["j"].isna()]
    np.add.at(counts, by_session["sid"].to_numpy(np.int64), 1)
    return matrix, counts
