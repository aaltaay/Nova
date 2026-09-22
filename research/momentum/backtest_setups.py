"""Gate 1 harness for three minute-bar setups on the Five Pillars universe:
``pullback`` (P1: the first and second pullback), ``flat_top`` (P2: HOD / flat-top breakout)
and ``red_to_green`` (P3). Rules are the pre-registered readings recorded in
knowledge/obsidian/03-Nova-Decisions/Bot-Trading-Plan.md section 2f. Nothing here is imported
by backend/. Every free number is a Params field so the neighbourhood can be
reported.

Universe: ``gng_selection_nofloat`` (price $2-20 at 09:30, gap >= 10%, pre-market RVOL >= 5x,
at least one news article, ranked by pre-market RVOL). Bars: ``minutes_pillars`` (04:00-16:00).

Shared exit logic after any entry at bar k (entry price E, stop S, target T1):
  entry bar  the stop counts only when the bar closes at or below S (minute-bar optimism)
  target 1   half sold at T1 (limit; at the open when the bar gaps over it), stop -> E
  rest       first close below the 9 EMA, or the break-even stop, or the stop before target 1;
             ``bailout_bars`` bars without a close above E -> out at the close; flat at ``flat_by``
Costs, sizing, cash: as research/orb/backtest_orb.py (IBKR fixed commission, slippage per fill,
risk_pct of equity per trade, notional cap, cash account -- trades allocated in time order).

Usage:
    py -3 research/momentum/backtest_setups.py --tag fp_base [--ladder]
    py -3 research/momentum/backtest_setups.py --set setup=flat_top --tag ft_base [--ladder]
    py -3 research/momentum/backtest_setups.py --set setup=red_to_green --tag r2g_base [--ladder]
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import asdict, dataclass, replace
from datetime import time as dtime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "orb"))
from backtest_orb import commission, print_report, summarize  # noqa: E402
from common import DB_PATH, STORE_DIR, load_env  # noqa: E402


@dataclass
class Params:
    setup: str = "pullback"          # pullback | flat_top | red_to_green
    universe: str = "gng_selection_nofloat"
    bars_table: str = "minutes_pillars"
    session_start: str = "09:30"
    entry_cutoff: str = "11:30"
    flat_by: str = "15:55"
    # pullback (P1)
    leg_pct: float = 0.05
    leg_window: int = 10
    leg_lookback: int = 30
    require_hod: bool = True
    min_pullback_bars: int = 1
    max_pullback_bars: int = 3
    max_retrace: float = 0.5
    # flat top (P2)
    ft_impulse_pct: float = 0.03
    ft_min_consol: int = 2
    ft_max_consol: int = 6
    ft_band: float = 0.02
    ft_entry: str = "hold"           # hold | break
    ft_hold_bars: int = 3
    # red to green (P3)
    r2g_min_red_bars: int = 1
    r2g_cutoff: str = "10:30"
    r2g_target_hod: bool = True
    # shared
    ema_period: int = 9
    ema_tol: float = 0.0
    macd_positive: bool = True
    stop_cap: float = 0.20
    min_stop: float = 0.03
    target_r: float = 2.0
    bailout_bars: int = 5
    max_trades_per_symbol_day: int = 2
    gap_rank_max: int | None = None
    risk_pct: float = 0.01
    max_position_pct: float = 0.25
    min_notional: float = 500.0
    slippage: float = 0.01
    commission_per_share: float = 0.005
    commission_min: float = 1.0
    commission_max_pct: float = 0.01
    start_equity: float = 25_000.0
    top: int = 20  # unused; keeps summarize() happy
    stop_atr: float = 0.0
    date_from: str | None = None
    date_to: str | None = None
    tag: str = "fp_base"


def ema(x: np.ndarray, n: int) -> np.ndarray:
    out = np.empty_like(x, dtype=float)
    a = 2.0 / (n + 1)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def macd_hist(c: np.ndarray) -> np.ndarray:
    m = ema(c, 12) - ema(c, 26)
    return m - ema(m, 9)


def _t(s: str) -> dtime:
    return dtime(*map(int, s.split(":")))


class Day:
    """One symbol-day's arrays and indicators."""

    def __init__(self, bars: pd.DataFrame, p: Params):
        self.t = bars["t"].to_numpy()
        self.o, self.h, self.l, self.c = (bars[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
        self.n = len(self.c)
        self.e9 = ema(self.c, p.ema_period)
        self.hist = macd_hist(self.c)
        self.p = p
        self.flat = _t(p.flat_by)

    def simulate(self, k: int, entry: float, stop: float, t1: float, half_on_entry_bar: bool = True):
        """Shared exit logic from bar k. Returns (half_px, half_t, exit_px, exit_t, reason, j)."""
        p, t, o, h, l, c, e9, n = self.p, self.t, self.o, self.h, self.l, self.c, self.e9, self.n
        half_done, half_px, half_t = False, None, None
        exit_px, exit_t, reason = None, None, None
        if c[k] <= stop:
            exit_px, exit_t, reason = stop - p.slippage, t[k], "stop_entry_bar"
        elif half_on_entry_bar and h[k] >= t1 and t1 > entry:
            half_done, half_px, half_t = True, t1 - p.slippage, t[k]
            stop = entry
        j = k + 1
        while exit_px is None and j < n:
            if t[j] >= self.flat:
                exit_px, exit_t, reason = c[j] - p.slippage, t[j], "close"
                break
            if l[j] <= stop:
                exit_px, exit_t, reason = min(o[j], stop) - p.slippage, t[j], ("breakeven" if half_done else "stop")
                break
            if not half_done and h[j] >= t1:
                half_done, half_px, half_t = True, (max(o[j], t1) - p.slippage), t[j]
                stop = entry
            elif half_done and c[j] < e9[j]:
                exit_px, exit_t, reason = c[j] - p.slippage, t[j], "ema"
                break
            elif not half_done and j - k >= p.bailout_bars and c[j] <= entry:
                exit_px, exit_t, reason = c[j] - p.slippage, t[j], "bailout"
                break
            j += 1
        if exit_px is None:
            j = n - 1
            exit_px, exit_t, reason = c[j] - p.slippage, t[j], "close"
        return half_px, half_t, exit_px, exit_t, reason, j

    def record(self, k: int, entry: float, stop0: float, t1: float, sim, extra: dict, nth: int) -> dict:
        half_px, half_t, exit_px, exit_t, reason, j = sim
        risk = entry - stop0
        row = {"entry_t": str(self.t[k]), "entry": round(entry, 4), "stop0": round(stop0, 4), "risk": round(risk, 4),
               "t1": round(t1, 4), "half_px": round(half_px, 4) if half_px else None, "half_t": str(half_t) if half_t else None,
               "exit_t": str(exit_t), "exit": round(exit_px, 4), "reason": reason, "nth": nth, "_k": k, "_j": j}
        row.update(extra)
        return row


def find_pullback(day: Day, p: Params) -> list[dict]:
    t, o, h, l, c, e9, hist, n = day.t, day.o, day.h, day.l, day.c, day.e9, day.hist, day.n
    ss, cut = _t(p.session_start), _t(p.entry_cutoff)
    trades: list[dict] = []
    k = 1
    while k < n and t[k] < ss:
        k += 1
    while k < n and t[k] < cut and len(trades) < p.max_trades_per_symbol_day:
        found = None
        for m in range(p.min_pullback_bars, p.max_pullback_bars + 1):
            H = k - 1 - m
            if H < p.leg_lookback:
                continue
            leg_high = h[H]
            if leg_high < h[H - p.leg_lookback:H].max():
                continue
            if p.require_hod and leg_high < h[:H].max():
                continue
            leg_low = l[max(0, H - p.leg_window + 1):H + 1].min()
            if leg_low <= 0 or leg_high / leg_low - 1 < p.leg_pct:
                continue
            pb = slice(H + 1, k)
            if h[pb].max() > leg_high:
                continue
            pb_low = l[pb].min()
            if (leg_high - pb_low) / max(leg_high - leg_low, 1e-9) >= p.max_retrace:
                continue
            if (c[pb] < e9[pb] * (1 - p.ema_tol)).any():
                continue
            found = (H, m, leg_high, leg_low, pb_low)
            break
        if found is None:
            k += 1
            continue
        H, m, leg_high, leg_low, pb_low = found
        trig = h[k - 1]
        if h[k] <= trig or (p.macd_positive and hist[k - 1] <= 0):
            k += 1
            continue
        entry = max(o[k], trig + 0.01) + p.slippage
        risk = entry - pb_low
        if risk > p.stop_cap or risk < p.min_stop:
            k += 1
            continue
        t1 = max(leg_high, entry + p.target_r * risk)
        sim = day.simulate(k, entry, pb_low, t1)
        trades.append(day.record(k, entry, pb_low, t1, sim,
                                 {"leg_pct": round(leg_high / leg_low - 1, 4), "pullback_bars": m, "level": round(leg_high, 4)},
                                 len(trades) + 1))
        k = sim[5] + 1
    return trades


def find_flat_top(day: Day, p: Params) -> list[dict]:
    t, o, h, l, c, e9, hist, n = day.t, day.o, day.h, day.l, day.c, day.e9, day.hist, day.n
    ss, cut = _t(p.session_start), _t(p.entry_cutoff)
    trades: list[dict] = []
    k = 1
    while k < n and t[k] < ss:
        k += 1
    while k < n and t[k] < cut and len(trades) < p.max_trades_per_symbol_day:
        L = h[:k].max()
        if h[k] <= L or (p.macd_positive and hist[k - 1] <= 0):
            k += 1
            continue
        found = None
        for m in range(p.ft_min_consol, p.ft_max_consol + 1):
            cs = slice(k - m, k)          # consolidation bars
            H = k - m - 1                 # impulse high bar
            if H < p.leg_window:
                continue
            if h[H] != L:
                continue
            if h[cs].max() > L or (c[cs] < L * (1 - p.ft_band)).any() or (l[cs] < e9[cs] * (1 - p.ema_tol)).any():
                continue
            imp_low = l[max(0, H - p.leg_window + 1):H + 1].min()
            if imp_low <= 0 or L / imp_low - 1 < p.ft_impulse_pct:
                continue
            found = (m, l[cs].min(), L / imp_low - 1)
            break
        if found is None:
            k += 1
            continue
        m, cons_low, imp_pct = found
        if p.ft_entry == "break":
            entry = max(o[k], L + 0.01) + p.slippage
            stop0, ek = cons_low, k
        else:
            ek = None
            for j in range(k + 1, min(n, k + 1 + p.ft_hold_bars)):
                if c[j] < L:
                    break
                if l[j] >= L and c[j] > o[j]:
                    ek = j
                    break
            if ek is None:
                k += 1
                continue
            entry = c[ek] + p.slippage
            stop0 = l[ek]
        risk = entry - stop0
        if risk > p.stop_cap or risk < p.min_stop:
            k = ek + 1
            continue
        t1 = entry + p.target_r * risk
        sim = day.simulate(ek, entry, stop0, t1, half_on_entry_bar=(p.ft_entry == "break"))
        trades.append(day.record(ek, entry, stop0, t1, sim,
                                 {"consol_bars": m, "impulse_pct": round(imp_pct, 4), "level": round(L, 4), "ft_entry": p.ft_entry},
                                 len(trades) + 1))
        k = sim[5] + 1
    return trades


def find_red_to_green(day: Day, p: Params) -> list[dict]:
    t, o, h, l, c, hist, n = day.t, day.o, day.h, day.l, day.c, day.hist, day.n
    ss, cut = _t(p.session_start), _t(p.r2g_cutoff)
    k0 = 0
    while k0 < n and t[k0] < ss:
        k0 += 1
    if k0 >= n:
        return []
    open_px = o[k0]
    red = 0
    for k in range(k0 + 1, n):
        if t[k] >= cut:
            break
        if c[k - 1] < open_px:
            red += 1
        if red < p.r2g_min_red_bars or c[k - 1] >= open_px:
            continue
        if h[k] <= open_px or (p.macd_positive and hist[k - 1] <= 0):
            continue
        entry = max(o[k], open_px + 0.01) + p.slippage
        stop0 = l[k0:k].min()
        risk = entry - stop0
        if risk > p.stop_cap or risk < p.min_stop:
            return []
        t1 = entry + p.target_r * risk
        if p.r2g_target_hod:
            t1 = max(h[:k].max(), t1)
        sim = day.simulate(k, entry, stop0, t1)
        return [day.record(k, entry, stop0, t1, sim, {"open_px": round(open_px, 4), "red_bars": red, "level": round(open_px, 4)}, 1)]
    return []


FINDERS = {"pullback": find_pullback, "flat_top": find_flat_top, "red_to_green": find_red_to_green}


def run(p: Params) -> dict:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    where = ["1=1"]
    if p.date_from:
        where.append(f"d >= DATE '{p.date_from}'")
    if p.date_to:
        where.append(f"d <= DATE '{p.date_to}'")
    base = (f"SELECT ticker, d, prev_close, pm_high, gap, rvol_pm, rank, "
            f"row_number() OVER (PARTITION BY d ORDER BY gap DESC) AS gap_rank FROM {p.universe} WHERE {' AND '.join(where)}")
    sel = con.execute(f"SELECT * FROM ({base}) WHERE gap_rank <= {p.gap_rank_max or 10_000} ORDER BY d, rank").df()
    finder = FINDERS[p.setup]
    days = sorted(sel["d"].unique())
    equity, curve, trades_out = p.start_equity, [], []
    for d in days:
        todays = sel[sel["d"] == d]
        bars_all = con.execute(
            f"SELECT ticker, t, open, high, low, close, volume FROM {p.bars_table} WHERE d = ? AND ticker IN "
            f"(SELECT ticker FROM {p.universe} WHERE d = ?) ORDER BY ticker, t", [d, d]).df()
        if bars_all.empty:
            continue
        cands: list[dict] = []
        for row in todays.itertuples(index=False):
            b = bars_all[bars_all["ticker"] == row.ticker]
            if len(b) < 40:
                continue
            day = Day(b.reset_index(drop=True), p)
            for tr in finder(day, p):
                tr.update({"d": str(d), "ticker": row.ticker, "rank": int(row.rank), "gap_rank": int(row.gap_rank),
                           "gap": round(float(row.gap), 4), "rvol_pm": round(float(row.rvol_pm), 1),
                           "prev_close": float(row.prev_close)})
                cands.append(tr)
        cands.sort(key=lambda x: x["entry_t"])
        cash, day_pnl, open_pos = equity, 0.0, []
        for tr in cands:
            still = []
            for xt, cb in open_pos:
                if xt <= tr["entry_t"]:
                    cash += cb
                else:
                    still.append((xt, cb))
            open_pos = still
            shares = int(min(p.risk_pct * equity / tr["risk"], p.max_position_pct * equity / tr["entry"], cash / tr["entry"]))
            if shares < 1 or shares * tr["entry"] < p.min_notional:
                continue
            half = shares // 2 if tr["half_px"] else 0
            rest = shares - half
            fee = commission(shares, shares * tr["entry"], p)
            pnl = 0.0
            if half:
                pnl += half * (tr["half_px"] - tr["entry"])
                fee += commission(half, half * tr["half_px"], p)
            pnl += rest * (tr["exit"] - tr["entry"])
            fee += commission(rest, rest * tr["exit"], p)
            pnl -= fee
            cash -= shares * tr["entry"]
            open_pos.append((tr["exit_t"], shares * tr["entry"] + pnl))
            day_pnl += pnl
            out = {k: v for k, v in tr.items() if not k.startswith("_")}
            out.update({"shares": shares, "fees": round(fee, 2), "pnl": round(pnl, 2), "r": round(pnl / (shares * tr["risk"]), 3)})
            trades_out.append(out)
        equity += day_pnl
        curve.append({"d": str(d), "equity": round(equity, 2), "pnl": round(day_pnl, 2)})
    con.close()
    out = summarize(p, trades_out, curve)
    out["params"] = asdict(p)
    if trades_out:
        pd.DataFrame(trades_out).to_csv(STORE_DIR / f"orb_{p.tag}_trades.csv", index=False)
    pd.DataFrame(curve).to_csv(STORE_DIR / f"orb_{p.tag}_equity.csv", index=False)
    return out


def buckets(tag: str) -> None:
    f = STORE_DIR / f"orb_{tag}_trades.csv"
    if not f.exists():
        return
    tr = pd.read_csv(f)
    tr["price_bucket"] = pd.cut(tr["entry"], [0, 5, 10, 1e9], labels=["$2-5", "$5-10", "$10+"])
    tr["hour"] = tr["entry_t"].str[:2]
    tr["gap_rank_b"] = pd.cut(tr["gap_rank"], [0, 3, 100], labels=["top3", "4+"])
    cols = [c for c in ("nth", "reason", "price_bucket", "gap_rank_b", "pullback_bars", "consol_bars", "red_bars", "hour") if c in tr.columns]
    for col in cols:
        g = tr.groupby(col, observed=True).agg(trades=("pnl", "size"), win_pct=("pnl", lambda s: round(100 * (s > 0).mean(), 1)),
                                                exp_R=("r", "mean"), pnl=("pnl", "sum")).round(3)
        print(f"\n== by {col} ({tag}) ==\n{g.to_string()}")
    top10 = tr.nlargest(10, "pnl")["pnl"].sum(); tot = tr["pnl"].sum()
    print(f"\nconcentration ({tag}): total {tot:.0f}, top10 {100 * top10 / tot if tot else 0:.0f}%, ex-top10 {tot - top10:.0f}")


LADDERS = {
    "pullback": [
        ("slip0", dict(slippage=0.0)), ("slip0.02", dict(slippage=0.02)), ("slip0.03", dict(slippage=0.03)),
        ("2xcosts", dict(slippage=0.02, commission_per_share=0.01)),
        ("stopcap0.30", dict(stop_cap=0.30)), ("stopcap0.10", dict(stop_cap=0.10)),
        ("leg3", dict(leg_pct=0.03)), ("leg8", dict(leg_pct=0.08)),
        ("pb5", dict(max_pullback_bars=5)), ("pb2", dict(max_pullback_bars=2)),
        ("nomacd", dict(macd_positive=False)), ("anyhigh", dict(require_hod=False)),
        ("top3gap", dict(gap_rank_max=3)), ("open30", dict(entry_cutoff="10:00")),
        ("first_only", dict(max_trades_per_symbol_day=1)), ("target1r", dict(target_r=1.0)),
        ("bailout2", dict(bailout_bars=2)), ("cutoff1030", dict(entry_cutoff="10:30")),
        ("papercosts", dict(slippage=0.0, commission_per_share=0.0035, commission_min=0.0)),
    ],
    "flat_top": [
        ("slip0", dict(slippage=0.0)), ("slip0.02", dict(slippage=0.02)),
        ("2xcosts", dict(slippage=0.02, commission_per_share=0.01)),
        ("break", dict(ft_entry="break")), ("impulse5", dict(ft_impulse_pct=0.05)), ("band1", dict(ft_band=0.01)),
        ("stopcap0.30", dict(stop_cap=0.30)), ("nomacd", dict(macd_positive=False)),
        ("top3gap", dict(gap_rank_max=3)), ("open30", dict(entry_cutoff="10:00")),
        ("target1r", dict(target_r=1.0)), ("bailout2", dict(bailout_bars=2)),
        ("papercosts", dict(slippage=0.0, commission_per_share=0.0035, commission_min=0.0)),
    ],
    "red_to_green": [
        ("slip0", dict(slippage=0.0)), ("slip0.02", dict(slippage=0.02)),
        ("2xcosts", dict(slippage=0.02, commission_per_share=0.01)),
        ("red2", dict(r2g_min_red_bars=2)), ("cutoff1130", dict(r2g_cutoff="11:30")),
        ("stopcap0.10", dict(stop_cap=0.10)), ("stopcap0.30", dict(stop_cap=0.30)),
        ("nomacd", dict(macd_positive=False)), ("target2r", dict(r2g_target_hod=False)),
        ("top3gap", dict(gap_rank_max=3)), ("target1r", dict(target_r=1.0, r2g_target_hod=False)),
        ("bailout2", dict(bailout_bars=2)),
        ("papercosts", dict(slippage=0.0, commission_per_share=0.0035, commission_min=0.0)),
    ],
}


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="fp_base")
    ap.add_argument("--ladder", action="store_true")
    ap.add_argument("--date-from"); ap.add_argument("--date-to")
    ap.add_argument("--set", nargs="*", default=[], help="field=value overrides (setup=flat_top ...)")
    a = ap.parse_args()
    p = Params(tag=a.tag, date_from=a.date_from, date_to=a.date_to)
    for kv in a.set:
        k, v = kv.split("=", 1)
        cur = getattr(p, k)
        if isinstance(cur, bool):
            val = v.lower() in ("1", "true", "yes")
        elif cur is None:
            val = int(v)
        else:
            val = type(cur)(v)
        p = replace(p, **{k: val})
    t0 = time.time()
    out = run(p)
    print_report(out)
    buckets(p.tag)
    if a.ladder:
        rows = []
        for name, kw in LADDERS[p.setup]:
            o = run(replace(p, tag=f"{p.tag}_{name}", **kw))
            rows.append({"run": name, "trades": o.get("trades"), "win%": o.get("win_rate_pct"), "PF": o.get("profit_factor"),
                         "exp_R": o.get("expectancy_r"), "CAGR%": o.get("cagr_pct"), "maxDD%": o.get("max_drawdown_pct"),
                         "sharpe": o.get("sharpe")})
            print(f"  {name}: trades={o.get('trades')} PF={o.get('profit_factor')} expR={o.get('expectancy_r')} CAGR={o.get('cagr_pct')}", flush=True)
        df = pd.DataFrame(rows)
        print("\n== ladder ==\n" + df.to_string(index=False))
        (STORE_DIR / f"robustness_{p.tag}.json").write_text(df.to_json(orient="records", indent=2), encoding="utf-8")
    print(f"  ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
