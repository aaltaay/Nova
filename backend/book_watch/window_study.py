"""Does the book watcher's matching window call fills "pulled"? (ADR 033 amendment 2026-09-30)

IBKR's depth and its tape arrive separately, so a print that took a level can land outside the matching
window (``matching.py``) and the drop it caused reads as pulled. A wider window claims such a print, but
it also claims prints that only traded at the same price nearby -- a busy price always has one. Over a
Session Record's books and prints this measures both:

1. **The sweep.** The detector with each window in ``WINDOWS_SEC`` either side of a drop's two books
   (judged ``SETTLE_AFTER_SEC`` after it closes): the size filled and pulled, the large pulls, the flags
   and the large drops that traded.
2. **What a wider window adds, against chance.** From the 0.5 s run: the lit prints no drop claimed, and
   the drops with size left pulled. For a window reaching ``EXTENSIONS_SEC`` before the earlier book
   (the print early: the depth trailing the tape) or after the later one (the print late), the size the
   prints there would claim. Then the same prints **moved** by ``SHIFT_SEC`` (to a moment their price
   stood in the same place against the quote; a print no try places is left out of both sides, per
   seed) and moved one tick away from the inside (**tick out**). Every print, real or moved, first meets
   the drop's own 0.5 s window, as an unclaimed print already had. Real less moved is what the window
   misses; moved is what widening would claim by chance.
3. **The evidence test.** Of the lit size at the best bid or ask that no drop claimed, how much had a
   pulled drop at its price shown 0.5-3 s before it (the print late) or 0.5-1 s / 1-3 s after it (the
   print early) -- against the same prints moved. The print-early windows read low for the real prints:
   a drop shown just after a print held that print in its own window.
4. **Depth late, directly.** A lit print through the displayed best price (above the best ask, below the
   best bid; that best level at least ``DEPTH_LATE_MIN_LEVEL``, so an unprotected odd lot proves nothing)
   proves the best level was emptied; how long until a book showed that level smaller or gone.

A print with no book within ``BOOK_WATCH_IDLE_SEC`` either side (the tape kept without a depth line) and a
cross print are left out. Pure apart from the recordings it reads; owner of no file.
``tools/book_watch_window_study.py`` prints it.
"""
from __future__ import annotations

import bisect
import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any, Iterable

from book_watch.book import aggregate, lit_print, price_key, tick_for
from book_watch.constants_book_watch import BOOK_WATCH_AUCTION_CONDITIONS, BOOK_WATCH_IDLE_SEC
from book_watch.detector import SymbolWatch
from book_watch.hidden import HiddenParams
from book_watch.matching import PRICE_EPS, MatchParams, claim
from book_watch.replay import merged_rows

SCHEMA_VERSION = 1
NUM_ROWS = 10
WINDOWS_SEC = (0.5, 1.0, 2.0, 3.0)
BASE_SEC = WINDOWS_SEC[0]
SETTLE_AFTER_SEC = 0.25
EXTENSIONS_SEC = (1.0, 2.0, 3.0)
SHIFT_SEC = (30.0, 60.0)
SHIFT_TRIES = 20
SEEDS = (1, 2)
# t1 (the book that showed the drop) less the print's arrival.
EVIDENCE_SEC = {"print_late_0.5_3": (-3.0, -0.5), "print_early_0.5_1": (0.5, 1.0), "print_early_1_3": (1.0, 3.0)}
DEPTH_LATE_BINS = ((0.5, "<=0.5"), (1.0, "0.5-1"), (3.0, "1-3"), (10.0, "3-10"))
DEPTH_LATE_MIN_LEVEL = 100.0
# No hidden seller fires while the study runs; the tracker only follows its stretches.
_NO_HIDDEN = HiddenParams(min_shares=math.inf)


