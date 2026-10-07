"""Nova's LULD bands against the pauses its own Session Records caught (ADR 047): ``tools/luld_check.py records``.

Read-only. A Session Record holds IBKR's tape and book -- the live desk's own data -- but no band, so
the truth is where the quote sat for the 15 s before each LULD pause in the halt log: the best offer
for a pause on the way down, the best bid on the way up. Each recorded day replays through
``Tracker`` with the desk's options, and only pauses whose 5 minutes before are on the tape count.
"""
from __future__ import annotations

import sqlite3

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from luld.study import et
from luld.tracker import Facts, Tracker

logger = logging.getLogger(__name__)
LULD_PAUSE_CODES = ("LUDP", "LUDS", "M")


def _rows(path: Path) -> list[dict[str, Any]]:
    out = []
    if not path.is_file():
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _pauses(day: str, symbol: str) -> tuple[list[float], list[tuple[float, bool]]]:
    """The halt log's LULD pause starts, and the halts the replay feeds (IBKR's tick 49, else Nasdaq's)."""
    from leaderboard import store

    db = store.read_only()
    if db is None:
        return [], []
    db.row_factory = sqlite3.Row   # halt_events reads rows by name
    try:
        rows = store.halt_events(db, day, symbols=[symbol])
    finally:
        db.close()
    starts = sorted({r["ts"] for r in rows if r["source"] == "nasdaq_trade_halt_rss" and r["event"] == "start"
                     and (r.get("code") or "") in LULD_PAUSE_CODES})
    ibkr = [(r["ts"], r["event"] == "start") for r in rows if r["source"] == "ibkr_ticker_halted"]
    rss = [(r["ts"], r["event"] == "start") for r in rows if r["source"] == "nasdaq_trade_halt_rss"]
    return starts, sorted(ibkr or rss)


def check(day: str, symbol: str, root: Path) -> list[dict[str, Any]]:
    """Each LULD pause the recording covers: where the quote sat, and the band Nova had then."""
    from sale_conditions import row_sets_price
    from sim.prior_close import previous_close, recorded_close

    folder = root / day / symbol
    prints = [p for p in _rows(folder / "prints.jsonl") if p.get("price")]
    quotes = _rows(folder / "quotes.jsonl")
    starts, halts = _pauses(day, symbol)
    if not prints or not starts:
        return []
    events = [(float(p["ts"]), 0, p) for p in prints] + [(float(q["ts"]), 1, q) for q in quotes]
    events.sort(key=lambda e: (e[0], e[1]))
    first, last = events[0][0], events[-1][0]
    covered = [h for h in starts if first < h <= last + 2.0]
    if not covered:
        return []
    prev = previous_close(symbol, day, recorded=recorded_close(quotes, day))
    if prev is None:
        # No previous close on file for the replay (#542): the check takes the Massive day aggregates'.
        from luld.study import massive_prev_close

        prev = massive_prev_close(day, [symbol]).get(symbol)
    tracker = Tracker(symbol, started_at=events[0][0], facts=Facts(prev_close=prev, tier=2))
    out, hi, pending = [], 0, list(covered)
    for ts, kind, row in events:
        while hi < len(halts) and halts[hi][0] <= ts:
            tracker.on_halt(halts[hi][0], halts[hi][1])
            hi += 1
        while pending and pending[0] - 0.5 <= ts:
            out.append(_judge(day, symbol, pending.pop(0), tracker, quotes))
        if kind == 0:
            tracker.on_print(ts, float(row["price"]), eligible=row_sets_price(row),
                             conditions=row.get("conditions") or "", exchange=row.get("exchange") or "")
        else:
            tracker.on_quote(ts, row.get("bid"), row.get("ask"))
    for h in pending:
        out.append(_judge(day, symbol, h, tracker, quotes))
    return out


def _judge(day: str, symbol: str, h: float, tracker: Tracker, quotes: list[dict]) -> dict[str, Any]:
    v = tracker.view(h - 0.5)
    window = [q for q in quotes if h - 15.5 <= float(q["ts"]) <= h and q.get("bid") and q.get("ask")]
    bids = Counter(round(float(q["bid"]), 2) for q in window)
    asks = Counter(round(float(q["ask"]), 2) for q in window)
    lo, up = v["lower"], v["upper"]
    last = v["last"]
    side = None
    if lo is not None and up is not None and last is not None:
        side = "down" if abs(last - lo) < abs(last - up) else "up"
    pinned = (asks if side == "down" else bids).most_common(1)[0][0] if side and window else None
    band = lo if side == "down" else up
    return {"day": day, "symbol": symbol, "pause": et(h), "side": side, "pinned": pinned, "band": band,
            "miss_c": None if pinned is None or band is None else round((band - pinned) * 100),
            "exact": v["exact"], "source": v["reference_source"],
            "limit_seen": v["limit"] is not None, "limit_since": et(v["limit"]["since"]) if v["limit"] else None}


def check_all(root: Path | None = None) -> list[dict[str, Any]]:
    from capture.recorder import capture_root

    base = root or capture_root()
    out: list[dict[str, Any]] = []
    for day_dir in sorted(p for p in base.iterdir() if p.is_dir() and p.name[:2] == "20"):
        for sym_dir in sorted(p for p in day_dir.iterdir() if p.is_dir()):
            try:
                out += check(day_dir.name, sym_dir.name, base)
            except Exception:  # maintainer: allow-swallow one unreadable recording is reported, the rest still read
                logger.warning("LULD records: could not read %s %s", day_dir.name, sym_dir.name, exc_info=True)
    return out
