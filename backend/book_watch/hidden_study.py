"""Does a hidden seller (or buyer) say anything about what the price does next? (ADR 033 amendment)

The book watcher's hidden tracker (``hidden.py``) runs over a Session Record's books and prints,
keeping every stretch with a trace of its prints. For one rule (``min_shares``, ``shown_mult``) a
stretch is **flagged** at the first print where it meets the rule -- the moment the ladder would
mark it. A stretch where as much printed but the rule never held -- the book showed enough there to
explain what traded -- is **busy**, measured at the print where it reached ``min_shares``: the same
heavy trading at a price that held, with the size in view. A stretch the book could not follow
(``Stretch.uncertain``) is in neither.

From that moment, over each horizon: did a counted print go through the price (the offer taken out,
the bid broken) at any point, is the mid past the price at the horizon (it gave way and stayed
broken), and where did the mid go, in basis points **toward the break** -- up for an offer, down for
a bid. A horizon that runs past the end of its recorded stretch is not measured, and a
mid needs a book in the same stretch: a gap is never read as a price. Moves are signed by side and
overlap between events, so ``t`` (the mean over its standard error) is a guide, never a proof.

The question for a hidden seller: after an offer took several times what it ever showed, does it
hold -- fewer breaks, the mid not rising -- more often than an offer that took as much and showed it?

Pure apart from the recordings it is handed. Owner of no file; ``tools/hidden_study.py`` prints it.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from book_watch.book import aggregate, lit_print
from book_watch.constants_book_watch import (
    BOOK_WATCH_AUCTION_CONDITIONS,
    BOOK_WATCH_HIDDEN_MIN_HOLD_SEC,
    BOOK_WATCH_HIDDEN_MIN_SHARES,
    BOOK_WATCH_HIDDEN_SHOWN_MULT,
    BOOK_WATCH_HIDDEN_SKIP_CONDITIONS,
    BOOK_WATCH_IDLE_SEC,
)
from book_watch.detector import SymbolWatch
from book_watch.hidden import EPS, HiddenParams, Stretch
from book_watch.replay import feed, merged_rows

SCHEMA_VERSION = 1
HORIZONS_SEC = (10, 30, 60, 300)
GRID_MIN_SHARES = (2000, 5000, 10000, 20000)
GRID_SHOWN_MULT = (2.0, 3.0, 5.0, 10.0)
GRID_MIN_HOLD_SEC = (0.0, 5.0, 10.0, 20.0)
# The run keeps every stretch: no rule fires while it runs, the study applies each afterwards.
_TRACE_ONLY = HiddenParams(min_shares=math.inf)


@dataclass
class Recorded:
    """One recording as the study needs it: its stretches, where the price went, where it was recorded."""

    date: str
    symbol: str
    stretches: list[Stretch]
    mid_ts: list[float]
    mids: list[float]
    spans: list[tuple[float, float]]
    books: int = 0
    prints: int = 0
    first_ts: float | None = None
    last_ts: float | None = None
    depth_sec: float = 0.0        # seconds with a book no older than BOOK_WATCH_IDLE_SEC
    # Counted prints per whole second: (min price, max price) and the prints themselves, for breaks.
    second_range: dict[int, tuple[float, float]] = field(default_factory=dict)
    second_prints: dict[int, list[tuple[float, float]]] = field(default_factory=dict)

    @property
    def depth_hours(self) -> float:
        """Hours the watcher had a fresh book (a stretch recorded without a depth line counts nothing)."""
        return self.depth_sec / 3600.0


def read(directory: Path, *, spans: list[tuple[float, float]] | None = None, num_rows: int = 10) -> Recorded:
    """Run the watcher over one recording directory with every stretch traced."""
    directory = Path(directory)
    history: list[Stretch] = []
    watch = SymbolWatch(directory.name.upper(), num_rows=num_rows, hidden=_TRACE_ONLY, hidden_history=history)
    rec = Recorded(directory.parent.name, directory.name.upper(), history, [], [], [])
    first = last = last_book = None
    for ts, _order, kind, row in merged_rows(directory):
        first = ts if first is None else first
        last = ts
        feed(watch, kind, ts, row)
        if kind == "book":
            rec.books += 1
            if last_book is not None:
                rec.depth_sec += min(ts - last_book, BOOK_WATCH_IDLE_SEC)
            last_book = ts
            bids, asks = aggregate(row.get("bids")), aggregate(row.get("asks"))
            if bids and asks and max(bids) < min(asks):
                rec.mid_ts.append(ts)
                rec.mids.append((max(bids) + min(asks)) / 2)
            continue
        rec.prints += 1
        codes = set(str(row.get("conditions") or ""))
        try:
            price = float(row.get("price"))
        except (TypeError, ValueError):
            continue
        if not lit_print(row) or codes & (BOOK_WATCH_AUCTION_CONDITIONS | BOOK_WATCH_HIDDEN_SKIP_CONDITIONS):
            continue
        sec = int(ts)
        lo, hi = rec.second_range.get(sec, (price, price))
        rec.second_range[sec] = (min(lo, price), max(hi, price))
        rec.second_prints.setdefault(sec, []).append((ts, price))
    watch.flush()
    rec.first_ts, rec.last_ts = first, last
    rec.spans = spans if spans is not None else ([(first, last)] if first is not None else [])
    return rec


def _span_end(rec: Recorded, ts: float) -> float | None:
    for a, b in rec.spans:
        if a <= ts <= b:
            return b
    return None


def _mid(rec: Recorded, ts: float, span_start: float) -> float | None:
    i = bisect.bisect_right(rec.mid_ts, ts) - 1
    if i < 0 or rec.mid_ts[i] < span_start:
        return None
    return rec.mids[i]


def _break_after(rec: Recorded, side: str, price: float, t0: float, limit: float) -> float | None:
    """When a counted print first went through ``price`` after ``t0``, up to ``limit`` seconds on."""
    through = (lambda p: p > price + EPS) if side == "ask" else (lambda p: p < price - EPS)
    for sec in range(int(t0), int(t0 + limit) + 1):
        rng = rec.second_range.get(sec)
        if rng is None or not through(rng[1] if side == "ask" else rng[0]):
            continue
        for ts, p in rec.second_prints[sec]:
            if t0 < ts <= t0 + limit and through(p):
                return ts
    return None


def events(rec: Recorded, min_shares: float, shown_mult: float, min_hold: float = 0.0) -> list[dict[str, Any]]:
    """Every flagged and every busy stretch of one recording under one rule, with what came next.
    ``min_hold``: the price must have held this long since the stretch's first print."""
    out: list[dict[str, Any]] = []
    for st in rec.stretches:
        if st.uncertain is not None or not st.trace:
            continue
        held = [(t, pr, sh) for t, pr, sh in st.trace if t - st.started_ts >= min_hold]
        flag = next(((t, pr, sh) for t, pr, sh in held if pr >= min_shares and pr >= shown_mult * sh), None)
        if flag is not None:
            group, (t0, printed, shown) = "flagged", flag
        else:
            busy = next(((t, pr, sh) for t, pr, sh in held if pr >= min_shares), None)
            if busy is None:
                continue
            group, (t0, printed, shown) = "busy", busy
        end = _span_end(rec, t0)
        if end is None:
            continue
        start = next(a for a, b in rec.spans if a <= t0 <= b)
        mid0 = _mid(rec, t0, start)
        brk = _break_after(rec, st.side, st.price, t0, max(HORIZONS_SEC))
        ev: dict[str, Any] = {
            "date": rec.date, "symbol": rec.symbol, "group": group, "side": st.side, "price": st.price,
            "at": t0, "held_sec": round(t0 - st.started_ts, 3), "printed": printed, "shown_max": shown,
            "ended": st.state,
            "broke_after_sec": None if brk is None else round(brk - t0, 3), "horizons": {},
        }
        for h in HORIZONS_SEC:
            if t0 + h > end:
                continue
            mid1 = _mid(rec, t0 + h, start)
            toward = beyond = None
            if mid0 and mid1:
                move = (mid1 - mid0) / mid0 * 1e4
                toward = move if st.side == "ask" else -move
                beyond = mid1 > st.price + EPS if st.side == "ask" else mid1 < st.price - EPS
            ev["horizons"][str(h)] = {"broke": brk is not None and brk - t0 <= h, "beyond": beyond,
                                      "toward_bp": toward}
        out.append(ev)
    return out