@dataclass
class Recording:
    """One recording as the study needs it: books with their best prices, prints in arrival order."""

    date: str
    symbol: str
    books: list[tuple[float, list[Any], list[Any]]]
    prints: list[tuple[float, float, float, bool]]   # ts, price key, shares, lit
    book_ts: list[float] = field(default_factory=list)
    bids: list[dict[float, float]] = field(default_factory=list)
    asks: list[dict[float, float]] = field(default_factory=list)
    best_bid: list[float | None] = field(default_factory=list)
    best_ask: list[float | None] = field(default_factory=list)
    cross: int = 0
    tape_only: int = 0

    def __post_init__(self) -> None:
        self.book_ts = [b[0] for b in self.books]
        self.bids = [aggregate(b[1]) for b in self.books]
        self.asks = [aggregate(b[2]) for b in self.books]
        self.best_bid = [max(side) if side else None for side in self.bids]
        self.best_ask = [min(side) if side else None for side in self.asks]

    def covered(self, ts: float) -> bool:
        """A book within ``BOOK_WATCH_IDLE_SEC`` either side of ``ts``."""
        i = bisect.bisect_left(self.book_ts, ts)
        near = min(ts - self.book_ts[i - 1] if i > 0 else math.inf,
                   self.book_ts[i] - ts if i < len(self.book_ts) else math.inf)
        return near <= BOOK_WATCH_IDLE_SEC

    def book_at(self, ts: float) -> int | None:
        i = bisect.bisect_right(self.book_ts, ts) - 1
        return i if i >= 0 else None

    def at_quote(self, ts: float, key: float) -> str | None:
        """'ask' or 'bid' when ``key`` is that side's best price in the latest book, else None."""
        i = self.book_at(ts)
        if i is None:
            return None
        ask, bid = self.best_ask[i], self.best_bid[i]
        if ask is not None and abs(key - ask) <= PRICE_EPS:
            return "ask"
        if bid is not None and abs(key - bid) <= PRICE_EPS:
            return "bid"
        return None

    @property
    def covered_sec(self) -> float:
        return sum(min(b - a, BOOK_WATCH_IDLE_SEC) for a, b in pairwise(self.book_ts))


def read(directory: Path) -> Recording:
    """A recording's books and counted prints (cross prints and tape-only stretches left out)."""
    directory = Path(directory)
    books: list[tuple[float, list[Any], list[Any]]] = []
    raw: list[tuple[float, float, float, bool]] = []
    cross = 0
    for ts, _order, kind, row in merged_rows(directory):
        if kind == "book":
            books.append((ts, row.get("bids") or [], row.get("asks") or []))
            continue
        key = price_key(row.get("price"))
        try:
            shares = float(row.get("size"))
        except (TypeError, ValueError):
            continue
        if key is None or not shares > 0:
            continue
        if set(str(row.get("conditions") or "")) & BOOK_WATCH_AUCTION_CONDITIONS:
            cross += 1
            continue
        raw.append((ts, key, shares, lit_print(row)))
    books.sort(key=lambda b: b[0])
    raw.sort(key=lambda p: p[0])
    rec = Recording(directory.parent.name, directory.name.upper(), books, [], cross=cross)
    rec.prints = [p for p in raw if rec.covered(p[0])] if books else []
    rec.tape_only = len(raw) - len(rec.prints)
    return rec


def _fed(rec: Recording) -> Iterable[tuple[str, tuple]]:
    """Books and prints in arrival order, a book first on a tie (as the replay merges them)."""
    bi = pi = 0
    while bi < len(rec.books) or pi < len(rec.prints):
        if pi >= len(rec.prints) or (bi < len(rec.books) and rec.books[bi][0] <= rec.prints[pi][0]):
            yield "book", rec.books[bi]
            bi += 1
        else:
            yield "print", rec.prints[pi]
            pi += 1


def _new_sweep() -> dict[str, Any]:
    return {"dropped": 0.0, "filled": 0.0, "pulled": 0.0, "large_pulls": 0,
            "flags": {"pulled_on_approach": 0, "repeated_pulls": 0}, "large_drops": 0, "large_traded": 0}


def _count(tot: dict[str, Any], events: list[dict[str, Any]]) -> None:
    for e in events:
        kind = e["event"]
        if kind == "minute":
            tot["filled"] += e["filled_shares"]
            tot["pulled"] += e["pulled_shares"]
            tot["dropped"] += e["filled_shares"] + e["pulled_shares"]
            tot["large_pulls"] += e["large_pulls"]
        elif kind == "flag":
            tot["flags"][e["kind"]] += 1
        elif kind == "drop":
            tot["large_drops"] += 1
            tot["large_traded"] += e["outcome"] == "traded"


def sweep(rec: Recording) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """The detector at every window, and every drop the 0.5 s run judged with the prints it claimed."""
    judged: list[dict[str, Any]] = []
    watches = {w: SymbolWatch(rec.symbol, num_rows=NUM_ROWS, hidden=_NO_HIDDEN,
                              match=MatchParams(w, w, w + SETTLE_AFTER_SEC), judged=judged if w == BASE_SEC else None)
               for w in WINDOWS_SEC}
    totals = {w: _new_sweep() for w in WINDOWS_SEC}
    for kind, item in _fed(rec):
        for w, watch in watches.items():
            if kind == "book":
                _count(totals[w], watch.on_book(item[0], item[1], item[2]))
            else:
                _count(totals[w], watch.on_print(item[0], item[1], item[2], lit=item[3]))
    for w, watch in watches.items():
        _count(totals[w], watch.flush())
    return {f"{w:g}": totals[w] for w in WINDOWS_SEC}, judged


