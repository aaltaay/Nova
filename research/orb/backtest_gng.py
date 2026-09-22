"""Gap and Go, long-only, mechanical -- honest simulation (rules pre-registered 2026-09-22).

Candidates come from ``gng_selection`` (select_gng.py: the Five Pillars at 09:30, ranked
by pre-market relative volume). Per candidate, in rank order while cash lasts:
  entry     buy stop at the pre-market high, live from 09:30 until ``entry_end`` (10:00);
            only when the 09:30 open is below that high (a gap through it is skipped)
  stop      ``min(stop_cents, stop_pct x entry)`` below the fill ($0.20 or 4%)
  target 1  at ``t1_r`` x the stop distance: sell half, move the stop to the entry price
  target 2  at ``t2_r`` x the stop distance: sell the rest
  time stop ``time_stop`` (11:30): whatever is left goes at that bar's close; EOD fallback
Fills as in backtest_orb.py: entry at max(open, level) + slippage; a stop on the entry bar
counts only if the bar closes at or below it, later stops fill at min(open, stop) -
slippage; a target on the entry bar counts only if the bar closes at or above it, later
targets fill at the target (or the open when the bar gaps above); when a bar reaches both
the stop and a target the stop is taken. IBKR fixed commission per leg, cash reserved at
placement, no margin, no shorts.

Usage:
    py -3 research/orb/backtest_gng.py --tag gng_base
    py -3 research/orb/backtest_gng.py --grid --tag gng      # neighbourhood + costs + variants
"""
from __future__ import annotations

import argparse
import time
from dataclasses import asdict, dataclass, replace
from datetime import time as dtime

import numpy as np
import pandas as pd

from backtest_orb import commission, print_report, summarize
from common import STORE_DIR, connect, load_env


@dataclass
class GParams:
    selection: str = "gng_selection"
    minutes: str = "minutes_gng"
    top: int = 10
    entry_end: str = "10:00"
    stop_cents: float = 0.20
    stop_pct: float = 0.04
    t1_r: float = 2.0
    t2_r: float = 4.0
    time_stop: str = "11:30"
    risk_pct: float = 0.01
    max_position_pct: float = 0.25
    min_notional: float = 500.0
    slippage: float = 0.01
    commission_per_share: float = 0.005
    commission_min: float = 1.0
    commission_max_pct: float = 0.01
    start_equity: float = 25_000.0
    tag: str = "gng_base"


def _t(s: str) -> dtime:
    return dtime(*(int(x) for x in s.split(":")))


def simulate(bars: pd.DataFrame, level: float, shares: int, p: GParams) -> list[tuple[int, int, float, str]] | None:
    """Return exit legs [(bar_i, qty, price, reason)] plus an entry leg first, or None if no fill."""
    t = bars["t"].to_numpy()
    o = bars["open"].to_numpy(dtype=float)
    h = bars["high"].to_numpy(dtype=float)
    lo = bars["low"].to_numpy(dtype=float)
    c = bars["close"].to_numpy(dtype=float)
    end, tstop = _t(p.entry_end), _t(p.time_stop)
    hit = np.flatnonzero(np.array([tt < end for tt in t]) & (h >= level))
    if hit.size == 0:
        return None
    i = int(hit[0])
    entry = max(o[i], level) + p.slippage
    stop_dist = min(p.stop_cents, p.stop_pct * entry)
    stop, t1, t2 = entry - stop_dist, entry + p.t1_r * stop_dist, entry + p.t2_r * stop_dist
    half = shares // 2 if shares >= 2 else 0
    legs: list[tuple[int, int, float, str]] = [(i, shares, entry, "entry")]
    qty, t1_done = shares, False
    # entry bar: close-based, pessimistic
    if c[i] <= stop:
        legs.append((i, qty, stop - p.slippage, "stop"))
        return legs
    if half and c[i] >= t1:
        legs.append((i, half, t1, "t1"))
        qty, t1_done, stop = qty - half, True, entry
    for j in range(i + 1, len(bars)):
        if lo[j] <= stop:
            legs.append((j, qty, min(o[j], stop) - p.slippage, "stop" if not t1_done else "be_stop"))
            return legs
        if not t1_done and half and h[j] >= t1:
            legs.append((j, half, max(o[j], t1), "t1"))
            qty, t1_done, stop = qty - half, True, entry
            continue
        if (t1_done or not half) and h[j] >= t2:
            legs.append((j, qty, max(o[j], t2), "t2"))
            return legs
        if t[j] >= tstop:
            legs.append((j, qty, c[j] - p.slippage, "time"))
            return legs
    legs.append((len(bars) - 1, qty, c[-1] - p.slippage, "eod"))
    return legs


