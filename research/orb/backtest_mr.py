"""A4: large-cap daily mean reversion, long-only -- rules pre-registered in Bot-Trading-Plan §2d.

Each trading day, from rows known at that close:
  universe   close > min_price ($20), 20-day average dollar volume >= min_adv_usd ($50M),
             200 rows of history, common stock / ADR, no split in the trailing 30 days
  signal     close > SMA200 and RSI(2) < rsi_max (10); rank by RSI ascending; up to max_names (5)
  entry      buy at that day's close (+ slippage)
  exit       sell at the close (- slippage) of the first later day whose close is above the
             prior day's high, or after max_hold (10) trading days
  sizing     size_pct (20%) of equity per name, whole shares, cash only, IBKR fixed commission
Positions are tracked per ticker; a ticker already held is not re-entered. Delisted names:
if a held ticker's bars end, the position is closed at its last close (the stock stopped
trading -- the honest assumption is the last print, not a rescue).

Usage:
    py -3 research/orb/backtest_mr.py --tag mr_base
    py -3 research/orb/backtest_mr.py --grid --tag mr
"""
from __future__ import annotations

import argparse
import time
from dataclasses import asdict, dataclass, replace

import pandas as pd

from backtest_orb import commission, print_report, summarize
from common import STORE_DIR, connect, load_env


@dataclass
class MParams:
    min_price: float = 20.0
    min_adv_usd: float = 50e6
    sma_len: int = 200
    rsi_max: float = 10.0
    max_names: int = 5
    max_hold: int = 10
    size_pct: float = 0.20
    slippage: float = 0.01
    commission_per_share: float = 0.005
    commission_min: float = 1.0
    commission_max_pct: float = 0.01
    start_equity: float = 25_000.0
    tag: str = "mr_base"


# Prices are split-adjusted in daily_adj / daily_ind (build_daily.py), so no split exclusion.
# The trend filter column is chosen by sma_len (200 or 100); sma_len 1 disables it.
SIGNAL_SQL = """
SELECT i.ticker, i.d, i.close, i.prev_high, r.rsi2, i.sma200, i.sma100, i.adv20_usd
FROM daily_ind i
JOIN daily_rsi r USING (ticker, d)
WHERE i.n_hist >= 200 AND i.close > ? AND i.adv20_usd >= ?
  AND (CASE WHEN ? = 200 THEN i.close > i.sma200 WHEN ? = 100 THEN i.close > i.sma100 ELSE TRUE END)
  AND r.rsi2 < ?
  AND i.ticker NOT IN (SELECT ticker FROM tickers WHERE type IS NOT NULL AND type NOT IN ('CS', 'ADRC'))
ORDER BY i.d, r.rsi2, i.ticker
"""

BARS_SQL = """
SELECT ticker, d, close, prev_high FROM daily_ind WHERE ticker IN (SELECT DISTINCT ticker FROM sig) ORDER BY ticker, d
"""


