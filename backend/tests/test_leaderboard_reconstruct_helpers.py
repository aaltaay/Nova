"""Helpers (no tests) for the leaderboard-rebuild tests (ADR 023): tiny synthetic
Massive flat files and a one-call rebuild into a tmp store.

Writes ``minute_aggs_v1`` / ``day_aggs_v1`` csv.gz files into a tmp dir in the
Massive layout; never touches F:. Consecutive June 2026 dates (one DST offset)
stand in for sessions -- the builder takes its calendar from the files.
"""
from __future__ import annotations

import gzip
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("duckdb")
pytest.importorskip("pandas")

RESEARCH = Path(__file__).resolve().parents[2] / "research" / "leaderboard"
if str(RESEARCH) not in sys.path:
    sys.path.insert(0, str(RESEARCH))

import build_leaderboard as bl  # noqa: E402
import lb_io  # noqa: E402

ET = ZoneInfo("America/New_York")
HEADER = "ticker,volume,open,close,high,low,window_start,transactions\n"
DAY0 = date(2026, 6, 1)


def session(i: int) -> date:
    return DAY0 + timedelta(days=i)


def ts(d: date, hh: int, mm: int) -> int:
    return int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET).timestamp())


def _path(root: Path, kind: str, d: date) -> Path:
    p = root / kind / f"{d:%Y}" / f"{d:%m}" / f"{d.isoformat()}.csv.gz"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def write_minutes(root: Path, d: date, bars: list[tuple]) -> None:
    """bars: (ticker, hh, mm, close, volume[, open])."""
    with gzip.open(_path(root, "minute_aggs_v1", d), "wt", encoding="utf-8") as fh:
        fh.write(HEADER)
        for bar in sorted(bars, key=lambda b: (b[0], b[1], b[2])):
            ticker, hh, mm, close, volume = bar[:5]
            open_ = bar[5] if len(bar) > 5 else close
            fh.write(f"{ticker},{volume},{open_},{close},{max(open_, close)},{min(open_, close)},"
                     f"{ts(d, hh, mm) * 1_000_000_000},1\n")


def write_closes(root: Path, d: date, closes: dict[str, float]) -> None:
    with gzip.open(_path(root, "day_aggs_v1", d), "wt", encoding="utf-8") as fh:
        fh.write(HEADER)
        for ticker, close in sorted(closes.items()):
            fh.write(f"{ticker},1000,{close},{close},{close},{close},{ts(d, 0, 0) * 1_000_000_000},1\n")


def reference(types: dict[str, str]) -> lb_io.Reference:
    return lb_io.Reference(dict(types), {t: "XNAS" for t in types}, "test")


def build(
    root: Path,
    d: date,
    types: dict[str, str],
    *,
    db: Path,
    splits: list[lb_io.Split] | None = None,
    articles: list[tuple[str, float]] | None = None,
    news_known: bool = True,
    floats: dict[str, float] | None = None,
    top_n: int = 100,
) -> dict:
    return bl.rebuild_day(
        d,
        top_n=top_n,
        database=db,
        data_root=root,
        reference=reference(types),
        splits=splits or [],
        news_for=lambda window: lb_io.News(news_known, list(articles or [])),
        floats_for=lambda _d: dict(floats or {}),
    )


def rows_at(db: Path, d: date, hh: int, mm: int) -> dict[str, dict]:
    from leaderboard import store

    with store.connect(db) as con:
        return {r["symbol"]: r for r in store.rows_at(con, d.isoformat(), "reconstructed", ts(d, hh, mm))}
