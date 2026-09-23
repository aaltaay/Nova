"""The Massive news archive already on F: (``store/reference/news/*.jsonl``) into the store.

No network. Each month file is read once and kept to the tickers the targets name; every
target then gets an ``ok`` check with its own item count. Months the archive does not hold are
``out_of_range``.

Usage:  py -3 research/catalysts/import_massive.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

from cat_config import REFERENCE_DIR
from store import connect, put_check, put_items

SOURCE = "massive"


def month_of(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m")


def main() -> int:
    con = connect()
    targets = con.execute("SELECT ticker, session_date, window_start, window_end FROM targets").fetchall()
    wanted = {t[0] for t in targets}
    months = sorted({month_of(t[2]) for t in targets} | {month_of(t[3]) for t in targets})
    have = {p.stem: p for p in (REFERENCE_DIR / "news").glob("*.jsonl")}
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    n = 0
    for m in months:
        if m not in have:
            continue
        rows = []
        for line in have[m].read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            art = json.loads(line)
            tickers = [str(t).upper() for t in art.get("tickers") or []]
            if not art.get("published_utc") or not wanted.intersection(tickers):
                continue
            ts = datetime.fromisoformat(str(art["published_utc"]).replace("Z", "+00:00")).timestamp()
            rows.append({"item_id": f"massive:{art.get('id')}", "source": SOURCE, "published_ts": ts,
                         "title": art.get("title"), "summary": (art.get("description") or "")[:2000],
                         "url": art.get("article_url"), "publisher": (art.get("publisher") or {}).get("name"),
                         "tickers": tickers})
        with con:
            put_items(con, rows)
        for r in rows:
            for t in r["tickers"]:
                by_ticker[t].append(r)
        n += len(rows)
        print(f"  {m}: {len(rows)} items", flush=True)
    with con:
        for ticker, day, w0, w1 in targets:
            if month_of(w0) not in have or month_of(w1) not in have:
                put_check(con, ticker, day, SOURCE, "out_of_range", detail="archive holds no such month")
                continue
            mine = [r for r in by_ticker.get(ticker, ()) if w0 < r["published_ts"] <= w1]
            put_check(con, ticker, day, SOURCE, "ok", n_items=len(mine))
    print(f"massive: {n} items for {len(targets)} targets", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
