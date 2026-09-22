"""Boring baseline: five published SPY mean-reversion swing rules on free daily bars.

Rules follow the "5 swing trading strategies for beginners" write-up (QuantifiedStrategies):
every rule buys SPY at the close when its condition holds and sells at the close of the
first later day whose close is above the previous day's high. One position at a time per
rule, 100% of equity, and a cost of ``cost_pct`` of the trade value on each side.

  band_ibs   close < (10-day high - 2.5 x 25-day mean range) and IBS < 0.3
  turnaround Monday close < Friday close < Thursday close (buy Monday close)
  low5       close < the lowest low of the previous 5 days
  vol_contr  5-day ADX > 40 and today's range is the smallest of the last 6 days
  newhigh_ibs today's high > previous 10-day high and IBS < 0.15
  combined   long whenever any rule is in a trade (one position, 100% of equity)

This is a comparison point for the ORB study, not a candidate for the bot: a few trades
a month on one index, no scanner, no intraday data. Fits a cash account.

Usage:
    py -3 research/orb/swing_baseline.py --from 1993-02-01
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from common import STORE_DIR


def adx(df: pd.DataFrame, n: int) -> pd.Series:
    """Wilder's ADX."""
    high, low, close = df["High"], df["Low"], df["Close"]
    up, down = high.diff(), -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def signals(df: pd.DataFrame) -> pd.DataFrame:
    h, lo, c = df["High"], df["Low"], df["Close"]
    rng = h - lo
    ibs = ((c - lo) / rng.replace(0, np.nan)).fillna(0.5)
    out = pd.DataFrame(index=df.index)
    out["band_ibs"] = (c < (h.rolling(10).max() - 2.5 * rng.rolling(25).mean())) & (ibs < 0.3)
    weekday = pd.Series(df.index.dayofweek, index=df.index)
    out["turnaround"] = (weekday == 0) & (c < c.shift(1)) & (c.shift(1) < c.shift(2))
    out["low5"] = c < lo.shift(1).rolling(5).min()
    out["vol_contr"] = (adx(df, 5) > 40) & (rng == rng.rolling(6).min())
    out["newhigh_ibs"] = (h > h.shift(1).rolling(10).max()) & (ibs < 0.15)
    out["exit"] = c > h.shift(1)
    return out


def backtest_rule(df: pd.DataFrame, entry: pd.Series, exit_: pd.Series, cost_pct: float) -> dict:
    close = df["Close"].to_numpy(dtype=float)
    ent, ex = entry.to_numpy(), exit_.to_numpy()
    equity, in_trade, entry_px, entry_i = 1.0, False, 0.0, 0
    trades: list[float] = []
    days_in = 0
    curve = np.ones(len(close))
    for i in range(len(close)):
        if in_trade:
            days_in += 1
            if ex[i]:
                gross = close[i] / entry_px
                net = gross * (1 - cost_pct) ** 2
                equity *= net
                trades.append(net - 1)
                in_trade = False
        if not in_trade and ent[i]:
            in_trade, entry_px, entry_i = True, close[i], i
        curve[i] = equity * (close[i] / entry_px if in_trade else 1.0)
    curve_s = pd.Series(curve, index=df.index)
    dd = curve_s / curve_s.cummax() - 1
    years = (df.index[-1] - df.index[0]).days / 365.25
    tr = np.array(trades)
    return {
        "trades": int(len(tr)),
        "win_rate_pct": round(100 * float((tr > 0).mean()), 1) if len(tr) else None,
        "avg_trade_pct": round(100 * float(tr.mean()), 3) if len(tr) else None,
        "profit_factor": round(float(tr[tr > 0].sum() / -tr[tr < 0].sum()), 2) if len(tr) and (tr < 0).any() else None,
        "cagr_pct": round(100 * (equity ** (1 / years) - 1), 2),
        "total_return_pct": round(100 * (equity - 1), 1),
        "max_drawdown_pct": round(100 * float(dd.min()), 1),
        "time_in_market_pct": round(100 * days_in / len(close), 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="SPY")
    ap.add_argument("--from", dest="start", default="1993-02-01")
    ap.add_argument("--cost-pct", type=float, default=0.0003, help="per side, as a fraction (0.0003 = 0.03%)")
    a = ap.parse_args()
    df = yf.download(a.symbol, start=a.start, auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    sig = signals(df)
    rules = ["band_ibs", "turnaround", "low5", "vol_contr", "newhigh_ibs"]
    results = {r: backtest_rule(df, sig[r], sig["exit"], a.cost_pct) for r in rules}
    results["combined_any"] = backtest_rule(df, sig[rules].any(axis=1), sig["exit"], a.cost_pct)
    bh = df["Close"].iloc[-1] / df["Close"].iloc[0]
    years = (df.index[-1] - df.index[0]).days / 365.25
    results["buy_and_hold"] = {"cagr_pct": round(100 * (bh ** (1 / years) - 1), 2),
                               "max_drawdown_pct": round(100 * float((df["Close"] / df["Close"].cummax() - 1).min()), 1),
                               "time_in_market_pct": 100.0}
    out = {"symbol": a.symbol, "from": str(df.index[0].date()), "to": str(df.index[-1].date()),
           "cost_pct_per_side": a.cost_pct, "rules": results}
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    Path(STORE_DIR / f"swing_baseline_{a.symbol}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"{a.symbol} {out['from']}..{out['to']}  cost {a.cost_pct:.4%} per side")
    cols = ["trades", "win_rate_pct", "avg_trade_pct", "profit_factor", "cagr_pct", "max_drawdown_pct", "time_in_market_pct"]
    print(f"{'rule':14}" + "".join(f"{c:>19}" for c in cols))
    for name, r in results.items():
        print(f"{name:14}" + "".join(f"{str(r.get(c, '')):>19}" for c in cols))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
