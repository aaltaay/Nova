"""Rebuild the whole-market per-minute leaderboard from the Massive minute flat files (ADR 022).

Writes ``source="reconstructed"``, ``board="market"`` rows into the leaderboard store
(``backend/leaderboard/store.py``; default F:\\Nova\\leaderboard\\leaderboard.sqlite3), one
board per minute 04:01-20:00 ET: the top ``--top`` rows by ``rank_rows(rows, BOARD_RULES)``
plus every row ``LEADERS_RULES`` or ``S5_RULES`` picks, so playback leaders and the S5
universe read back exactly. A row is the board as it stood at its minute: only bars
that closed by then. Idempotent: a day's (date, reconstructed) rows are replaced.
See research/leaderboard/README.md for every definition.

Usage (from the repo root):
    py -3 research/leaderboard/build_leaderboard.py --date 2026-09-21
    py -3 research/leaderboard/build_leaderboard.py --start 2026-09-08 --end 2026-09-21
    py -3 research/leaderboard/build_leaderboard.py --date 2026-09-21 --dry-run
"""
from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lb_config import (  # noqa: E402
    ARCHIVE_DB,
    DATA_ROOT,
    DAY_SUBDIR,
    MINUTE_SUBDIR,
    REFERENCE_SUBDIR,
    RESEARCH_DB,
    RVOL_LOOKBACK_SESSIONS,
    TOP_N_DEFAULT,
    WRITE_CHUNK_MINUTES,
)
from lb_core import DayInputs, coverage_row, day_boards, news_first_seen  # noqa: E402
from lb_io import (  # noqa: E402
    News,
    Reference,
    Split,
    files_by_date,
    load_floats,
    load_news_archive,
    load_reference,
    load_splits,
    news_window,
    open_research_db,
    open_ts,
    read_day_bars,
    read_day_closes,
    read_prior_profile,
    split_factor,
    splits_by_ticker,
    work_db,
)

from constants_leaderboard import LEADERBOARD_SOURCE_RECONSTRUCTED  # noqa: E402  (backend on sys.path via lb_core)
from leaderboard import store  # noqa: E402
from leaderboard.ranking import S5_RULES, leader_symbols  # noqa: E402


def assemble(
    session_date: date,
    *,
    data_root: Path,
    reference: Reference,
    splits: list[Split],
    news_for: Callable[[tuple[float, float] | None], News],
    floats_for: Callable[[date], dict[str, float]],
    con=None,
) -> tuple[DayInputs | None, dict]:
    """Everything one rebuilt session needs, read with no bar from after it."""
    minute = files_by_date(data_root / MINUTE_SUBDIR)
    daily = files_by_date(data_root / DAY_SUBDIR)
    if session_date not in minute:
        return None, {"skipped": "no minute file"}
    dates = list(minute)
    i = dates.index(session_date)
    prev = dates[i - 1] if i else None
    priors = dates[max(0, i - RVOL_LOOKBACK_SESSIONS):i]
    con = con or work_db()
    bars = read_day_bars(con, minute[session_date], open_ts(session_date), reference.universe())
    symbols = bars["symbols"]
    by_ticker = splits_by_ticker(splits)
    closes = read_day_closes(con, daily.get(prev)) if prev else {}
    prev_close = np.array([
        closes[s] * split_factor(by_ticker.get(s, []), prev, session_date, prices=True) if s in closes else np.nan
        for s in symbols
    ], dtype=np.float64)
    factors = {
        (s, p): f
        for s in symbols if s in by_ticker
        for p in priors
        if (f := split_factor(by_ticker[s], p, session_date, prices=False)) != 1.0
    }
    prior_volume, prior_sessions = read_prior_profile(con, [(p, minute[p]) for p in priors], symbols, factors)
    window = news_window(prev, session_date)
    news = news_for(window)
    first = news_first_seen(news.articles, *window) if news.known and window else {}
    floats = floats_for(session_date)
    inputs = DayInputs(
        session_date=session_date.isoformat(),
        open_ts=open_ts(session_date),
        symbols=symbols,
        sid=bars["sid"], j=bars["j"], open=bars["open"], close=bars["close"], volume=bars["volume"],
        prev_close=prev_close,
        prior_volume=prior_volume,
        prior_sessions=prior_sessions,
        float_shares=[floats.get(s) for s in symbols],
        exchange=[reference.exchange(s) for s in symbols],
        news_first_ts=np.array([first.get(s, np.nan) for s in symbols], dtype=np.float64),
        news_known=news.known,
    )
    info = {
        "prev": prev.isoformat() if prev else None,
        "prior_sessions": len(priors),
        "symbols": len(symbols),
        "left_out": bars["left_out"],
        "prev_close_known": int(np.isfinite(prev_close).sum()),
        "splits_in_lookback": sorted({s for s, _ in factors}),
        "news": news.note,
        "floats": sum(1 for s in symbols if s in floats),
    }
    return inputs, info


