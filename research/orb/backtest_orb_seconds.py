"""S1 -- the ORB entry window replayed on one-second bars (Bot-Trading-Plan §2e; verdict: not passed).

Same published rule and the same ``selection`` as backtest_orb.py, but 09:30-11:00 ET
is replayed from ``store/seconds.duckdb``: the fill is the first second at or after 09:35
whose high reaches the 5-minute high (at max(open, level) + slippage), the stop is checked
every second after it (entry second: only if it closes at or below the stop; later
seconds: the first low at or below the stop, at min(open, stop) - slippage). After 11:00
the position rides the 1-minute bars in ``minutes_selected`` to the stop or the close.
Sizing, costs, cash reservation: as backtest_orb.py. Nothing reads ahead of its own bar.

Pre-planned splits (reported from the trade list, never re-selected): rank 1-5 vs 6-10,
entry price $2-10 vs $10+, and the cost ladder.

Usage:
    py -3 research/orb/backtest_orb_seconds.py --top 10 --tag s1
    py -3 research/orb/backtest_orb_seconds.py --top 10 --tag s1 --ladder
"""
from __future__ import annotations

import argparse
import time
from dataclasses import asdict, replace
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import pandas as pd

from backtest_orb import Params, commission, print_report, summarize
from common import DB_PATH, STORE_DIR, load_env

ET = ZoneInfo("America/New_York")
SECONDS_DB = STORE_DIR / "seconds.duckdb"
SECONDS_END = dtime(11, 0)


def _connect():
    con = duckdb.connect(str(SECONDS_DB), read_only=True)
    con.execute(f"ATTACH '{DB_PATH.as_posix()}' AS orb (READ_ONLY)")
    return con


def simulate(sec: pd.DataFrame, mins: pd.DataFrame, level: float, stop_dist: float, cutoff: dtime, p: Params):
    """Seconds for the entry window, minutes after 11:00. Returns (entry_t, entry, exit_t, exit_px, reason) or None."""
    st = sec["t"].to_numpy()
    so, sh, sl, sc = (sec[c].to_numpy(dtype=float) for c in ("open", "high", "low", "close"))
    after = np.array([tt >= dtime(9, 35) and tt < cutoff for tt in st])
    hit = np.flatnonzero(after & (sh >= level))
    if hit.size == 0:
        return None
    i = int(hit[0])
    entry = max(so[i], level) + p.slippage
    stop = entry - stop_dist
    if sc[i] <= stop:
        return st[i], entry, st[i], stop - p.slippage, "stop_entry_sec"
    stopped = np.flatnonzero(sl[i + 1:] <= stop)
    if stopped.size:
        j = i + 1 + int(stopped[0])
        return st[i], entry, st[j], min(so[j], stop) - p.slippage, "stop_sec"
    # ride the minute bars from 11:00 on
    if mins is None or len(mins) == 0:
        last = sec.iloc[-1]
        return st[i], entry, last["t"], float(last["close"]) - p.slippage, "close_sec_end"
    mt = mins["t"].to_numpy()
    mo, ml, mc = (mins[c].to_numpy(dtype=float) for c in ("open", "low", "close"))
    stopped = np.flatnonzero(ml <= stop)
    if stopped.size:
        j = int(stopped[0])
        return st[i], entry, mt[j], min(mo[j], stop) - p.slippage, "stop_min"
    return st[i], entry, mt[-1], mc[-1] - p.slippage, "close"


