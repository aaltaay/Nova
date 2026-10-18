"""A6 gate 1: the pre-registered rule, its neighbourhood and the cost ladder on SPY / QQQ (Bot-Trading-Plan.md 2i).

Reads ``ict_minutes.parquet`` (``extract.py``), plays every session through ``rules.run_day``, sizes each fill on a
$25,000 account and charges IBKR fixed commission plus slippage on every fill. Writes the summary beside this file
and the base run's trades to the research store.

Usage:
    py -3 research/ict/backtest.py
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "orb"))

from common import STORE_DIR  # noqa: E402
from rules import Params, hourly, levels, run_day  # noqa: E402

SOURCE = STORE_DIR / "ict_minutes.parquet"
RESULTS = HERE / "results_2026-10-18.json"
PREMARKET_HOURS_END = 9 * 60            # the 09:00 hourly bar is still forming at 09:30


@dataclass(frozen=True)
class Costs:
    commission: float = 0.005
    commission_min: float = 1.0
    slippage: float = 0.01


@dataclass(frozen=True)
class Account:
    equity: float = 25_000.0
    risk_pct: float = 0.01
    notional_x: float = 2.0


def load() -> dict[str, list[tuple[str, tuple[np.ndarray, ...]]]]:
    frame = pd.read_parquet(SOURCE)
    out: dict[str, list] = {}
    for (symbol, day), g in frame.groupby(["symbol", "day"], sort=True):
        cols = tuple(g[c].to_numpy() for c in ("minute", "open", "high", "low", "close"))
        out.setdefault(symbol, []).append((day, cols))
    return out


def signals(days: list, p: Params) -> list[tuple[str, object]]:
    """Every trade the rule takes on one symbol, in day order."""
    full = [hourly(d[0], d[2], d[3]) for _, d in days]
    trades = []
    for n, (day, (minute, o, h, low, c)) in enumerate(days):
        if n < p.lookback:
            continue
        rth = np.flatnonzero(minute >= 9 * 60 + 30)
        if not len(rth):
            continue
        prior = full[n - p.lookback:n]
        today = hourly(minute, h, low, before=PREMARKET_HOURS_END)
        hh = np.concatenate([x[0] for x in prior] + [today[0]])
        hl = np.concatenate([x[1] for x in prior] + [today[1]])
        supply, demand = levels(hh, hl, float(o[rth[0]]), p.hour_strength)
        trade = run_day(minute, o, h, low, c, supply, demand, p)
        if trade is not None:
            trades.append((day, trade))
    return trades


def commission(shares: int, price: float, costs: Costs) -> float:
    fee = max(costs.commission * shares, costs.commission_min)
    return min(fee, 0.01 * shares * price) if costs.commission_min else costs.commission * shares


def account_run(rows: list[dict], costs: Costs, account: Account) -> pd.DataFrame:
    """Size and charge every trade in day order; same-day trades size from the morning's equity."""
    equity = account.equity
    out = []
    if not rows:
        return pd.DataFrame()
    for day, group in pd.DataFrame(rows).groupby("day", sort=True):
        morning = equity
        for r in group.itertuples():
            risk_ps = abs(r.entry - r.stop)
            if risk_ps <= 0:
                continue
            shares = int(min(morning * account.risk_pct / risk_ps, account.notional_x * morning / r.entry))
            if shares <= 0:
                continue
            gross = (r.exit - r.entry) * r.side * shares
            cost = (2 * costs.slippage * shares + commission(shares, r.entry, costs)
                    + commission(shares, r.exit, costs))
            pnl = gross - cost
            equity += pnl
            out.append({**r._asdict(), "shares": shares, "pnl": pnl, "cost": cost,
                        "r_net": pnl / (shares * risk_ps), "r_gross": (r.exit - r.entry) * r.side / risk_ps})
    return pd.DataFrame(out).drop(columns=["Index"], errors="ignore")


