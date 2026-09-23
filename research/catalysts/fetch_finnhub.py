"""Finnhub company news for every target inside the free tier's one-year reach.

One call per symbol-day (``company-news`` is per symbol, date-granular); items are kept to the
target's window by their own timestamp. Older targets are recorded ``out_of_range`` -- asked of
a source that cannot reach them, never "no news". Resumable: answered targets are skipped.

Usage:  py -3 research/catalysts/fetch_finnhub.py [--limit N] [--shard i/n]
"""
from __future__ import annotations

import argparse
import os
import time
import urllib.parse
from datetime import datetime, timedelta

from cat_config import ET, FINNHUB_CALLS_PER_MIN, FINNHUB_HISTORY_DAYS, load_env
from http_util import HttpRefused, Pacer, get
from store import connect, pending, put_check, put_items

from constants_catalysts import CATALYST_FINNHUB_SKIP_PUBLISHERS  # the live desk's list (cat_config: backend/ on the path)

SOURCE = "finnhub"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--shard", default="0/1", help="i/n: this worker takes every n-th target (parallel workers share the limit)")
    a = ap.parse_args()
    shard, shards = (int(x) for x in a.shard.split("/"))
    load_env()
    key = os.environ.get("FINNHUB_API_KEY")
    con = connect()
    todo = [t for k, t in enumerate(pending(con, SOURCE)) if k % shards == shard]
    if a.limit:
        todo = todo[: a.limit]
    reach = time.time() - FINNHUB_HISTORY_DAYS * 86400
    pacer = Pacer(FINNHUB_CALLS_PER_MIN / 60 / shards)
    n_ok = n_items = 0
    for i, (ticker, day, w0, _cut, w1) in enumerate(todo, 1):
        if not key:
            put_check(con, ticker, day, SOURCE, "unavailable", detail="FINNHUB_API_KEY not set")
            continue
        if w0 < reach:
            put_check(con, ticker, day, SOURCE, "out_of_range", detail=f"free tier reaches {FINNHUB_HISTORY_DAYS} days")
            continue
        frm = datetime.fromtimestamp(w0, ET).date().isoformat()
        to = (datetime.fromtimestamp(w1, ET).date() + timedelta(days=1)).isoformat()
        q = urllib.parse.urlencode({"symbol": ticker, "from": frm, "to": to, "token": key})
        try:
            rows = get(f"https://finnhub.io/api/v1/company-news?{q}", None, pacer)
        except HttpRefused as e:
            put_check(con, ticker, day, SOURCE, "unavailable", detail=str(e))
            continue
        except Exception as e:  # noqa: BLE001 -- recorded and retried next run
            put_check(con, ticker, day, SOURCE, "error", detail=str(e)[:200])
            continue
        items = [{
            "item_id": f"finnhub:{r.get('id')}", "source": SOURCE, "published_ts": float(r["datetime"]),
            "title": r.get("headline"), "summary": (r.get("summary") or "")[:2000], "url": r.get("url"),
            "publisher": r.get("source"), "tickers": [ticker], "n_tickers": None,
        } for r in (rows if isinstance(rows, list) else []) if r.get("datetime") and w0 < float(r["datetime"]) <= w1
            # Benzinga copies carry Eastern time read as UTC, four hours early (#516); Alpaca has them right.
            and str(r.get("source") or "").strip().lower() not in CATALYST_FINNHUB_SKIP_PUBLISHERS]
        with con:
            put_items(con, items)
            put_check(con, ticker, day, SOURCE, "ok", n_items=len(items))
        n_ok += 1
        n_items += len(items)
        if i % 100 == 0:
            print(f"  {i}/{len(todo)} checked, {n_items} items", flush=True)
    con.commit()
    print(f"finnhub: {n_ok} symbol-days answered, {n_items} items", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
