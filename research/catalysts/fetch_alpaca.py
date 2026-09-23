"""Alpaca news (Benzinga's newsroom) for every target, one session day per request batch.

Targets of one session day share a request of up to 50 symbols over the day's widest window,
paged to the end; each target then keeps only its own ticker's items inside its own window.
Resumable: answered targets are skipped.

Usage:  py -3 research/catalysts/fetch_alpaca.py [--limit-days N]
"""
from __future__ import annotations

import argparse
import os
import urllib.parse
from collections import defaultdict
from datetime import datetime, timezone

from cat_config import ALPACA_CALLS_PER_MIN, load_env
from http_util import HttpRefused, Pacer, get
from store import connect, pending, put_check, put_items

SOURCE = "alpaca"
URL = "https://data.alpaca.markets/v1beta1/news"
BATCH = 50


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(symbols: list[str], start: float, end: float, headers: dict, pacer: Pacer) -> list[dict]:
    out, token = [], None
    while True:
        params = {"symbols": ",".join(symbols), "start": iso(start), "end": iso(end), "limit": 50,
                  "sort": "asc", "include_content": "false"}
        if token:
            params["page_token"] = token
        body = get(f"{URL}?{urllib.parse.urlencode(params)}", headers, pacer)
        out.extend(body.get("news") or [])
        token = body.get("next_page_token")
        if not token:
            return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit-days", type=int, default=0)
    a = ap.parse_args()
    load_env()
    kid = os.environ.get("APCA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY_ID")
    sec = os.environ.get("APCA_API_SECRET_KEY") or os.environ.get("ALPACA_API_SECRET_KEY")
    headers = {"APCA-API-KEY-ID": kid or "", "APCA-API-SECRET-KEY": sec or ""}
    con = connect()
    by_day: dict[str, list[tuple]] = defaultdict(list)
    for row in pending(con, SOURCE):
        by_day[row[1]].append(row)
    days = sorted(by_day, reverse=True)[: a.limit_days or None]
    pacer = Pacer(ALPACA_CALLS_PER_MIN / 60)
    n_items = 0
    for i, day in enumerate(days, 1):
        targets = by_day[day]
        for k in range(0, len(targets), BATCH):
            chunk = targets[k:k + BATCH]
            if not (kid and sec):
                for t in chunk:
                    put_check(con, t[0], day, SOURCE, "unavailable", detail="Alpaca keys not set")
                continue
            try:
                news = fetch(sorted({t[0] for t in chunk}), min(t[2] for t in chunk), max(t[4] for t in chunk), headers, pacer)
            except HttpRefused as e:
                for t in chunk:
                    put_check(con, t[0], day, SOURCE, "unavailable", detail=str(e))
                continue
            except Exception as e:  # noqa: BLE001 -- recorded and retried next run
                for t in chunk:
                    put_check(con, t[0], day, SOURCE, "error", detail=str(e)[:200])
                continue
            items = []
            for n in news:
                ts = datetime.fromisoformat(str(n["created_at"]).replace("Z", "+00:00")).timestamp()
                items.append({"item_id": f"alpaca:{n['id']}", "source": SOURCE, "published_ts": ts,
                              "title": n.get("headline"), "summary": (n.get("summary") or "")[:2000],
                              "url": n.get("url"), "publisher": n.get("source") or n.get("author"),
                              "tickers": [s.upper() for s in n.get("symbols") or []]})
            with con:
                put_items(con, items)
                for t in chunk:
                    mine = [it for it in items if t[0] in it["tickers"] and t[2] < it["published_ts"] <= t[4]]
                    put_check(con, t[0], day, SOURCE, "ok", n_items=len(mine))
            n_items += len(items)
        if i % 50 == 0:
            print(f"  {i}/{len(days)} days, {n_items} items", flush=True)
    print(f"alpaca: {len(days)} days answered, {n_items} items", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
