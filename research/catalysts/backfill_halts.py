"""Nasdaq Trader's halt history into the leaderboard's halt log (ADR 023 / 024).

  download   one RSS page per trading day (``rss.aspx?feed=tradehalts&haltdate=MMDDYYYY``) kept raw
             under ``F:\\Nova\\catalysts\\halts\\raw`` -- resumable, a file per date. A day counts as
             downloaded only when its page reads as RSS: Nasdaq answers some requests with a small bot-check
             HTML page instead, which is never saved as the day and is fetched again next run (#1075)
  load       every raw page parsed by the live desk's own parser (``ibkr/nasdaq_halt_rss.py``) into
             ``halt_events`` (source ``nasdaq_trade_halt_rss``): a start at the official halt time, an
             end at the trade resumption. Idempotent -- the table's key makes a repeat harmless.

Sim playback of a rebuilt day then shows its halts, and research can ask "halted for news before
the entry?" (T1 news pending, T2 news released, LUDP a LULD pause, ...). Nothing is inferred from
quiet tape; a day Nasdaq lists no halt for simply has none.

Usage:  py -3 research/catalysts/backfill_halts.py [--download] [--load [--dry-run]]
"""
from __future__ import annotations

import argparse
import time
import urllib.request
from collections import Counter
from contextlib import closing
from datetime import date
from pathlib import Path

import duckdb

from cat_config import RESEARCH_DB, ROOT

from constants_leaderboard import LEADERBOARD_HALT_EVENT_END, LEADERBOARD_HALT_EVENT_START, LEADERBOARD_HALT_SOURCE_NASDAQ
from ibkr.nasdaq_halt_rss import parse_trade_halt_rss
from leaderboard import store as lb_store
from leaderboard.halts import event

RAW = ROOT / "halts" / "raw"
URL = "https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts&haltdate={d:%m%d%Y}"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
ATTEMPTS = 4            # a day whose answer fails, or is not RSS, is asked this often, then left for the next run
RETRY_PAUSE_SEC = 3.0   # before the next attempt, times the attempts made
DAY_PAUSE_SEC = 0.4     # between days


def trading_days() -> list[date]:
    con = duckdb.connect(str(RESEARCH_DB), read_only=True)
    try:
        return [r[0] for r in con.execute("SELECT DISTINCT d FROM daily_days ORDER BY d").fetchall()]
    finally:
        con.close()


def is_rss(body: bytes) -> bool:
    """The live desk's parser reads ``body`` as Nasdaq's RSS (a day with no halts is RSS with no items)."""
    return bool(parse_trade_halt_rss(body).get("ok"))


def downloaded(page: Path) -> bool:
    """A day's stored page counts only when it reads as RSS: a run before #1075 kept any page over 200 bytes, so
    a 212-byte bot-check page sat on disk as a finished day and was never asked for again."""
    try:
        return page.is_file() and is_rss(page.read_bytes())
    except OSError:
        return False


def _fetch(d: date) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(URL.format(d=d), headers=UA), timeout=30) as r:
        return r.read()


def _fetch_rss(d: date) -> bytes | None:
    """The day's page from the first attempt that answers RSS; None after ``ATTEMPTS`` that did not."""
    for attempt in range(ATTEMPTS):
        try:
            body = _fetch(d)
        except Exception as exc:  # noqa: BLE001 -- retried, then left for the next run
            print(f"  {d} retry {attempt}: {exc}", flush=True)
        else:
            parsed = parse_trade_halt_rss(body)
            if parsed.get("ok"):
                return body
            print(f"  {d} retry {attempt}: the answer is not RSS ({len(body)} bytes, {parsed.get('error')}); "
                  "a bot-check page is not saved", flush=True)
        if attempt + 1 < ATTEMPTS:
            time.sleep(RETRY_PAUSE_SEC * (attempt + 1))
    return None


def download() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    got = kept = left = 0
    for d in trading_days():
        out = RAW / f"{d.isoformat()}.xml"
        if downloaded(out):
            kept += 1
            continue
        body = _fetch_rss(d)
        if body is None:
            left += 1
            print(f"  {d}: no RSS after {ATTEMPTS} attempts; not saved as the day, asked for again next run",
                  flush=True)
        else:
            out.write_bytes(body)
            got += 1
        time.sleep(DAY_PAUSE_SEC)
    print(f"download: {got} new pages; {kept} already on disk; {left} days without an RSS page "
          "(asked for again next run)", flush=True)


def _new_by_event(db, rows: list[dict]) -> Counter:
    have = set(db.execute("SELECT symbol, source, event, ts FROM halt_events WHERE source = ?",
                          [LEADERBOARD_HALT_SOURCE_NASDAQ]).fetchall())
    keys = {(r["symbol"], r["source"], r["event"], r["ts"]) for r in rows}
    return Counter(k[2] for k in keys - have)


def load(dry_run: bool = False) -> None:
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
    if dry_run:
        db = lb_store.read_only()
        if db is None:
            raise SystemExit(f"{lb_store.path()} is not on disk: nothing to compare against")
        with closing(db):
            new = _new_by_event(db, rows)
        print(f"load --dry-run: {len(rows)} events offered, {sum(new.values())} would be new "
              f"({dict(new)}); {bad} unreadable pages; nothing written", flush=True)
        return
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
    ap.add_argument("--dry-run", action="store_true", help="with --load: count the new halt_events rows, write none")
    a = ap.parse_args()
    if a.download or not a.load:
        download()
    if a.load or not a.download:
        load(dry_run=a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