def run(p: GParams) -> dict:
    con = connect(read_only=True)
    sel = con.execute(
        f"SELECT ticker, d, rank, rvol_pm, gap, pm_high, o5_open, float_shares, news_n FROM {p.selection} "
        f"WHERE rank <= ? AND o5_open < pm_high ORDER BY d, rank", [p.top]
    ).df()
    mins = con.execute(
        f"SELECT m.ticker, m.d, m.t, m.open, m.high, m.low, m.close, m.volume FROM {p.minutes} m "
        f"JOIN (SELECT DISTINCT ticker, d FROM {p.selection} WHERE rank <= ?) s USING (ticker, d) "
        f"WHERE m.t >= TIME '09:30' ORDER BY m.d, m.ticker, m.t", [p.top]
    ).df()
    con.close()
    groups = {k: g for k, g in mins.groupby(["ticker", "d"], sort=False)}
    equity, trades, curve = p.start_equity, [], []
    for d in sorted(sel["d"].unique()):
        cash, day_pnl = equity, 0.0
        for row in sel[sel["d"] == d].itertuples(index=False):
            level = float(row.pm_high)
            est_entry = level + p.slippage
            stop_dist = min(p.stop_cents, p.stop_pct * est_entry)
            shares = int(min(p.risk_pct * equity / stop_dist, p.max_position_pct * equity / level, cash / level))
            if shares < 1 or shares * level < p.min_notional:
                continue
            cash -= shares * level
            bars = groups.get((row.ticker, d))
            if bars is None or len(bars) < 6:
                continue
            legs = simulate(bars, level, shares, p)
            if legs is None:
                continue
            (ei, eq_, entry, _), exits = legs[0], legs[1:]
            fees = commission(eq_, eq_ * entry, p) + sum(commission(q, q * px, p) for _, q, px, _ in exits)
            pnl = sum(q * (px - entry) for _, q, px, _ in exits) - fees
            risk = shares * min(p.stop_cents, p.stop_pct * entry)
            day_pnl += pnl
            trades.append({
                "d": str(d), "ticker": row.ticker, "rank": int(row.rank), "rvol": round(float(row.rvol_pm), 2),
                "gap_pct": round(100 * float(row.gap), 1), "shares": shares,
                "entry_t": str(bars["t"].iloc[ei]), "entry": round(entry, 4),
                "exit_t": str(bars["t"].iloc[exits[-1][0]]), "exit": round(exits[-1][2], 4),
                "reason": "+".join(x[3] for x in exits), "stop_dist": round(risk / shares, 4),
                "risk": round(risk, 2), "fees": round(fees, 2), "pnl": round(pnl, 2), "r": round(pnl / risk, 3),
            })
        equity += day_pnl
        curve.append({"d": str(d), "equity": round(equity, 2), "pnl": round(day_pnl, 2)})
    out = summarize(_as_params(p), trades, curve)
    out["params"] = asdict(p)
    out["candidates"] = int(len(sel))
    (STORE_DIR / f"orb_{p.tag}.json").write_text(pd.Series(out).to_json(indent=2), encoding="utf-8")
    return out


def _as_params(p: GParams):
    """summarize() reads start_equity and tag from a Params-like object."""
    from backtest_orb import Params

    return Params(start_equity=p.start_equity, tag=p.tag, slippage=p.slippage,
                  commission_per_share=p.commission_per_share, commission_min=p.commission_min)


def grid(base: GParams) -> pd.DataFrame:
    rows = []

    def add(name: str, q: GParams) -> None:
        o = run(replace(q, tag=f"{base.tag}_{name}"))
        rows.append({"run": name, "cands": o.get("candidates"), "trades": o.get("trades"), "win%": o.get("win_rate_pct"),
                     "PF": o.get("profit_factor"), "exp_R": o.get("expectancy_r"), "exp_$": o.get("expectancy_usd"),
                     "CAGR%": o.get("cagr_pct"), "maxDD%": o.get("max_drawdown_pct"), "sharpe": o.get("sharpe")})
        print(pd.DataFrame(rows[-1:]).to_string(index=False, header=len(rows) == 1), flush=True)

    add("base", base)
    for sc in (0.10, 0.30):
        add(f"stop{sc}", replace(base, stop_cents=sc))
    for t1 in (1.5, 3.0):
        add(f"t1_{t1}", replace(base, t1_r=t1, t2_r=2 * t1))
    add("no_t2_eod", replace(base, t2_r=99.0, time_stop="15:59"))
    add("entry_1030", replace(base, entry_end="10:30"))
    add("top5", replace(base, top=5))
    add("top20", replace(base, top=20))
    for slip in (0.0, 0.02, 0.03):
        add(f"slip{slip}", replace(base, slippage=slip))
    add("2xcosts", replace(base, slippage=0.02, commission_per_share=0.01))
    add("no_float_pillar", replace(base, selection="gng_selection_nofloat"))  # minutes_gng covers both selections
    return pd.DataFrame(rows)


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="gng_base")
    ap.add_argument("--top", type=int, default=GParams.top)
    ap.add_argument("--selection", default=GParams.selection)
    ap.add_argument("--minutes", default=GParams.minutes)
    ap.add_argument("--slippage", type=float, default=GParams.slippage)
    ap.add_argument("--grid", action="store_true")
    a = ap.parse_args()
    p = GParams(tag=a.tag, top=a.top, selection=a.selection, minutes=a.minutes, slippage=a.slippage)
    t0 = time.time()
    if a.grid:
        table = grid(p)
        print("\n== summary ==\n" + table.to_string(index=False))
        (STORE_DIR / f"robustness_{p.tag}.json").write_text(table.to_json(orient="records", indent=2), encoding="utf-8")
    else:
        print_report(run(p))
    print(f"  ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
