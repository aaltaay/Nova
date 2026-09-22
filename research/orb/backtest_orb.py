"""Long-only 5-minute opening range breakout on stocks in play -- honest simulation.

Rules (Zarattini, Barbon & Aziz 2024, long side only, cash account -- no leverage):
  * universe + top-N by opening relative volume come from ``selection`` (build_store.py)
  * a green first candle places a buy stop at the 5-minute high; red or doji: no trade
  * stop loss = ``stop_atr`` x ATR14 below the fill; exit at the last regular-session bar
  * risk ``risk_pct`` of equity per position, notional capped per position and per day
    at the account's cash (no margin); orders reserve cash at placement in rank order
Fills are pessimistic: entry at max(bar open, level) + slippage on the first bar that
trades through the level; stop at min(bar open, stop) - slippage on the first bar whose
low touches it, and a stop touched on the entry bar itself is treated as hit; the close
exit pays slippage too. Commission is IBKR fixed: $0.005/share, min $1, max 1% of value,
each side. Nothing reads a bar ahead of the one it is deciding on.

Usage:
    py -3 research/orb/backtest_orb.py --top 20 --tag base
    py -3 research/orb/backtest_orb.py --top 20 --stop-atr 0.05 --slippage 0.02 --tag tight
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from datetime import time as dtime

import numpy as np
import pandas as pd

from common import STORE_DIR, connect, load_env


@dataclass
class Params:
    top: int = 20
    stop_atr: float = 0.10
    risk_pct: float = 0.01
    max_position_pct: float = 0.25   # notional cap per position as a share of equity (cash account)
    min_notional: float = 500.0      # skip orders smaller than this (fees would dominate)
    slippage: float = 0.01           # $/share paid on every fill
    commission_per_share: float = 0.005
    commission_min: float = 1.0
    commission_max_pct: float = 0.01
    entry_cutoff: str = "15:30"      # no new entries at or after this time
    start_equity: float = 25_000.0
    date_from: str | None = None
    date_to: str | None = None
    tag: str = "base"


def commission(shares: int, value: float, p: Params) -> float:
    return min(max(shares * p.commission_per_share, p.commission_min), p.commission_max_pct * value)


def simulate_symbol_day(bars: pd.DataFrame, level: float, stop_dist: float, cutoff: dtime, p: Params):
    """Return (entry_i, entry_px, exit_i, exit_px, reason) or None when the stop never fills."""
    t = bars["t"].to_numpy()
    o = bars["open"].to_numpy(dtype=float)
    h = bars["high"].to_numpy(dtype=float)
    lo = bars["low"].to_numpy(dtype=float)
    c = bars["close"].to_numpy(dtype=float)
    # first bar after the opening range that trades through the level, before the cutoff
    after_range = np.array([tt >= dtime(9, 35) and tt < cutoff for tt in t])
    hit = np.flatnonzero(after_range & (h >= level))
    if hit.size == 0:
        return None
    i = int(hit[0])
    entry = max(o[i], level) + p.slippage
    stop = entry - stop_dist
    # Entry bar: the bar's low may have printed before the fill, so it only counts as a
    # stop-out when the bar *finishes* at or below the stop. Later bars: the first low
    # at or below the stop fills it, at the open when the bar gaps through.
    if c[i] <= stop:
        return i, entry, i, stop - p.slippage, "stop"
    stopped = np.flatnonzero(lo[i + 1:] <= stop)
    if stopped.size:
        j = i + 1 + int(stopped[0])
        return i, entry, j, min(o[j], stop) - p.slippage, "stop"
    j = len(bars) - 1
    return i, entry, j, c[j] - p.slippage, "close"


def run(p: Params) -> dict:
    con = connect(read_only=True)
    where = ["rank <= ?", "direction = 'long'"]
    args: list = [p.top]
    if p.date_from:
        where.append("d >= ?")
        args.append(p.date_from)
    if p.date_to:
        where.append("d <= ?")
        args.append(p.date_to)
    sel = con.execute(
        f"SELECT ticker, d, rank, rvol, o5_high, atr14, prev_close, o5_open FROM selection "
        f"WHERE {' AND '.join(where)} ORDER BY d, rank", args
    ).df()
    days = sorted(sel["d"].unique())
    mins = con.execute(
        "SELECT m.ticker, m.d, m.t, m.open, m.high, m.low, m.close, m.volume FROM minutes_selected m "
        "JOIN (SELECT DISTINCT ticker, d FROM selection WHERE " + " AND ".join(where) + ") s USING (ticker, d) "
        "ORDER BY m.d, m.ticker, m.t", args
    ).df()
    con.close()
    groups = {k: g for k, g in mins.groupby(["ticker", "d"], sort=False)}
    cutoff = dtime(*(int(x) for x in p.entry_cutoff.split(":")))

    equity = p.start_equity
    trades: list[dict] = []
    curve: list[dict] = []
    for d in days:
        cash = equity  # settled cash from yesterday's closes (T+1) -- no margin
        day_pnl = 0.0
        for row in sel[sel["d"] == d].itertuples(index=False):
            stop_dist = p.stop_atr * float(row.atr14)
            if not (stop_dist > 0) or not (row.o5_high > 0):
                continue
            level = float(row.o5_high)
            risk_dollars = p.risk_pct * equity
            shares = int(min(risk_dollars / stop_dist, p.max_position_pct * equity / level, cash / level))
            if shares < 1 or shares * level < p.min_notional:
                continue  # too small to survive the $1 minimum commission; skip rather than pretend
            cash -= shares * level  # reserved at placement, like a cash account's buying-power check
            bars = groups.get((row.ticker, d))
            if bars is None or len(bars) < 6:
                continue
            res = simulate_symbol_day(bars, level, stop_dist, cutoff, p)
            if res is None:
                continue  # never triggered; reservation wasted for the day
            i, entry, j, exit_px, reason = res
            fee = commission(shares, shares * entry, p) + commission(shares, shares * exit_px, p)
            pnl = shares * (exit_px - entry) - fee
            day_pnl += pnl
            trades.append({
                "d": str(d), "ticker": row.ticker, "rank": int(row.rank), "rvol": round(float(row.rvol), 2),
                "shares": shares, "entry_t": str(bars["t"].iloc[i]), "entry": round(entry, 4),
                "exit_t": str(bars["t"].iloc[j]), "exit": round(exit_px, 4), "reason": reason,
                "stop_dist": round(stop_dist, 4), "risk": round(shares * stop_dist, 2),
                "fees": round(fee, 2), "pnl": round(pnl, 2), "r": round(pnl / (shares * stop_dist), 3),
            })
        equity += day_pnl
        curve.append({"d": str(d), "equity": round(equity, 2), "pnl": round(day_pnl, 2)})
    return summarize(p, trades, curve)


def summarize(p: Params, trades: list[dict], curve: list[dict]) -> dict:
    eq = pd.DataFrame(curve)
    tr = pd.DataFrame(trades)
    out: dict = {"params": asdict(p), "days": len(curve), "trades": len(trades)}
    if eq.empty:
        return out
    eq["ret"] = eq["equity"].pct_change().fillna(eq["pnl"] / p.start_equity)
    peak = eq["equity"].cummax()
    dd = (eq["equity"] / peak - 1.0)
    years = max((pd.to_datetime(eq["d"]).iloc[-1] - pd.to_datetime(eq["d"]).iloc[0]).days / 365.25, 1e-9)
    total = eq["equity"].iloc[-1] / p.start_equity - 1.0
    out.update({
        "end_equity": round(float(eq["equity"].iloc[-1]), 2),
        "total_return_pct": round(100 * total, 2),
        "cagr_pct": round(100 * ((1 + total) ** (1 / years) - 1), 2),
        "max_drawdown_pct": round(100 * float(dd.min()), 2),
        "sharpe": round(float(eq["ret"].mean() / eq["ret"].std() * math.sqrt(252)), 2) if eq["ret"].std() > 0 else None,
    })
    if not tr.empty:
        wins, losses = tr[tr["pnl"] > 0], tr[tr["pnl"] <= 0]
        gp, gl = wins["pnl"].sum(), -losses["pnl"].sum()
        out.update({
            "win_rate_pct": round(100 * len(wins) / len(tr), 1),
            "avg_win": round(float(wins["pnl"].mean()), 2) if len(wins) else 0.0,
            "avg_loss": round(float(losses["pnl"].mean()), 2) if len(losses) else 0.0,
            "profit_factor": round(gp / gl, 2) if gl > 0 else None,
            "expectancy_usd": round(float(tr["pnl"].mean()), 2),
            "expectancy_r": round(float(tr["r"].mean()), 3),
            "fees_total": round(float(tr["fees"].sum()), 2),
            "stopped_pct": round(100 * float((tr["reason"] == "stop").mean()), 1),
            "trades_per_day": round(len(tr) / len(curve), 2),
        })
        tr["year"] = tr["d"].str[:4]
        out["by_year"] = {
            y: {"trades": int(len(g)), "pnl": round(float(g["pnl"].sum()), 2),
                "win_rate_pct": round(100 * float((g["pnl"] > 0).mean()), 1),
                "expectancy_r": round(float(g["r"].mean()), 3)}
            for y, g in tr.groupby("year")
        }
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    (STORE_DIR / f"orb_{p.tag}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    tr.to_csv(STORE_DIR / f"orb_{p.tag}_trades.csv", index=False)
    eq.to_csv(STORE_DIR / f"orb_{p.tag}_equity.csv", index=False)
    return out


def print_report(out: dict) -> None:
    keys = ["days", "trades", "trades_per_day", "win_rate_pct", "profit_factor", "expectancy_r",
            "expectancy_usd", "avg_win", "avg_loss", "stopped_pct", "fees_total",
            "total_return_pct", "cagr_pct", "max_drawdown_pct", "sharpe", "end_equity"]
    print(f"\nORB long-only  tag={out['params']['tag']}  top={out['params']['top']}  "
          f"stop={out['params']['stop_atr']}xATR  slip=${out['params']['slippage']}")
    for k in keys:
        if k in out:
            print(f"  {k:18} {out[k]}")
    for y, g in (out.get("by_year") or {}).items():
        print(f"  {y}: trades={g['trades']} pnl={g['pnl']} win={g['win_rate_pct']}% exp={g['expectancy_r']}R")


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for f in ("top",):
        ap.add_argument(f"--{f}", type=int, default=Params.top)
    ap.add_argument("--stop-atr", type=float, default=Params.stop_atr)
    ap.add_argument("--risk-pct", type=float, default=Params.risk_pct)
    ap.add_argument("--max-position-pct", type=float, default=Params.max_position_pct)
    ap.add_argument("--slippage", type=float, default=Params.slippage)
    ap.add_argument("--commission", type=float, default=Params.commission_per_share, help="$/share each side")
    ap.add_argument("--commission-min", type=float, default=Params.commission_min)
    ap.add_argument("--min-notional", type=float, default=Params.min_notional)
    ap.add_argument("--entry-cutoff", default=Params.entry_cutoff)
    ap.add_argument("--start-equity", type=float, default=Params.start_equity)
    ap.add_argument("--from", dest="date_from")
    ap.add_argument("--to", dest="date_to")
    ap.add_argument("--tag", default="base")
    a = ap.parse_args()
    p = Params(top=a.top, stop_atr=a.stop_atr, risk_pct=a.risk_pct, max_position_pct=a.max_position_pct,
               min_notional=a.min_notional, slippage=a.slippage, commission_per_share=a.commission,
               commission_min=a.commission_min, entry_cutoff=a.entry_cutoff, start_equity=a.start_equity,
               date_from=a.date_from, date_to=a.date_to, tag=a.tag)
    t0 = time.time()
    out = run(p)
    print_report(out)
    print(f"  ({time.time() - t0:.1f}s; files under {STORE_DIR})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