def run(p: MParams) -> dict:
    con = connect(read_only=True)
    sig = con.execute(SIGNAL_SQL, [p.min_price, p.min_adv_usd, p.sma_len, p.sma_len, p.rsi_max]).df()
    con.register("sig", sig)
    bars = con.execute(BARS_SQL).df()
    con.close()
    days = sorted(bars["d"].unique())
    day_index = {d: i for i, d in enumerate(days)}
    by_ticker = {t: g.set_index("d") for t, g in bars.groupby("ticker", sort=False)}
    sig_by_day = {d: g for d, g in sig.groupby("d", sort=False)}

    equity, cash = p.start_equity, p.start_equity
    open_pos: dict[str, dict] = {}
    trades, curve = [], []
    for d in days:
        # 1) exits at today's close for positions opened before today
        for t in list(open_pos):
            pos = open_pos[t]
            g = by_ticker[t]
            if d not in g.index:
                # delisted / no bar: close at the last known close if the series ended
                if g.index[-1] < d:
                    px = float(g["close"].iloc[-1]) - p.slippage
                    _close(pos, px, d, "delisted", p, trades, t)
                    cash += pos["qty"] * px - commission(pos["qty"], pos["qty"] * px, p)
                    del open_pos[t]
                continue
            row = g.loc[d]
            held = day_index[d] - day_index[pos["entry_d"]]
            if held >= 1 and (float(row["close"]) > float(row["prev_high"]) or held >= p.max_hold):
                px = float(row["close"]) - p.slippage
                _close(pos, px, d, "target" if float(row["close"]) > float(row["prev_high"]) else "time", p, trades, t)
                cash += pos["qty"] * px - commission(pos["qty"], pos["qty"] * px, p)
                del open_pos[t]
        # 2) mark and record
        mark = cash + sum(pos["qty"] * float(by_ticker[t].loc[d, "close"]) if d in by_ticker[t].index else pos["qty"] * pos["last"]
                          for t, pos in open_pos.items())
        equity = mark
        # 3) entries at today's close
        todays = sig_by_day.get(d)
        if todays is not None:
            slots = p.max_names - len(open_pos)
            for row in todays.itertuples(index=False):
                if slots <= 0:
                    break
                if row.ticker in open_pos:
                    continue
                px = float(row.close) + p.slippage
                qty = int(min(p.size_pct * equity, cash) // px)
                if qty < 1 or qty * px < 500:
                    continue
                fee = commission(qty, qty * px, p)
                cash -= qty * px + fee
                open_pos[row.ticker] = {"qty": qty, "entry": px, "entry_d": d, "fee_in": fee, "last": float(row.close),
                                        "rsi": float(row.rsi2)}
                slots -= 1
        for t, pos in open_pos.items():
            if d in by_ticker[t].index:
                pos["last"] = float(by_ticker[t].loc[d, "close"])
        curve.append({"d": str(d), "equity": round(equity, 2), "pnl": round(equity - (curve[-1]["equity"] if curve else p.start_equity), 2)})
    out = summarize(_as_params(p), trades, curve)
    out["params"] = asdict(p)
    out["signals"] = int(len(sig))
    out["open_at_end"] = len(open_pos)
    (STORE_DIR / f"orb_{p.tag}.json").write_text(pd.Series(out).to_json(indent=2), encoding="utf-8")
    return out


def _close(pos: dict, px: float, d, reason: str, p: MParams, trades: list, ticker: str) -> None:
    fee = pos["fee_in"] + commission(pos["qty"], pos["qty"] * px, p)
    pnl = pos["qty"] * (px - pos["entry"]) - fee
    risk = pos["qty"] * pos["entry"] * 0.05  # 5% of notional as the R unit for comparability (no hard stop)
    trades.append({"d": str(pos["entry_d"]), "exit_d": str(d), "ticker": ticker, "shares": pos["qty"], "entry": round(pos["entry"], 4),
                   "exit": round(px, 4), "reason": reason, "rsi": round(pos["rsi"], 1), "risk": round(risk, 2),
                   "fees": round(fee, 2), "pnl": round(pnl, 2), "r": round(pnl / risk, 3)})


def _as_params(p: MParams):
    from backtest_orb import Params

    return Params(start_equity=p.start_equity, tag=p.tag, slippage=p.slippage,
                  commission_per_share=p.commission_per_share, commission_min=p.commission_min)


def grid(base: MParams) -> pd.DataFrame:
    rows = []

    def add(name: str, q: MParams) -> None:
        o = run(replace(q, tag=f"{base.tag}_{name}"))
        rows.append({"run": name, "signals": o.get("signals"), "trades": o.get("trades"), "win%": o.get("win_rate_pct"),
                     "PF": o.get("profit_factor"), "exp_$": o.get("expectancy_usd"), "CAGR%": o.get("cagr_pct"),
                     "maxDD%": o.get("max_drawdown_pct"), "sharpe": o.get("sharpe")})
        print(pd.DataFrame(rows[-1:]).to_string(index=False, header=len(rows) == 1), flush=True)

    add("base", base)
    for r in (5.0, 15.0):
        add(f"rsi{int(r)}", replace(base, rsi_max=r))
    for h in (5, 20):
        add(f"hold{h}", replace(base, max_hold=h))
    add("sma100", replace(base, sma_len=100))
    add("no_trend", replace(base, sma_len=1))
    add("names3", replace(base, max_names=3, size_pct=0.33))
    add("names10", replace(base, max_names=10, size_pct=0.10))
    add("price10_adv20m", replace(base, min_price=10.0, min_adv_usd=20e6))
    add("adv200m", replace(base, min_adv_usd=200e6))
    for slip in (0.0, 0.02, 0.03):
        add(f"slip{slip}", replace(base, slippage=slip))
    add("2xcosts", replace(base, slippage=0.02, commission_per_share=0.01))
    return pd.DataFrame(rows)


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="mr_base")
    ap.add_argument("--grid", action="store_true")
    a = ap.parse_args()
    p = MParams(tag=a.tag)
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
