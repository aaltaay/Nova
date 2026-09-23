"""Split a setup's backtest trades by catalyst class (ADR 024).

Each trade's symbol-day is judged by the live desk's classifier twice, never with hindsight:

  open    items published after the prior close and by 09:30 ET (the pre-registered cutoff)
  entry   items published by the trade's own entry minute (what a trader could have read)

and the trades are grouped by verdict (catalyst strong / weak, negative, routine / noise
only, none found) and, for catalysts, by class. Results are descriptive: a split of a screen
that did not pass gate 1, to see whether a real catalyst changes the first pullback.

Usage:  py -3 research/catalysts/split_trades.py --tag fp_all
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime, time as dtime

import pandas as pd

from cat_config import ET, MASSIVE_ROOT, RESEARCH_CUTOFF_ET, RESULTS_DIR, et_ts
from store import connect

from catalysts.classify import verdict

ITEM_COLS = ("title", "summary", "source", "publisher", "n_tickers", "form", "sec_items", "url", "published_ts")


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
            "WHERE t.ticker = ? AND t.published_ts > ? AND t.published_ts <= ?", [tr.ticker, w0, entry_ts])]
        src = answered.get(key, ())
        v_open = verdict(items, window_start=w0, cutoff=et_ts(d, RESEARCH_CUTOFF_ET), sources_answered=src)
        v_entry = verdict(items, window_start=w0, cutoff=entry_ts, sources_answered=src)
        rows.append({"at_open": v_open["verdict"] + (f":{v_open['strength']}" if v_open["strength"] else ""),
                     "at_entry": v_entry["verdict"] + (f":{v_entry['strength']}" if v_entry["strength"] else ""),
                     "open_class": v_open["category"], "open_strength": v_open["strength"],
                     "open_title": v_open["title"], "negative_too": v_open["negative_too"]})
    df = pd.concat([trades.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    out = {"tag": a.tag, "trades": stats(df), "by_verdict_at_open": {}, "by_verdict_at_entry": {},
           "catalyst_class_at_open": {}, "catalyst_with_dilution_at_open": {}}
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
    for section in ("by_verdict_at_open", "by_verdict_at_entry", "catalyst_class_at_open", "catalyst_with_dilution_at_open"):
        print(f"\n== {section} ==")
        print(pd.DataFrame(out[section]).T.sort_values("trades", ascending=False).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
