"""Does a level a print traded through read traded, and is the rule right? (#636, ADR 033 amendment)

IBKR's book can trail its tape. A lit print above the best ask (below the best bid) proves the size the
book showed at the round-lot levels from the best to its price traded, yet the book may show it for
seconds more; its drop then lands after the prints that took it, and the matching window alone calls it
pulled. The detector's sweep rule (``matching.Sweeps``) lets such a drop take the sweep's own prints
first, at most the size the sweep proved taken, until the book shows new size posted there. Over a
Session Record this measures, always with the detector itself:

1. **The rule's effect.** The detector at the 0.5 s window with the rule off and on: the size filled and
   pulled, the large pulls, the flags and the large drops that traded.
2. **Its precision, against chance.** The detector with its own sweeps off (``Sweeps.auto``), fed sweeps
   the study places at the moment of each of their prints: the real ones; the same **moved** 30-60 s, to
   a moment their best price stood as the best on that side again (a sweep no try places is left out of
   both, per seed); and the level one tick **beyond** where each sweep stopped, at its own moments (a
   level it did not take, at the same busy second). What each adds to the size filled, against the
   detector without the rule, is what the rule claims there; moved and beyond are chance.
3. **The levels it proves.** Every drop the rule let take a sweep's prints: its size, and how much of it
   read traded without the rule and with it.

A sweep is the detector's own trigger (``matching.swept_levels`` on a book no older than
``BOOK_WATCH_IDLE_SEC``, skipping ``BOOK_WATCH_SWEEP_SKIP_CONDITIONS``); the prints of one sweep that
arrive within ``SWEEP_JOIN_SEC`` of its first, through the same best price, are one sweep. Pure apart
from the recordings it reads; owner of no file. ``tools/book_watch_window_study.py`` prints it.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from book_watch.book import tick_for
from book_watch.constants_book_watch import BOOK_WATCH_IDLE_SEC, BOOK_WATCH_SWEEP_HOLD_SEC, BOOK_WATCH_SWEEP_SKIP_CONDITIONS
from book_watch.detector import SymbolWatch
from book_watch.matching import MatchParams, swept_levels
from book_watch.window_study import NO_HIDDEN, NUM_ROWS, SEEDS, SHIFT_SEC, SHIFT_TRIES, Recording, count_events, fed, new_totals

SWEEP_JOIN_SEC = 1.0

Placed = tuple[float, str, tuple[float, ...]]  # when, the side, the levels


@dataclass
class Sweep:
    """One sweep: when its first print arrived, the side it took, the best price then and the levels."""

    ts: float
    side: str
    best: float
    prices: set[float]
    times: list[float]

    def placed(self, shift: float = 0.0) -> list[Placed]:
        levels = tuple(sorted(self.prices))
        return [(ts + shift, self.side, levels) for ts in self.times]

    def beyond(self) -> list[Placed]:
        """The level one tick past where the sweep stopped (above its last price on the ask, below it on
        the bid), at the sweep's own moments: a level it did not take."""
        last = max(self.prices) if self.side == "ask" else min(self.prices)
        step = tick_for(last) if self.side == "ask" else -tick_for(last)
        return [(ts, self.side, (round(last + step, 6),)) for ts in self.times]


def sweeps(rec: Recording) -> list[Sweep]:
    """Every sweep in the recording, as the detector's trigger sees it."""
    out: list[Sweep] = []
    last: dict[str, Sweep] = {}
    for ts, key, _shares, lit, conditions in rec.prints:
        if not lit or set(conditions) & BOOK_WATCH_SWEEP_SKIP_CONDITIONS:
            continue
        i = rec.book_at(ts)
        if i is None or ts - rec.book_ts[i] > BOOK_WATCH_IDLE_SEC:
            continue
        found = swept_levels(key, rec.views(i))
        if found is None:
            continue
        side, prices = found
        best = prices[0] if side == "ask" else prices[-1]
        prev = last.get(side)
        if prev is not None and prev.best == best and ts - prev.ts <= SWEEP_JOIN_SEC:
            prev.prices.update(prices)  # the same sweep's next print
            prev.times.append(ts)
            continue
        last[side] = Sweep(ts, side, best, set(prices), [ts])
        out.append(last[side])
    return out