def summarize(t: pd.DataFrame, account: Account, all_days: list[str]) -> dict:
    if t.empty:
        return {"trades": 0}
    wins, losses = t.loc[t.pnl > 0, "pnl"].sum(), -t.loc[t.pnl < 0, "pnl"].sum()
    daily = t.groupby("day")["pnl"].sum().reindex(all_days, fill_value=0.0)
    eq = account.equity + daily.cumsum()
    ret = daily / eq.shift(1, fill_value=account.equity)
    years = (pd.Timestamp(all_days[-1]) - pd.Timestamp(all_days[0])).days / 365.25
    final = float(eq.iloc[-1])
    by_year = t.groupby(t.day.str[:4])["pnl"].sum().round(0).to_dict()
    best = t.pnl.nlargest(10).sum()
    total = float(t.pnl.sum())
    by_month = t.groupby(t.day.str[:7])["pnl"].sum()
    return {
        "trades": int(len(t)), "win_rate": round(float((t.pnl > 0).mean()), 3),
        "profit_factor": round(float(wins / losses), 3) if losses else None,
        "exp_r_net": round(float(t.r_net.mean()), 3), "exp_r_gross": round(float(t.r_gross.mean()), 3),
        "total_pnl": round(total, 0), "cagr": round((max(final, 1) / account.equity) ** (1 / years) - 1, 4),
        "max_dd": round(float((eq / eq.cummax() - 1).min()), 4),
        "sharpe": round(float(ret.mean() / ret.std() * math.sqrt(252)), 2) if ret.std() else None,
        "by_year": by_year, "without_best_year": round(total - max(by_year.values()), 0),
        "best10_share": round(float(best / total), 2) if total > 0 else None,
        "months_positive": f"{int((by_month > 0).sum())} of {len(by_month)}",
        "reasons": t.reason.value_counts().to_dict(),
        "median_risk_per_share": round(float((t.entry - t.stop).abs().median()), 3),
        "median_cost_r": round(float((t.cost / (t.shares * (t.entry - t.stop).abs())).median()), 3),
    }


def trade_rows(data: dict, p: Params) -> list[dict]:
    rows = []
    for symbol, days in data.items():
        for day, tr in signals(days, p):
            rows.append({"symbol": symbol, "day": day, **asdict(tr)})
    return rows


def main() -> None:
    data = load()
    all_days = sorted({d for days in data.values() for d, _ in days})
    base, account = Params(), Account()
    neighbours = {
        "target 1.5R": replace(base, target_r=1.5), "target 3R": replace(base, target_r=3.0),
        "window to 10:00": replace(base, window_end=10 * 60), "window to 11:00": replace(base, window_end=11 * 60),
        "hourly swing strength 3": replace(base, hour_strength=3),
        "lookback 5 sessions": replace(base, lookback=5), "lookback 20 sessions": replace(base, lookback=20),
        "entry at the far edge": replace(base, far_edge=True), "no 50% rule": replace(base, premium=False),
    }
    ladder = {
        "zero costs": Costs(0, 0, 0), "slippage $0.02": Costs(slippage=0.02),
        "slippage $0.03": Costs(slippage=0.03), "2x costs": Costs(0.01, 1.0, 0.02),
    }
    base_rows = trade_rows(data, base)
    base_t = account_run(base_rows, Costs(), account)
    out = {"period": [all_days[0], all_days[-1]], "sessions": len(all_days), "params": asdict(base),
           "account": asdict(account), "costs": asdict(Costs()), "base": summarize(base_t, account, all_days)}
    out["split"] = {f"{name} {key}": summarize(g, account, all_days)
                    for name, col in (("symbol", "symbol"), ("side", "side")) for key, g in base_t.groupby(col)}
    out["ladder"] = {name: summarize(account_run(base_rows, c, account), account, all_days)
                     for name, c in ladder.items()}
    out["neighbourhood"] = {}
    for name, p in neighbours.items():
        out["neighbourhood"][name] = summarize(account_run(trade_rows(data, p), Costs(), account), account, all_days)
        print(f"  {name}: {out['neighbourhood'][name].get('profit_factor')}", flush=True)
    pfs = [v.get("profit_factor") or 0 for v in out["neighbourhood"].values()]
    b = out["base"]
    out["kill"] = {
        "at_least_300_trades": b["trades"] >= 300,
        "survives_without_best_year": b.get("without_best_year", 0) > 0,
        "neighbourhood_mostly_positive": sum(pf > 1 for pf in pfs) > len(pfs) / 2,
        "survives_2x_costs": (out["ladder"]["2x costs"].get("profit_factor") or 0) > 1,
    }
    out["verdict"] = "passed" if all(out["kill"].values()) and (b.get("profit_factor") or 0) > 1 else "not passed"
    RESULTS.write_text(json.dumps(out, indent=2), encoding="utf-8")
    base_t.to_csv(STORE_DIR / "ict_trades_base.csv", index=False)
    print(json.dumps({k: out[k] for k in ("base", "kill", "verdict")}, indent=2))


if __name__ == "__main__":
    main()
