"""Each symbol-day's news into the leaderboard store, so Sim playback shows a mover's catalyst (#498).

The backend never reads this research store (ADR 024); Sim playback of a past day reads the
leaderboard store (ADR 023). So this copies what playback needs into ``leaderboard.sqlite3``, per
target (ticker, session_date):

  catalyst_checks  the window (prior session's 16:00 ET close -> 20:00 ET) and the sources that
                   answered for it (``checks.status = 'ok'``; '' when none did -- playback then says
                   unknown, never "no news")
  catalyst_items   every item naming the ticker inside the window, labelled by the live desk's own
                   classifier at the current rules version (kind, category, strength, dilution) --
                   labels, not article text, so the leaderboard store stays small

Playback judges each board read from the items published by the playhead, so a verdict never knows
a catalyst before it was published. Finnhub's Benzinga copies are left out (``HONEST_CLOCK_SQL``:
their clock is four hours early, #516). Idempotent: every symbol-day written is replaced whole, one
session day per transaction (the desk's recorder keeps writing meanwhile). Run it again after
``build_verdicts.py``, a new fetch or a rules bump.

Usage:  py -3 research/catalysts/export_leaderboard.py [--db PATH] [--since YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

from store import HONEST_CLOCK_SQL, connect

from catalysts.classify import classify_item  # the live desk's module (cat_config puts backend/ on the path)
from constants_catalysts import CATALYST_RULES_VERSION
from leaderboard import store as lb_store

_ITEM_SQL = (
    "SELECT i.item_id, i.published_ts, i.source, i.publisher, i.title, i.summary, i.url, i.n_tickers, "
    "i.form, i.sec_items FROM item_tickers t JOIN items i USING (item_id) "
    f"WHERE t.ticker = ? AND t.published_ts > ? AND t.published_ts <= ? AND {HONEST_CLOCK_SQL} "
    "ORDER BY i.published_ts, i.item_id"
)


def _items_for(con: sqlite3.Connection, ticker: str, day: str, w0: float, w1: float, rules: str) -> list[dict]:
    out = []
    for item_id, ts, source, publisher, title, summary, url, n_tickers, form, sec_items in con.execute(
            _ITEM_SQL, [ticker, w0, w1]):
        label = classify_item(title, summary, source=source or "", publisher=publisher or "", n_tickers=n_tickers,
                              form=form, sec_items=sec_items, url=url or "")
        out.append({"session_date": day, "symbol": ticker, "item_id": item_id, "published_ts": float(ts),
                    "source": source, "publisher": publisher, "title": title, "url": url, "kind": label.kind,
                    "category": label.category, "strength": label.strength, "dilution": int(label.dilution),
                    "rules_version": rules})
    return out


def export(con: sqlite3.Connection, db_path: Path | None = None, *, since: str | None = None,
           now: float | None = None) -> dict:
    """Write every target on or after ``since`` into the leaderboard store at ``db_path``; the counts."""
    stamp = time.time() if now is None else float(now)
    answered: dict[tuple[str, str], set[str]] = defaultdict(set)
    for ticker, day, source in con.execute("SELECT ticker, session_date, source FROM checks WHERE status = 'ok'"):
        answered[(ticker, day)].add(source)
    by_day: dict[str, list[tuple]] = defaultdict(list)
    for ticker, day, w0, w1 in con.execute(
            "SELECT ticker, session_date, window_start, window_end FROM targets WHERE session_date >= ? "
            "ORDER BY session_date, ticker", [since or ""]):
        by_day[day].append((ticker.upper(), float(w0), float(w1), sorted(answered.get((ticker, day), ()))))
    n_checks = n_items = 0
    with lb_store.connect(db_path) as db:
        for day in sorted(by_day):
            checks, items = [], []
            for ticker, w0, w1, sources in by_day[day]:
                checks.append({"session_date": day, "symbol": ticker, "window_start": w0, "window_end": w1,
                               "sources_answered": ",".join(sources), "rules_version": CATALYST_RULES_VERSION,
                               "exported_ts": stamp})
                items.extend(_items_for(con, ticker, day, w0, w1, CATALYST_RULES_VERSION))
            written = lb_store.replace_catalysts(db, checks, items)
            n_checks += written["checks"]
            n_items += written["items"]
    return {"rules_version": CATALYST_RULES_VERSION, "days": len(by_day), "symbol_days": n_checks,
            "items": n_items, "store": str(db_path or lb_store.path())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=None, help=f"leaderboard store (default {lb_store.path()})")
    ap.add_argument("--since", default=None, help="only session days on or after YYYY-MM-DD")
    a = ap.parse_args()
    con = connect()
    try:
        out = export(con, a.db, since=a.since)
    finally:
        con.close()
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