def run(p: Params) -> dict:
    con = _connect()
    sel = con.execute(
        "SELECT ticker, d, rank, rvol, o5_high, atr14, o5_open FROM orb.selection "
        "WHERE rank <= ? AND direction = 'long' ORDER BY d, rank", [p.top]
    ).df()
    days = sorted(sel["d"].unique())
    cutoff = dtime(*(int(x) for x in p.entry_cutoff.split(":")))
    equity, trades, curve = p.start_equity, [], []
    for d in days:
        todays = sel[sel["d"] == d]
        syms = list(todays["ticker"])
        sec_all = con.execute(
            "SELECT ticker, (to_timestamp(t_ms / 1000.0) AT TIME ZONE 'America/New_York')::TIME AS t, "
            "open, high, low, close FROM seconds_selected WHERE d = ? AND ticker IN "
            "(SELECT ticker FROM orb.selection WHERE d = ? AND rank <= ? AND direction = 'long') ORDER BY ticker, t_ms",
            [d, d, p.top],
        ).df()
        min_all = con.execute(
            "SELECT ticker, t, open, high, low, close FROM orb.minutes_selected WHERE d = ? AND t >= TIME '11:00' "
            "AND ticker IN (SELECT ticker FROM orb.selection WHERE d = ? AND rank <= ? AND direction = 'long') "
            "ORDER BY ticker, t", [d, d, p.top],
        ).df()
        sec_by = {k: g for k, g in sec_all.groupby("ticker", sort=False)} if not sec_all.empty else {}
        min_by = {k: g for k, g in min_all.groupby("ticker", sort=False)} if not min_all.empty else {}
        cash, day_pnl = equity, 0.0
        for row in todays.itertuples(index=False):
            stop_dist = p.stop_atr * float(row.atr14)
            level = float(row.o5_high)
            if not (stop_dist > 0) or not (level > 0):
                continue
            shares = int(min(p.risk_pct * equity / stop_dist, p.max_position_pct * equity / level, cash / level))
            if shares < 1 or shares * level < p.min_notional:
                continue
            cash -= shares * level
            sec = sec_by.get(row.ticker)
            if sec is None or len(sec) < 5:
                continue
            res = simulate(sec, min_by.get(row.ticker), level, stop_dist, cutoff, p)
            if res is None:
                continue
            et, entry, xt, exit_px, reason = res
            fee = commission(shares, shares * entry, p) + commission(shares, shares * exit_px, p)
            pnl = shares * (exit_px - entry) - fee
            day_pnl += pnl
            trades.append({
                "d": str(d), "ticker": row.ticker, "rank": int(row.rank), "rvol": round(float(row.rvol), 2),
                "shares": shares, "entry_t": str(et), "entry": round(entry, 4), "exit_t": str(xt),
                "exit": round(exit_px, 4), "reason": reason, "stop_dist": round(stop_dist, 4),
                "risk": round(shares * stop_dist, 2), "fees": round(fee, 2), "pnl": round(pnl, 2),
                "r": round(pnl / (shares * stop_dist), 3),
            })
        equity += day_pnl
        curve.append({"d": str(d), "equity": round(equity, 2), "pnl": round(day_pnl, 2)})
    con.close()
    out = summarize(p, trades, curve)
    out["params"] = asdict(p)
    return out


def buckets(tag: str) -> None:
    tr = pd.read_csv(STORE_DIR / f"orb_{tag}_trades.csv")
    if tr.empty:
        return
    tr["rank_bucket"] = pd.cut(tr["rank"], [0, 5, 10, 30], labels=["1-5", "6-10", "11+"])
    tr["price_bucket"] = pd.cut(tr["entry"], [0, 10, 1e9], labels=["$2-10", "$10+"])
    for col in ("rank_bucket", "price_bucket", "reason"):
        g = tr.groupby(col, observed=True).agg(trades=("pnl", "size"), win_pct=("pnl", lambda s: round(100 * (s > 0).mean(), 1)),
                                                exp_R=("r", "mean"), pnl=("pnl", "sum")).round(3)
        print(f"\n== by {col} ({tag}) ==\n{g.to_string()}")
    top10 = tr.nlargest(10, "pnl")["pnl"].sum(); tot = tr["pnl"].sum()
    print(f"\nconcentration ({tag}): total {tot:.0f}, top10 {100 * top10 / tot if tot else 0:.0f}%, ex-top10 {tot - top10:.0f}")


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--stop-atr", type=float, default=Params.stop_atr)
    ap.add_argument("--slippage", type=float, default=Params.slippage)
    ap.add_argument("--tag", default="s1")
    ap.add_argument("--ladder", action="store_true", help="cost ladder + 2x costs + stop 0.05")
    a = ap.parse_args()
    base = Params(top=a.top, stop_atr=a.stop_atr, slippage=a.slippage, tag=a.tag)
    t0 = time.time()
    out = run(base)
    print_report(out)
    buckets(base.tag)
    if a.ladder:
        rows = []
        for name, q in [("slip0", replace(base, slippage=0.0)), ("slip0.02", replace(base, slippage=0.02)),
                        ("slip0.03", replace(base, slippage=0.03)),
                        ("2xcosts", replace(base, slippage=0.02, commission_per_share=0.01)),
                        ("stop0.05", replace(base, stop_atr=0.05)), ("top5", replace(base, top=5)),
                        ("papercosts", replace(base, slippage=0.0, commission_per_share=0.0035, commission_min=0.0))]:
            o = run(replace(q, tag=f"{base.tag}_{name}"))
            rows.append({"run": name, "trades": o.get("trades"), "win%": o.get("win_rate_pct"), "PF": o.get("profit_factor"),
                         "exp_R": o.get("expectancy_r"), "CAGR%": o.get("cagr_pct"), "maxDD%": o.get("max_drawdown_pct"),
                         "sharpe": o.get("sharpe")})
        print("\n== ladder ==\n" + pd.DataFrame(rows).to_string(index=False))
        (STORE_DIR / f"robustness_{base.tag}.json").write_text(pd.DataFrame(rows).to_json(orient="records", indent=2), encoding="utf-8")
    print(f"  ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
