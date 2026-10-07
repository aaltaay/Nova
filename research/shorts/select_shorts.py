"""Pass 1 of the five-year test (ADR 049 step 4): the short setups' universe, from the day movers index.

Reads ``<NOVA_MARKET_DATA_DIR>/movers/day_movers.sqlite3`` (ADR 050, read-only) and writes ``shorts_selection`` in
the ORB store (``research/orb/common.py``), one row per stock-day the scanner would have followed, with no
hindsight:

- a common stock (the index's ``CS`` / ``ADRC``, or a 1-4 letter ticker with no type) whose high reached +10% over
  the prior close (``up10_ts``), at $1-$20 at that price, that traded 100,000 shares or more that day (the minute it
  reached them is found from the minute bars), and not a likely split;
- ``former_momo``: yesterday's movers of the same kind, followed from 04:00 for the SSR bounce, with yesterday's
  official close as today's prior close when the stock did not move today;
- ``ssr_yesterday``: true when yesterday's whole-day low was 10% or more under its prior close, false when
  yesterday's session was built and the stock's row says less or is absent (the index keeps every -10% low), null
  when yesterday is not in the index.

Then extract the minutes with ``research/orb/extract_minutes.py --selection shorts_selection --table minutes_shorts
--start 04:00``.

Usage:
    py -3 research/shorts/select_shorts.py [--years 5] [--first YYYY-MM-DD] [--last YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import date, timedelta
from typing import Any

import shorts_config as cfg

SCHEMA = f"""
CREATE OR REPLACE TABLE {cfg.SELECTION_TABLE} (
    d DATE, ticker VARCHAR, prior_close DOUBLE, up10_ts BIGINT, mover BOOLEAN, former_momo BOOLEAN,
    ssr_yesterday BOOLEAN);
"""


def common_kind(row: dict[str, Any]) -> bool:
    from constants_agent_desk import AGENT_MOVERS_COMMON_KINDS

    kind, sym = row.get("kind"), str(row.get("symbol") or "")
    if kind in AGENT_MOVERS_COMMON_KINDS:
        return True
    return kind is None and 1 <= len(sym) <= 4 and sym.isalpha() and sym.isupper()


def followed(row: dict[str, Any]) -> bool:
    """Today's mover the scanner would have followed (the minute bars add the 100,000-share minute)."""
    from day_movers.query import split_label

    pc = row.get("prev_close")
    if not common_kind(row) or not pc or row.get("up10_ts") is None:
        return False
    price = pc * (1.0 + cfg.FOLLOW_UP_PCT)
    if not cfg.PRICE_MIN <= price <= cfg.PRICE_MAX:
        return False
    if (row.get("volume") or 0) < cfg.FOLLOW_MIN_VOLUME:
        return False
    return split_label(row) != "likely_split"


def ssr_from(row: dict[str, Any] | None, session_built: bool) -> bool | None:
    """Yesterday's SSR from yesterday's index row: on at a whole-day low 10% or more under its prior close."""
    if row is None:
        return False if session_built else None
    low_pct = row.get("low_pct")
    if low_pct is None:
        return None
    return low_pct <= -cfg.SSR_DROP + 1e-12


def select(rows_by_day: dict[str, list[dict[str, Any]]], sessions: dict[str, str | None],
           built: set[str] | None = None) -> list[tuple]:
    """``(d, ticker, prior_close, up10_ts, mover, former_momo, ssr_yesterday)`` for every followed stock-day of
    ``sessions``. Pure: ``rows_by_day`` is the index's rows per session, ``sessions`` each session's ``prev_date``,
    ``built`` every session the index built (a session with no mover is built too); by default the sessions named."""
    built = set(sessions) | set(rows_by_day) if built is None else built
    out: list[tuple] = []
    for day in sorted(sessions):
        prev = sessions.get(day)
        yesterday = {r["symbol"]: r for r in rows_by_day.get(prev or "", [])}
        was_built = prev in built
        today: dict[str, tuple] = {}
        for r in rows_by_day.get(day, []):
            if followed(r):
                sym = r["symbol"]
                was = yesterday.get(sym)
                former = was is not None and followed(was)
                today[sym] = (day, sym, float(r["prev_close"]), int(r["up10_ts"]), True, former,
                              ssr_from(was, was_built))
        for sym, was in yesterday.items():
            if sym in today or not followed(was) or was.get("close") is None:
                continue
            today[sym] = (day, sym, float(was["close"]), None, False, True, ssr_from(was, was_built))
        out += [today[s] for s in sorted(today)]
    return out


def read_index(first: str, last: str) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str | None], set[str]]:
    from day_movers import store

    db = store.read_only()
    if db is None:
        raise SystemExit(f"the day movers index is not built: {store.path()} (research/movers/build_movers.py)")
    db.row_factory = sqlite3.Row
    try:
        sessions = {r["session_date"]: r["prev_date"] for r in db.execute(
            "SELECT session_date, prev_date FROM sessions WHERE session_date BETWEEN ? AND ? ORDER BY session_date",
            (first, last))}
        built = {r[0] for r in db.execute("SELECT session_date FROM sessions")}
        lo = min(sessions, default=first)
        lo = min([lo] + [p for p in sessions.values() if p])       # yesterday of the first day too
        rows: dict[str, list[dict[str, Any]]] = {}
        for r in db.execute("SELECT * FROM movers WHERE session_date BETWEEN ? AND ?", (lo, last)):
            rows.setdefault(r["session_date"], []).append(dict(r))
    finally:
        db.close()
    return rows, sessions, built


def main() -> int:
    from common import connect, load_env

    load_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", type=int, default=cfg.YEARS)
    ap.add_argument("--first", help="the first session (default: --years before the last)")
    ap.add_argument("--last", help="the last session (default: the newest built)")
    a = ap.parse_args()
    last = a.last or date.today().isoformat()
    first = a.first or (date.fromisoformat(last) - timedelta(days=365 * a.years + 2)).isoformat()
    rows, sessions, built = read_index(first, last)
    picked = select(rows, sessions, built)
    con = connect()
    con.execute(SCHEMA)
    con.executemany(f"INSERT INTO {cfg.SELECTION_TABLE} VALUES (?::DATE, ?, ?, ?, ?, ?, ?)", picked)
    days = len({p[0] for p in picked})
    movers = sum(1 for p in picked if p[4])
    print(f"{cfg.SELECTION_TABLE}: {len(picked)} stock-days on {days} sessions ({movers} movers, "
          f"{len(picked) - movers} former momo only), {min(sessions, default='?')} to {max(sessions, default='?')}")
    print(f"next: py -3 research/orb/extract_minutes.py --selection {cfg.SELECTION_TABLE} "
          f"--table {cfg.MINUTES_TABLE} --start {cfg.MINUTES_START}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