def run(rec: Recording, hold: float, placed: list[Placed] | None = None) -> tuple[dict[str, Any], list[dict]]:
    """The detector at the 0.5 s window with the sweep rule held ``hold`` seconds (0: off). With
    ``placed``, the detector finds no sweep itself and is given those, each marked right after the
    recording's last event at or before its moment."""
    judged: list[dict] = []
    watch = SymbolWatch(rec.symbol, num_rows=NUM_ROWS, hidden=NO_HIDDEN, match=MatchParams(sweep_hold_sec=hold),
                        judged=judged)
    marks = sorted(placed or [], key=lambda m: m[0])
    if placed is not None:
        watch.sweeps.auto = False
    totals, j = new_totals(), 0
    for kind, item in fed(rec):
        t = item[0]
        while j < len(marks) and marks[j][0] < t:
            watch.sweeps.mark(*marks[j], watch.prev)
            j += 1
        if kind == "book":
            count_events(totals, watch.on_book(item[0], item[1], item[2]))
        else:
            count_events(totals, watch.on_print(item[0], item[1], item[2], lit=item[3], conditions=item[4]))
        while j < len(marks) and marks[j][0] <= t:
            watch.sweeps.mark(*marks[j], watch.prev)
            j += 1
    count_events(totals, watch.flush())
    return totals, judged


def _moved(rec: Recording, found: list[Sweep], seed: int) -> list[float | None]:
    """Each sweep moved by ``SHIFT_SEC`` either way to a moment its best price was the best on its side."""
    rng = random.Random(seed)
    lo, hi = SHIFT_SEC
    out: list[float | None] = []
    for s in found:
        got = None
        for _ in range(SHIFT_TRIES):
            t = s.ts + rng.uniform(lo, hi) * (1 if rng.random() < 0.5 else -1)
            if rec.covered(t) and rec.at_quote(t, s.best) == s.side:
                got = t
                break
        out.append(got)
    return out


def measure(rec: Recording, hold: float = BOOK_WATCH_SWEEP_HOLD_SEC) -> dict[str, Any]:
    """Every measure of the sweep rule for one recording."""
    off, judged_off = run(rec, 0.0)
    on, judged_on = run(rec, hold)
    found = sweeps(rec)
    filled_off = {(d["side"], d["price"], d["t1"]): d["filled"] for d in judged_off}
    covered = {"drops": 0, "dropped": 0.0, "filled_off": 0.0, "filled_on": 0.0}
    for d in judged_on:
        if d["allow"] <= 0:
            continue
        covered["drops"] += 1
        covered["dropped"] += d["drop"]
        covered["filled_off"] += filled_off.get((d["side"], d["price"], d["t1"]), 0.0)
        covered["filled_on"] += d["filled"]

    def gain(placed: list[Placed]) -> float:
        return run(rec, hold, placed)[0]["filled"] - off["filled"]

    got = {"real": on["filled"] - off["filled"], "matched_real": 0.0, "moved": 0.0,
           "beyond": gain([m for s in found for m in s.beyond()])}
    for seed in SEEDS:
        kept = [(s, t) for s, t in zip(found, _moved(rec, found, seed), strict=True) if t is not None]
        got["matched_real"] += gain([m for s, _t in kept for m in s.placed()]) / len(SEEDS)
        got["moved"] += gain([m for s, t in kept for m in s.placed(t - s.ts)]) / len(SEEDS)
    return {"sweeps": len(found), "levels": sum(len(s.prices) for s in found),
            "pulled_off": sum(d["pulled"] for d in judged_off), "off": off, "on": on,
            "covered": covered, "reach": got}