def _stats(values: list[float]) -> dict[str, Any]:
    n = len(values)
    if not n:
        return {"n": 0, "mean": None, "median": None, "t": None}
    mean = sum(values) / n
    med = sorted(values)[n // 2]
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1)) if n > 1 else 0.0
    t = mean / (sd / math.sqrt(n)) if sd > 0 else None
    return {"n": n, "mean": round(mean, 1), "median": round(med, 1), "t": None if t is None else round(t, 2)}


def summarize(evs: list[dict[str, Any]], hours: float) -> dict[str, Any]:
    """Per group and side: how many, how often the price went through, and the move toward it."""
    out: dict[str, Any] = {}
    for group in ("flagged", "busy"):
        for side in ("ask", "bid"):
            rows = [e for e in evs if e["group"] == group and e["side"] == side]
            block: dict[str, Any] = {"n": len(rows), "per_hour": round(len(rows) / hours, 2) if hours else None,
                                     "horizons": {}}
            for h in HORIZONS_SEC:
                measured = [e["horizons"][str(h)] for e in rows if str(h) in e["horizons"]]
                broke = [m["broke"] for m in measured]
                beyond = [m["beyond"] for m in measured if m["beyond"] is not None]
                block["horizons"][str(h)] = {
                    "measured": len(measured),
                    "broke_pct": round(100 * sum(broke) / len(broke), 1) if broke else None,
                    "beyond_pct": round(100 * sum(beyond) / len(beyond), 1) if beyond else None,
                    "toward_bp": _stats([m["toward_bp"] for m in measured if m["toward_bp"] is not None]),
                }
            out[f"{group}_{side}"] = block
    return out


