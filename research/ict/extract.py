"""Pull every 04:00-20:00 minute bar of SPY and QQQ on every day on disk into one Parquet file.

Reads go through ``market_reads`` (the indexed Massive minute files); prices stay raw (neither symbol split in
2016-2026). The file lives beside the other research stores, never in the repo. Re-running skips days already in it.

Usage:
    py -3 research/ict/extract.py [--symbols SPY QQQ]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "orb"))

from common import MINUTE_DIR, STORE_DIR, minute_files  # noqa: E402
from market_reads import reads  # noqa: E402

OUT = STORE_DIR / "ict_minutes.parquet"
COLUMNS = ["symbol", "day", "minute", "open", "high", "low", "close", "volume"]


def one_day(symbol: str, day: str) -> pd.DataFrame:
    frame = reads.read_file("minute_aggs_v1", symbol, day)
    if not len(frame):
        return pd.DataFrame(columns=COLUMNS)
    t = frame["time_et"]
    out = pd.DataFrame({
        "symbol": symbol, "day": day, "minute": (t.dt.hour * 60 + t.dt.minute).astype("int16"),
        "open": frame["open"], "high": frame["high"], "low": frame["low"], "close": frame["close"],
        "volume": frame["volume"].astype("float64"),   # fractional on 2026 days; astype(int64) truncated it (#1219)
    })
    return out[(out["minute"] >= 4 * 60) & (out["minute"] < 20 * 60)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["SPY", "QQQ"])
    args = ap.parse_args()
    days = [d.isoformat() for d in minute_files()]
    if not days:
        raise SystemExit(f"no minute files under {MINUTE_DIR}")
    have = pd.read_parquet(OUT) if OUT.exists() else pd.DataFrame(columns=COLUMNS)
    done = set(zip(have["symbol"], have["day"], strict=True))
    parts = [have]
    t0 = time.time()
    todo = [(s, d) for d in days for s in args.symbols if (s, d) not in done]
    print(f"{len(days)} days on disk, {len(todo)} symbol-days to read", flush=True)
    for i, (symbol, day) in enumerate(todo, 1):
        parts.append(one_day(symbol, day))
        if i % 200 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)}  {day}  {time.time() - t0:.0f}s", flush=True)
    out = pd.concat(parts, ignore_index=True).sort_values(["symbol", "day", "minute"])
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"wrote {len(out):,} bars to {OUT}", flush=True)


if __name__ == "__main__":
    main()
