"""Spot-check a rebuilt leaderboard day against the flat files, independently (ADR 023).

For each chosen minute the whole-market board is recomputed from scratch with pandas --
the minute file, the prior session's day-aggregate file, reference/tickers.json and
reference/splits.json read directly; none of the builder's code, SQL or research store --
and compared with the stored reconstructed rows: every stored row's rank, change_pct,
price and volume, and that every symbol the independent board ranks 1..N (N = the
top N stored contiguously) is stored with that rank. Exit status 1 on any mismatch.

Usage (from the repo root):
    py -3 research/leaderboard/spot_check.py --date 2026-09-21 --minutes 07:05 07:42 08:30 09:31 09:58
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ET = ZoneInfo("America/New_York")
UNIVERSE = ("CS", "ADRC")
DATA_ROOT = Path(r"F:\Nova\data\massive")
CHANGE_TOL = 1e-12
VOLUME_REL_TOL = 1e-9


def day_file(root: Path, kind: str, d: date) -> Path:
    return root / kind / f"{d:%Y}" / f"{d:%m}" / f"{d.isoformat()}.csv.gz"


def prior_session(root: Path, d: date) -> date | None:
    days = sorted(date.fromisoformat(p.name[:10]) for p in (root / "minute_aggs_v1").glob("*/*/*.csv.gz"))
    earlier = [x for x in days if x < d]
    return earlier[-1] if earlier else None


def load_minutes(path: Path, universe: set[str]) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=["ticker", "volume", "close", "window_start"],
                     dtype={"ticker": str, "volume": float, "close": float, "window_start": "int64"})
    df = df[df["ticker"].isin(universe)].copy()
    df["start_s"] = df["window_start"] // 1_000_000_000
    return df.sort_values(["ticker", "window_start"], kind="mergesort")


def prior_closes(path: Path, splits: list[dict], prev: date, d: date) -> pd.Series:
    closes = pd.read_csv(path, usecols=["ticker", "close"], dtype={"ticker": str, "close": float})
    closes = closes[closes["close"] > 0].set_index("ticker")["close"].copy()
    for s in splits:
        ex = date.fromisoformat(s["execution_date"])
        if prev < ex <= d and s.get("ticker") in closes.index and s.get("split_from") and s.get("split_to"):
            closes[s["ticker"]] *= float(s["split_from"]) / float(s["split_to"])
    return closes


def independent_board(minutes: pd.DataFrame, closes: pd.Series, session_open: int, minute_ts: int) -> pd.DataFrame:
    """Rank every universe symbol that has a bar closed by ``minute_ts``, as rank_rows orders them."""
    closed = minutes[(minutes["start_s"] >= session_open) & (minutes["start_s"] + 60 <= minute_ts)]
    g = closed.groupby("ticker", sort=True)
    board = pd.DataFrame({"price": g["close"].last(), "volume": g["volume"].sum()})
    board["prev_close"] = closes.reindex(board.index)
    ok = (board["price"] > 0) & (board["prev_close"] > 0)
    board["change_pct"] = np.where(ok, (board["price"] - board["prev_close"]) / board["prev_close"], np.nan)
    order = np.lexsort((
        board.index.to_numpy(dtype=str),
        -board["volume"].fillna(0.0).to_numpy(),
        np.where(np.isnan(board["change_pct"]), np.inf, -board["change_pct"].to_numpy()),
    ))
    board = board.iloc[order]
    board["rank"] = np.arange(1, len(board) + 1)
    return board


def compare(stored: list[dict], board: pd.DataFrame) -> tuple[dict, list[str]]:
    problems: list[str] = []
    counts = {"stored": len(stored), "market": len(board), "rank": 0, "change": 0, "price": 0, "volume": 0}
    for row in stored:
        sym = row["symbol"]
        if sym not in board.index:
            problems.append(f"{sym}: stored but not on the independent board")
            continue
        ind = board.loc[sym]
        counts["rank"] += int(ind["rank"]) == row["rank"]
        a, b = row["change_pct"], ind["change_pct"]
        counts["change"] += (a is None and np.isnan(b)) or (a is not None and abs(a - b) <= CHANGE_TOL)
        counts["price"] += row["price"] == ind["price"]
        counts["volume"] += abs(row["volume"] - ind["volume"]) <= VOLUME_REL_TOL * max(1.0, ind["volume"])
        if int(ind["rank"]) != row["rank"] or not ((a is None and np.isnan(b)) or (a is not None and abs(a - b) <= CHANGE_TOL)):
            problems.append(f"{sym}: stored rank {row['rank']} change {a} vs independent {int(ind['rank'])} {b}")
    for key in ("rank", "change", "price", "volume"):
        if counts[key] != counts["stored"]:
            problems.append(f"{counts['stored'] - counts[key]} stored rows disagree on {key}")
    contiguous = 0
    ranks = {row["rank"] for row in stored}
    while contiguous + 1 in ranks:
        contiguous += 1
    missing = [s for s in board.index[:contiguous] if s not in {row["symbol"] for row in stored}]
    counts["top"] = contiguous
    if missing:
        problems.append(f"independent top {contiguous} not stored: {missing[:10]}")
    return counts, problems


def stored_rows(db_path: Path, d: date, minute_ts: int) -> list[dict]:
    db = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT symbol, rank, price, prev_close, change_pct, volume FROM rows WHERE session_date = ?"
            " AND source = 'reconstructed' AND board = 'market' AND minute_ts = ? ORDER BY rank",
            (d.isoformat(), minute_ts),
        ).fetchall()
    finally:
        db.close()
    return [dict(r) for r in rows]


def default_db() -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
    from leaderboard import store

    return store.path()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True)
    ap.add_argument("--minutes", nargs="+", required=True, help="HH:MM ET boundaries, e.g. 07:05 09:31")
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--data-root", type=Path, default=DATA_ROOT)
    args = ap.parse_args()
    d = date.fromisoformat(args.date)
    db_path = args.db or default_db()
    ref = args.data_root / "store" / "reference"
    universe = {t["ticker"] for t in json.loads((ref / "tickers.json").read_text(encoding="utf-8"))
                if t.get("type") in UNIVERSE and t.get("ticker")}
    splits = json.loads((ref / "splits.json").read_text(encoding="utf-8"))
    prev = prior_session(args.data_root, d)
    minutes = load_minutes(day_file(args.data_root, "minute_aggs_v1", d), universe)
    closes = prior_closes(day_file(args.data_root, "day_aggs_v1", prev), splits, prev, d)
    session_open = int(datetime(d.year, d.month, d.day, 4, 0, tzinfo=ET).timestamp())
    print(f"spot check {d} (prior session {prev}) store {db_path}")
    print(f"{'minute ET':<10}{'stored':>7}{'market':>8}{'top':>5}{'rank ok':>9}{'chg ok':>8}"
          f"{'px ok':>7}{'vol ok':>8}  leader stored / independent")
    failed = False
    for hm in args.minutes:
        hh, mm = (int(x) for x in hm.split(":"))
        minute_ts = int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET).timestamp())
        stored = stored_rows(db_path, d, minute_ts)
        board = independent_board(minutes, closes, session_open, minute_ts)
        counts, problems = compare(stored, board)
        failed |= bool(problems) or not stored
        lead_s = stored[0]["symbol"] if stored else "-"
        lead_i = board.index[0] if len(board) else "-"
        print(f"{hm:<10}{counts['stored']:>7}{counts['market']:>8}{counts['top']:>5}{counts['rank']:>9}"
              f"{counts['change']:>8}{counts['price']:>7}{counts['volume']:>8}  {lead_s} / {lead_i}")
        for p in problems[:10]:
            print(f"    MISMATCH {p}")
    print("FAIL" if failed else "OK: every stored row matches the independent board")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
