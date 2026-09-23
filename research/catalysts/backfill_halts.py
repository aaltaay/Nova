"""Nasdaq Trader's halt history into the leaderboard's halt log (ADR 023 / 024).

  download   one RSS page per trading day (``rss.aspx?feed=tradehalts&haltdate=MMDDYYYY``) kept raw
             under ``F:\\Nova\\catalysts\\halts\\raw`` -- resumable, a file per date
  load       every raw page parsed by the live desk's own parser (``ibkr/nasdaq_halt_rss.py``) into
             ``halt_events`` (source ``nasdaq_trade_halt_rss``): a start at the official halt time, an
             end at the trade resumption. Idempotent -- the table's key makes a repeat harmless.

Sim playback of a rebuilt day then shows its halts, and research can ask "halted for news before
the entry?" (T1 news pending, T2 news released, LUDP a LULD pause, ...). Nothing is inferred from
quiet tape; a day Nasdaq lists no halt for simply has none.

Usage:  py -3 research/catalysts/backfill_halts.py [--download] [--load]
"""
from __future__ import annotations

import argparse
import time
import urllib.request
from collections import Counter
from datetime import date

import duckdb

from cat_config import RESEARCH_DB, ROOT

from constants_leaderboard import LEADERBOARD_HALT_EVENT_END, LEADERBOARD_HALT_EVENT_START, LEADERBOARD_HALT_SOURCE_NASDAQ
from ibkr.nasdaq_halt_rss import parse_trade_halt_rss
from leaderboard import store as lb_store
from leaderboard.halts import event

RAW = ROOT / "halts" / "raw"
URL = "https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts&haltdate={d:%m%d%Y}"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def trading_days() -> list[date]:
    con = duckdb.connect(str(RESEARCH_DB), read_only=True)
    try:
        return [r[0] for r in con.execute("SELECT DISTINCT d FROM daily_days ORDER BY d").fetchall()]
    finally:
        con.close()


def download() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    got = 0
    for d in trading_days():
        out = RAW / f"{d.isoformat()}.xml"
        if out.exists() and out.stat().st_size > 200:
            continue
        for attempt in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(URL.format(d=d), headers=UA), timeout=30) as r:
                    out.write_bytes(r.read())
                got += 1
                break
            except Exception as exc:  # noqa: BLE001 -- retried, then left for the next run
                print(f"  {d} retry {attempt}: {exc}", flush=True)
                time.sleep(3 * (attempt + 1))
        time.sleep(0.4)
    print(f"download: {got} new pages; {len(list(RAW.glob('*.xml')))} on disk", flush=True)


def load() -> None:
    rows, codes, bad = [], Counter(), 0
    for path in sorted(RAW.glob("*.xml")):
        parsed = parse_trade_halt_rss(path.read_bytes())
        if not parsed.get("ok"):
            bad += 1
            continue
        recorded = path.stat().st_mtime
        for h in parsed["rows"]:
            if not h.symbol or h.mwcb_level is not None:
                continue
            codes[h.reason_code or "?"] += 1
            if h.official_halt_start is not None:
                rows.append(event(symbol=h.symbol, ts=h.official_halt_start, kind=LEADERBOARD_HALT_EVENT_START,
                                  source=LEADERBOARD_HALT_SOURCE_NASDAQ, halt_kind=h.reason_code, code=h.reason_code,
                                  recorded_ts=recorded))
            if h.trade_resume is not None:
                rows.append(event(symbol=h.symbol, ts=h.trade_resume, kind=LEADERBOARD_HALT_EVENT_END,
                                  source=LEADERBOARD_HALT_SOURCE_NASDAQ, halt_kind=h.reason_code, code=h.reason_code,
                                  recorded_ts=recorded))
    rows = [r for r in rows if r is not None]
    with lb_store.connect() as db:
        before = db.execute("SELECT count(*) FROM halt_events WHERE source = ?", [LEADERBOARD_HALT_SOURCE_NASDAQ]).fetchone()[0]
        lb_store.write_batch(db, halts=rows)
        after = db.execute("SELECT count(*) FROM halt_events WHERE source = ?", [LEADERBOARD_HALT_SOURCE_NASDAQ]).fetchone()[0]
    print(f"load: {len(rows)} events offered, {after - before} new ({after} Nasdaq events on file); "
          f"{bad} unreadable pages; halts by code: {dict(codes.most_common(12))}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--load", action="store_true")
    a = ap.parse_args()
    if a.download or not a.load:
        download()
    if a.load or not a.download:
        load()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