def unclaimed(rec: Recording, judged: list[dict[str, Any]]) -> list[list[float]]:
    """Lit size per (arrival, price) that no drop claimed: ``[ts, price, shares left]``, in arrival order."""
    size: dict[tuple[float, float], float] = defaultdict(float)
    for ts, key, shares, lit in rec.prints:
        if lit:
            size[(ts, key)] += shares
    for d in judged:
        for ts, key, take in d["claims"]:
            size[(ts, key)] -= take
    return sorted([ts, key, left] for (ts, key), left in size.items() if left > 1e-9)


def _moved(rec: Recording, rows: list[list[float]], seed: int) -> list[float | None]:
    """Each row's arrival moved by ``SHIFT_SEC`` either way to a moment with a book near and its price in the
    same place against the quote (at the ask, at the bid, or neither); None when no try did."""
    rng = random.Random(seed)
    lo, hi = SHIFT_SEC
    out: list[float | None] = []
    for ts, key, _left in rows:
        where = rec.at_quote(ts, key)
        got = None
        for _ in range(SHIFT_TRIES):
            t = ts + rng.uniform(lo, hi) * (1 if rng.random() < 0.5 else -1)
            if rec.covered(t) and rec.at_quote(t, key) == where:
                got = t
                break
        out.append(got)
    return out


def _tick_out(rec: Recording, rows: list[list[float]], seed: int) -> list[list[float]]:
    """Each row one tick away from the inside on its own side (either way when at neither), same arrival."""
    rng = random.Random(seed)
    out = []
    for ts, key, left in rows:
        where = rec.at_quote(ts, key)
        sign = 1 if where == "ask" else -1 if where == "bid" else (1 if rng.random() < 0.5 else -1)
        out.append([ts, round(key + sign * tick_for(key), 6), left])
    return out


def extend(judged: list[dict[str, Any]], pool: list[list[float]], before: float, after: float) -> float:
    """Size the pool fills for the pulled drops, in judge order: first inside each drop's own 0.5 s
    window, then the extra reach -- ``before`` s before its earlier book, ``after`` s after its later one.
    Only the extra reach is counted. ``pool`` is ``[ts, price, shares left]`` (consumed)."""
    by_price: dict[float, list[list[float]]] = defaultdict(list)
    for row in sorted(pool):
        by_price[row[1]].append(row)
    arrivals = {k: [r[0] for r in v] for k, v in by_price.items()}
    got = 0.0
    for d in judged:
        need, rows = d["pulled"], by_price.get(d["price"])
        if need <= 0 or not rows:
            continue
        t0, t1, price, ts = d["t0"], d["t1"], d["price"], arrivals[d["price"]]
        for start, end, counted in ((t0 - BASE_SEC, t1 + BASE_SEC, False), (t0 - before, t0 - BASE_SEC, True),
                                    (t1 + BASE_SEC, t1 + after, True)):
            if end <= start or need <= 0:
                continue
            span = rows[bisect.bisect_right(ts, start):bisect.bisect_right(ts, end)]
            took = claim(span, start, end, price, need)
            need -= took
            got += took if counted else 0.0
    return got


def _evidence(rows: list[list[float]], pulled_t1: dict[float, list[float]]) -> dict[str, float]:
    out = {"volume": 0.0, **{k: 0.0 for k in EVIDENCE_SEC}}
    for ts, key, left in rows:
        out["volume"] += left
        t1s = pulled_t1.get(key) or []
        for name, (a, b) in EVIDENCE_SEC.items():
            if a < 0:
                i = bisect.bisect_left(t1s, ts + a)
                hit = i < len(t1s) and t1s[i] < ts + b
            else:
                i = bisect.bisect_right(t1s, ts + a)
                hit = i < len(t1s) and t1s[i] <= ts + b
            out[name] += left if hit else 0.0
    return out