def rebuild_day(
    session_date: date,
    *,
    top_n: int = TOP_N_DEFAULT,
    database: Path | None = None,
    dry_run: bool = False,
    **sources,
) -> dict:
    """Rebuild one session and (unless ``dry_run``) replace its reconstructed rows in the store."""
    t0 = time.time()
    inputs, info = assemble(session_date, **sources)
    if inputs is None:
        return {"date": session_date.isoformat(), **info}
    iso = session_date.isoformat()
    stats = {"minutes": 0, "rows": 0, "s5_minutes": 0, "max_rows": 0}
    rows_buf: list[dict] = []
    cov_buf: list[dict] = []

    def flush(db) -> None:
        if db is not None and cov_buf:
            store.write_batch(db, rows=rows_buf, coverage=cov_buf)
        rows_buf.clear()
        cov_buf.clear()

    def run(db) -> None:
        for minute_ts, rows in day_boards(inputs, top_n):
            rows_buf.extend(rows)
            cov_buf.append(coverage_row(iso, minute_ts, len(rows)))
            stats["minutes"] += 1
            stats["rows"] += len(rows)
            stats["max_rows"] = max(stats["max_rows"], len(rows))
            stats["s5_minutes"] += bool(leader_symbols(rows, S5_RULES))
            if len(cov_buf) >= WRITE_CHUNK_MINUTES:
                flush(db)
        flush(db)

    if dry_run:
        run(None)
    else:
        with store.connect(database) as db:
            store.replace_day(db, iso, LEADERBOARD_SOURCE_RECONSTRUCTED)
            run(db)
    return {"date": iso, **info, **stats, "seconds": round(time.time() - t0, 1)}


def _dates(args, minute: dict[date, Path]) -> list[date]:
    if args.date:
        d = date.fromisoformat(args.date)
        return [d] if d in minute else []
    start = date.fromisoformat(args.start) if args.start else min(minute)
    end = date.fromisoformat(args.end) if args.end else max(minute)
    return [d for d in minute if start <= d <= end]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="one session, YYYY-MM-DD")
    ap.add_argument("--start", help="first session of a range, YYYY-MM-DD")
    ap.add_argument("--end", help="last session of a range, YYYY-MM-DD")
    ap.add_argument("--top", type=int, default=TOP_N_DEFAULT, help="rows kept per minute besides preset picks")
    ap.add_argument("--db", type=Path, default=None, help=f"leaderboard store (default {store.path()})")
    ap.add_argument("--data-root", type=Path, default=DATA_ROOT, help="Massive flat-file root")
    ap.add_argument("--dry-run", action="store_true", help="build and report, write nothing")
    args = ap.parse_args()
    if not (args.date or args.start or args.end):
        ap.error("give --date or --start/--end")

    minute = files_by_date(args.data_root / MINUTE_SUBDIR)
    dates = _dates(args, minute)
    if not dates:
        ap.error("no minute files in that range")
    ref_dir = args.data_root / REFERENCE_SUBDIR
    research, note = open_research_db(args.data_root / RESEARCH_DB.relative_to(DATA_ROOT))
    print(note, flush=True)
    try:
        reference = load_reference(research, ref_dir)
        splits = load_splits(research, ref_dir)
        all_dates = list(minute)
        windows = [
            w for d in dates
            if (w := news_window(all_dates[all_dates.index(d) - 1] if all_dates.index(d) else None, d))
        ]
        span = (min(w[0] for w in windows), max(w[1] for w in windows)) if windows else (0.0, 0.0)
        archive = load_news_archive(research, ref_dir, *span)
    finally:
        if research is not None:
            research.close()   # never hold the research store while the build runs
    print(f"reference {reference.source}: {len(reference.universe())} common/ADR tickers, "
          f"{len(splits)} splits, {len(archive.articles)} ticker-articles loaded", flush=True)
    print(f"store {'(dry run)' if args.dry_run else (args.db or store.path())}", flush=True)
    con = work_db()
    for d in dates:
        stats = rebuild_day(
            d, top_n=args.top, database=args.db, dry_run=args.dry_run,
            data_root=args.data_root, reference=reference, splits=splits,
            news_for=archive.for_window, floats_for=lambda day: load_floats(ARCHIVE_DB, day)[0], con=con,
        )
        print(" ".join(f"{k}={v}" for k, v in stats.items() if k != "splits_in_lookback"), flush=True)
        if stats.get("splits_in_lookback"):
            print(f"  splits adjusted in the RVOL lookback / prior close: {', '.join(stats['splits_in_lookback'])}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