def study(recs: Iterable[Recorded], *, min_shares: float = BOOK_WATCH_HIDDEN_MIN_SHARES,
          shown_mult: float = BOOK_WATCH_HIDDEN_SHOWN_MULT, min_hold: float = BOOK_WATCH_HIDDEN_MIN_HOLD_SEC,
          grid: bool = False) -> dict[str, Any]:
    recs = list(recs)
    hours = sum(r.depth_hours for r in recs)
    evs = [e for r in recs for e in events(r, min_shares, shown_mult, min_hold)]
    by_day: dict[str, list[dict[str, Any]]] = {}
    for e in evs:
        by_day.setdefault(e["date"], []).append(e)
    day_hours = {d: sum(r.depth_hours for r in recs if r.date == d) for d in by_day}
    answer: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "rule": {"min_shares": min_shares, "shown_mult": shown_mult, "min_hold_sec": min_hold},
        "horizons_sec": list(HORIZONS_SEC),
        "recordings": [{"date": r.date, "symbol": r.symbol, "books": r.books, "prints": r.prints,
                        "depth_hours": round(r.depth_hours, 2), "stretches": len(r.stretches)} for r in recs],
        "depth_hours": round(hours, 2),
        "groups": summarize(evs, hours),
        "by_day": {d: summarize(v, day_hours[d]) for d, v in sorted(by_day.items())},
        "events": evs,
    }
    if grid:
        answer["grid"] = [
            {"min_shares": m, "shown_mult": k, "min_hold_sec": h,
             "groups": summarize([e for r in recs for e in events(r, m, k, h)], hours)}
            for h in GRID_MIN_HOLD_SEC for m in GRID_MIN_SHARES for k in GRID_SHOWN_MULT
        ]
    return answer