def depth_late(rec: Recording) -> dict[str, int]:
    """Lit prints through the displayed best price, by how long a book took to show that level emptied."""
    out = {"through": 0, **{name: 0 for _, name in DEPTH_LATE_BINS}, "never": 0}
    for ts, key, _shares, lit in rec.prints:
        i = rec.book_at(ts) if lit else None
        if i is None:
            continue
        ask, bid = rec.best_ask[i], rec.best_bid[i]
        if ask is None or bid is None or ask <= bid:
            continue
        if key > ask + PRICE_EPS:
            best, levels = ask, rec.asks
        elif key < bid - PRICE_EPS:
            best, levels = bid, rec.bids
        else:
            continue
        shown = levels[i].get(best, 0.0)
        if shown < DEPTH_LATE_MIN_LEVEL:
            continue
        out["through"] += 1
        limit = DEPTH_LATE_BINS[-1][0]
        lag = None
        for j in range(i + 1, len(rec.books)):
            if rec.book_ts[j] > ts + limit:
                break
            if levels[j].get(best, 0.0) < shown:
                lag = rec.book_ts[j] - ts
                break
        name = "never" if lag is None else next(n for edge, n in DEPTH_LATE_BINS if lag <= edge)
        out[name] += 1
    return out


def measure(rec: Recording) -> dict[str, Any]:
    """Every measure for one recording."""
    swept, judged = sweep(rec)
    pool = unclaimed(rec, judged)
    pulled_t1: dict[float, list[float]] = defaultdict(list)
    for d in judged:
        if d["pulled"] > 0:
            pulled_t1[d["price"]].append(d["t1"])
    for t1s in pulled_t1.values():
        t1s.sort()
    ext: dict[str, Any] = {"pulled": sum(d["pulled"] for d in judged), "before": {}, "after": {}}
    reach = [("before", s, s, BASE_SEC) for s in EXTENSIONS_SEC] + [("after", s, BASE_SEC, s) for s in EXTENSIONS_SEC]
    for side, s, before, after in reach:
        ext[side][f"{s:g}"] = {"real": extend(judged, [list(r) for r in pool], before, after),
                               "moved_real": 0.0, "moved": 0.0,
                               "tick_out": extend(judged, _tick_out(rec, pool, SEEDS[0]), before, after)}
    at_quote = [r for r in pool if rec.at_quote(r[0], r[1])]
    evidence = {"real": {"volume": 0.0, **{k: 0.0 for k in EVIDENCE_SEC}},
                "moved": {"volume": 0.0, **{k: 0.0 for k in EVIDENCE_SEC}}}
    for seed in SEEDS:
        moved = _moved(rec, pool, seed)
        kept = [(r, t) for r, t in zip(pool, moved, strict=True) if t is not None]
        real_rows = [list(r) for r, _t in kept]
        moved_rows = [[t, r[1], r[2]] for r, t in kept]
        for side, s, before, after in reach:
            cell = ext[side][f"{s:g}"]
            cell["moved_real"] += extend(judged, [list(r) for r in real_rows], before, after) / len(SEEDS)
            cell["moved"] += extend(judged, [list(r) for r in moved_rows], before, after) / len(SEEDS)
        moved = _moved(rec, at_quote, seed + len(SEEDS))
        kept = [(r, t) for r, t in zip(at_quote, moved, strict=True) if t is not None]
        for group, rows in (("real", [r for r, _t in kept]), ("moved", [[t, r[1], r[2]] for r, t in kept])):
            for k, v in _evidence(rows, pulled_t1).items():
                evidence[group][k] += v / len(SEEDS)
    return {"sweep": swept, "extension": ext, "evidence": evidence, "depth_late": depth_late(rec)}


def _add(into: Any, more: Any) -> Any:
    """Sum two measures of the same shape (numbers add, dicts add key by key)."""
    if isinstance(more, dict):
        into = {} if into is None else into
        for k, v in more.items():
            into[k] = _add(into.get(k), v)
        return into
    return (into or 0) + more


def study(recs: Iterable[tuple[Recording, dict[str, Any]]]) -> dict[str, Any]:
    """Per recording, per day and in all: ``recs`` pairs each recording with its ``measure``."""
    rows, by_day, total = [], {}, None
    for rec, m in recs:
        rows.append({"date": rec.date, "symbol": rec.symbol, "books": len(rec.books),
                     "books_per_sec": round(len(rec.books) / rec.covered_sec, 2) if rec.covered_sec else None,
                     "prints": len(rec.prints), "left_out": {"cross": rec.cross, "tape_only": rec.tape_only}, **m})
        by_day[rec.date] = _add(by_day.get(rec.date), m)
        total = _add(total, m)
    return {"schema_version": SCHEMA_VERSION, "windows_sec": list(WINDOWS_SEC), "extensions_sec": list(EXTENSIONS_SEC),
            "shift_sec": list(SHIFT_SEC), "seeds": list(SEEDS), "recordings": rows,
            "by_day": dict(sorted(by_day.items())), "total": total}
