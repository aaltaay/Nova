"""Gate 1 robustness: try to break the ORB result before believing it.

Runs the simulator over a neighbourhood of the published parameters and over cost
assumptions, then reads the base run's trade list for rank-bucket and year splits.
Kill criteria (Bot-Trading-Plan.md): edge lives in one year, dies at 2x costs,
< 300 trades, or the parameter neighbourhood is not mostly positive.

Usage:
    py -3 research/orb/robustness.py --tag base
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace

import pandas as pd

from backtest_orb import Params, run
from common import STORE_DIR, load_env

GRID_TOP = (10, 20, 30)
GRID_STOP = (0.05, 0.10, 0.20, 0.50)
GRID_SLIP = (0.0, 0.01, 0.02, 0.03)


def _row(tag: str, out: dict) -> dict:
    return {
        "run": tag, "trades": out.get("trades"), "win%": out.get("win_rate_pct"),
        "PF": out.get("profit_factor"), "exp_R": out.get("expectancy_r"), "exp_$": out.get("expectancy_usd"),
        "CAGR%": out.get("cagr_pct"), "maxDD%": out.get("max_drawdown_pct"), "sharpe": out.get("sharpe"),
    }


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="base")
    ap.add_argument("--start-equity", type=float, default=Params.start_equity)
    ap.add_argument("--quick", action="store_true", help="stop grid only")
    a = ap.parse_args()
    base = Params(tag=a.tag, start_equity=a.start_equity)
    rows: list[dict] = []
    t0 = time.time()

    print("== stop x top neighbourhood (slippage $0.01) ==", flush=True)
    for top in (GRID_TOP if not a.quick else (base.top,)):
        for stop in GRID_STOP:
            p = replace(base, top=top, stop_atr=stop, tag=f"{a.tag}_t{top}_s{stop}")
            rows.append(_row(f"top={top} stop={stop}", run(p)))
            print(pd.DataFrame(rows[-1:]).to_string(index=False, header=len(rows) == 1), flush=True)

    if not a.quick:
        print("== cost sensitivity (top=20, stop=0.10) ==", flush=True)
        for slip in GRID_SLIP:
            p = replace(base, slippage=slip, tag=f"{a.tag}_slip{slip}")
            rows.append(_row(f"slip=${slip}", run(p)))
        rows.append(_row("paper costs ($0.0035, no slip)",
                         run(replace(base, slippage=0.0, commission_per_share=0.0035, commission_min=0.0,
                                     tag=f"{a.tag}_papercosts"))))
        rows.append(_row("2x costs ($0.01/sh, $0.02 slip)",
                         run(replace(base, slippage=0.02, commission_per_share=0.01, tag=f"{a.tag}_2xcosts"))))
        print("== entry cutoff / sizing ==", flush=True)
        rows.append(_row("cutoff 10:30", run(replace(base, entry_cutoff="10:30", tag=f"{a.tag}_cut1030"))))
        rows.append(_row("cutoff 12:00", run(replace(base, entry_cutoff="12:00", tag=f"{a.tag}_cut1200"))))
        rows.append(_row("risk 0.5%", run(replace(base, risk_pct=0.005, tag=f"{a.tag}_risk05"))))
        rows.append(_row("equity $100k", run(replace(base, start_equity=100_000.0, tag=f"{a.tag}_eq100k"))))

    table = pd.DataFrame(rows)
    print("\n== summary ==")
    print(table.to_string(index=False))

    # Rank buckets and years from the base trade list: does the edge decay with rank,
    # and does one year carry the result?
    trades_path = STORE_DIR / f"orb_{a.tag}_trades.csv"
    if trades_path.exists():
        tr = pd.read_csv(trades_path)
        tr["bucket"] = pd.cut(tr["rank"], [0, 5, 10, 20, 30], labels=["1-5", "6-10", "11-20", "21-30"])
        by_bucket = tr.groupby("bucket", observed=True).agg(
            trades=("pnl", "size"), win_pct=("pnl", lambda s: round(100 * (s > 0).mean(), 1)),
            exp_R=("r", "mean"), pnl=("pnl", "sum")).round(3)
        print("\n== by rank bucket (base run) ==")
        print(by_bucket.to_string())
        tr["year"] = tr["d"].str[:4]
        by_year = tr.groupby("year").agg(
            trades=("pnl", "size"), win_pct=("pnl", lambda s: round(100 * (s > 0).mean(), 1)),
            exp_R=("r", "mean"), pnl=("pnl", "sum"), fees=("fees", "sum")).round(2)
        print("\n== by year (base run) ==")
        print(by_year.to_string())
        tr["month"] = tr["d"].str[:7]
        monthly = tr.groupby("month")["pnl"].sum()
        print(f"\nmonths positive: {int((monthly > 0).sum())}/{len(monthly)}  "
              f"best {monthly.max():.0f}  worst {monthly.min():.0f}")

    (STORE_DIR / f"robustness_{a.tag}.json").write_text(table.to_json(orient="records", indent=2), encoding="utf-8")
    print(f"\n({time.time() - t0:.0f}s; robustness_{a.tag}.json under {STORE_DIR})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
