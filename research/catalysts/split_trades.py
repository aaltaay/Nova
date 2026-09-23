"""Split a setup's backtest trades by catalyst class (ADR 024).

Each trade's symbol-day is judged by the live desk's classifier twice, never with hindsight:

  open    items published after the prior close and by 09:30 ET (the pre-registered cutoff)
  entry   items published by the trade's own entry minute (what a trader could have read)

and the trades are grouped by verdict (catalyst strong / weak, negative, routine / noise
only, none found) and, for catalysts, by class. Each trade also carries, as known before it:

  halts   Nasdaq halts of the symbol that day before the entry (``halt_events``, backfilled by
          ``backfill_halts.py``): a news halt (T1 / T2 / T3 / T12), a volatility pause (LUDP / M), any halt
  shares  shares outstanding from the last SEC filing **filed before the day** (``sec_shares``)
  short   the last FINRA short interest settled at least ``SHORT_INTEREST_LAG_DAYS`` before the
          day, as a share of those shares, and its days to cover (``short_interest``)

Results are descriptive: a split of a screen that did not pass gate 1, to see what changes the
first pullback.

Usage:  py -3 research/catalysts/split_trades.py --tag fp_all
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime, time as dtime

import duckdb
import pandas as pd

from cat_config import ET, LEADERBOARD_DB, MASSIVE_ROOT, RESEARCH_CUTOFF_ET, RESEARCH_DB, RESULTS_DIR, et_ts
from store import HONEST_CLOCK_SQL, connect

from catalysts.classify import verdict

ITEM_COLS = ("title", "summary", "source", "publisher", "n_tickers", "form", "sec_items", "url", "published_ts")
SHORT_INTEREST_LAG_DAYS = 14   # FINRA publishes ~8 business days after settlement: never read one early
# Nasdaq's history shows a halt's final code: a news halt that opened as T1 (news pending) reads T3
# (news and resumption times) once resolved, so every T-code counts as a news halt here.
NEWS_HALT = ("T1", "T2", "T3", "T12")
VOLATILITY_PAUSE = ("LUDP", "M")


def facts(df: pd.DataFrame) -> pd.DataFrame:
    """Halts before the entry, shares outstanding filed before the day, lagged short interest."""
    import sqlite3

    lb = sqlite3.connect(f"file:{LEADERBOARD_DB.as_posix()}?mode=ro", uri=True)
    halts: dict[tuple[str, str], list[tuple[float, str]]] = {}
    for sym, day, ts, code in lb.execute(
            "SELECT symbol, session_date, ts, code FROM halt_events WHERE event = 'start' AND source = 'nasdaq_trade_halt_rss'"):
        halts.setdefault((sym, day), []).append((float(ts), (code or "").upper()))
    lb.close()
    rs = duckdb.connect(str(RESEARCH_DB), read_only=True)
    rs.register("tr", df[["ticker", "day"]].drop_duplicates())
    shares = {(t, d): v for t, d, v in rs.execute(
        "SELECT tr.ticker, tr.day, arg_max(s.shares, s.end_d) FROM tr JOIN sec_shares s ON s.ticker = tr.ticker "
        "AND s.filed_d < CAST(tr.day AS DATE) GROUP BY 1, 2").fetchall()}
    short = {(t, d): (si, dtc) for t, d, si, dtc in rs.execute(
        "SELECT tr.ticker, tr.day, arg_max(s.short_interest, s.settlement_d), arg_max(s.days_to_cover, s.settlement_d) "
        f"FROM tr JOIN short_interest s ON s.ticker = tr.ticker AND s.settlement_d <= CAST(tr.day AS DATE) - {SHORT_INTEREST_LAG_DAYS} "
        "GROUP BY 1, 2").fetchall()}
    rs.close()
    out = []
    for tr in df.itertuples(index=False):
        d = date.fromisoformat(tr.day)
        entry_ts = datetime.combine(d, dtime.fromisoformat(tr.entry_t), ET).timestamp()
        before = [code for ts, code in halts.get((tr.ticker, tr.day), []) if ts <= entry_ts]
        sh = shares.get((tr.ticker, tr.day))
        si, dtc = short.get((tr.ticker, tr.day), (None, None))
        si_pct = (si / sh) if (si and sh) else None
        out.append({
            "halt_before": "news halt (T1-T3)" if any(p in NEWS_HALT for c in before for p in c.split("/"))
            else "volatility pause (LULD)" if any(c in VOLATILITY_PAUSE for c in before) else "other halt" if before
            else "no halt",
            "shares_b": "unknown" if not sh else "<5M" if sh < 5e6 else "5-10M" if sh < 10e6 else "10-20M"
            if sh < 20e6 else "20-50M" if sh < 50e6 else ">50M",
            "short_b": "unknown" if si_pct is None else "<5%" if si_pct < 0.05 else "5-15%" if si_pct < 0.15 else ">=15%",
            "dtc_b": "unknown" if dtc is None else "<1d" if dtc < 1 else "1-3d" if dtc < 3 else ">=3d",
        })
    return pd.DataFrame(out)


def stats(g: pd.DataFrame) -> dict:
    wins, losses = g.loc[g.pnl > 0, "pnl"].sum(), -g.loc[g.pnl < 0, "pnl"].sum()
    return {"trades": int(len(g)), "win_pct": round(100 * float((g.pnl > 0).mean()), 1) if len(g) else None,
            "avg_r": round(float(g.r.mean()), 3) if len(g) else None,
            "median_r": round(float(g.r.median()), 3) if len(g) else None,
            "profit_factor": round(float(wins / losses), 2) if losses else None, "pnl": round(float(g.pnl.sum()), 0)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="fp_all")
    a = ap.parse_args()
    trades = pd.read_csv(MASSIVE_ROOT / "store" / f"orb_{a.tag}_trades.csv")
    trades["day"] = trades["d"].str[:10]
    con = connect()
    answered = defaultdict(list)
    for ticker, day, source in con.execute("SELECT ticker, session_date, source FROM checks WHERE status = 'ok'"):
        answered[(ticker, day)].append(source)
    windows = {(t, d): w0 for t, d, w0 in con.execute("SELECT ticker, session_date, window_start FROM targets")}
    rows = []
    for tr in trades.itertuples(index=False):
        key = (tr.ticker, tr.day)
        w0 = windows.get(key)
        if w0 is None:
            rows.append({"at_open": "no_target", "at_entry": "no_target", "open_class": None, "open_strength": None})
            continue
        d = date.fromisoformat(tr.day)
        entry_ts = datetime.combine(d, dtime.fromisoformat(tr.entry_t), ET).timestamp()
        items = [dict(zip(ITEM_COLS, r, strict=True)) for r in con.execute(
            f"SELECT {', '.join('i.' + c for c in ITEM_COLS)} FROM item_tickers t JOIN items i USING (item_id) "
            f"WHERE t.ticker = ? AND t.published_ts > ? AND t.published_ts <= ? AND {HONEST_CLOCK_SQL}",
            [tr.ticker, w0, entry_ts])]
        src = answered.get(key, ())
        v_open = verdict(items, window_start=w0, cutoff=et_ts(d, RESEARCH_CUTOFF_ET), sources_answered=src)
        v_entry = verdict(items, window_start=w0, cutoff=entry_ts, sources_answered=src)
        rows.append({"at_open": v_open["verdict"] + (f":{v_open['strength']}" if v_open["strength"] else ""),
                     "at_entry": v_entry["verdict"] + (f":{v_entry['strength']}" if v_entry["strength"] else ""),
                     "open_class": v_open["category"], "open_strength": v_open["strength"],
                     "open_title": v_open["title"], "negative_too": v_open["negative_too"]})
    df = pd.concat([trades.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    df = pd.concat([df, facts(df)], axis=1)
    df["catalyst_x_shares"] = df.at_open.str.split(":").str[0] + " / " + df.shares_b.where(
        df.shares_b.isin(["<5M", "5-10M", "10-20M"]), "20M+ or unknown").replace({"<5M": "<20M", "5-10M": "<20M", "10-20M": "<20M"})
    out = {"tag": a.tag, "trades": stats(df), "by_verdict_at_open": {}, "by_verdict_at_entry": {},
           "catalyst_class_at_open": {}, "catalyst_with_dilution_at_open": {}, "halt_before_entry": {},
           "shares_outstanding": {}, "short_interest_pct": {}, "days_to_cover": {}, "catalyst_x_shares": {}}
    for col, key in (("halt_before", "halt_before_entry"), ("shares_b", "shares_outstanding"),
                     ("short_b", "short_interest_pct"), ("dtc_b", "days_to_cover"), ("catalyst_x_shares", "catalyst_x_shares")):
        for v, g in df.groupby(col):
            out[key][v] = stats(g)
    for col, key in (("at_open", "by_verdict_at_open"), ("at_entry", "by_verdict_at_entry")):
        for v, g in df.groupby(col):
            out[key][v] = stats(g)
    cats = df[df.at_open.str.startswith("catalyst")]
    for c, g in cats.groupby("open_class"):
        out["catalyst_class_at_open"][c] = stats(g)
    for flag, g in cats.groupby("negative_too"):
        out["catalyst_with_dilution_at_open"][str(bool(flag))] = stats(g)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"split_{a.tag}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    df.to_csv(RESULTS_DIR / f"split_{a.tag}_trades.csv", index=False)
    for k in ("trades",):
        print(f"all trades: {out[k]}")
    for section in ("by_verdict_at_open", "by_verdict_at_entry", "catalyst_class_at_open", "catalyst_with_dilution_at_open",
                    "halt_before_entry", "shares_outstanding", "short_interest_pct", "days_to_cover", "catalyst_x_shares"):
        print(f"\n== {section} ==")
        print(pd.DataFrame(out[section]).T.sort_values("trades", ascending=False).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
