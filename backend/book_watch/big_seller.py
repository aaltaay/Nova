"""A big seller on the ask, a big buyer on the bid (ADR 033 amendment, operator ask 2026-10-12, #846).

From the held Level 2 line only. A price on one side is **big** when its resting size (summed across
venues, wholly in view) is at least ``BOOK_WATCH_BIG_MIN_SHARES`` shares and
``BOOK_WATCH_BIG_MIN_DOLLARS`` dollars and ``BOOK_WATCH_BIG_MEDIAN_MULT`` x the median of the other
levels in view on its side (at least ``BOOK_WATCH_BIG_MIN_OTHER_LEVELS`` of them), at or just over the
price for an ask -- just under it for a bid -- no further than the window (``BigParams.window``). The
price is the last print that sets one, else the middle of the inside. It is **called** a big seller (a
big buyer) once it has stayed big ``BOOK_WATCH_BIG_MIN_HOLD_SEC``.

A called price is followed through its life:

- ``holding``: the book still shows at least the floors there (whatever the other levels do since).
- ``left``: the book showed it fall under the floors; it is judged ``settle_sec`` later, as the
  watcher judges every drop (``matching.py``), so a print that arrives after the book still counts.
- ``eaten`` (said "taken"): a lit, price-setting print went through it (over a seller, under a buyer):
  a displayed price cannot be traded through, so its size traded (``how: "through"``); or lit prints at
  its price inside the matching window cover at least ``BOOK_WATCH_BIG_TAKEN_SHARE`` of the drop
  (``how: "traded"``). Either way the seller is gone.
- ``pulled``: it left and the prints at its price do not cover that share (``how: "no_prints"``) --
  ``on_approach`` when the price was closer to it as it left than when it was called.
- ``lost``: the book stopped showing that price -- it scrolled past the rows shown, the side collapsed
  at once, the book restarted: unknown, never pulled.

A price called where one on its side was pulled in the last ``BOOK_WATCH_BIG_BACK_SEC`` carries ``back``
(how many, when the last left) -- never a claim that it is the same seller. Each wall's ``clear_sec`` is
its size over the lit shares printed in the last ``BOOK_WATCH_BIG_PACE_SEC`` (#984).

Prints that prove nothing about the book -- off-exchange reports, crosses, volume-only prints and odd
lots (``BOOK_WATCH_SWEEP_SKIP_CONDITIONS``) -- never take one. The tracker keeps its own copy of the lit
prints, so its claims never touch the watcher's drop judgments. One order and several orders at one
price look the same here; a description of the book, never an order, a stop move or a gate.

Pure: books (as ``book.SideView`` pairs) and prints in, ``big`` events out -- one when a price is
called and one when it ends; ``reading`` is the state at a moment.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import median
from typing import Any

from book_watch.book import SideView, collapsed, in_view
from book_watch.constants_book_watch import (
    BOOK_WATCH_BIG_BACK_SEC,
    BOOK_WATCH_BIG_KEEP,
    BOOK_WATCH_BIG_MEDIAN_MULT,
    BOOK_WATCH_BIG_MIN_DOLLARS,
    BOOK_WATCH_BIG_MIN_HOLD_SEC,
    BOOK_WATCH_BIG_MIN_OTHER_LEVELS,
    BOOK_WATCH_BIG_MIN_SHARES,
    BOOK_WATCH_BIG_SHOW_ENDED_SEC,
    BOOK_WATCH_BIG_TAKEN_SHARE,
    BOOK_WATCH_BIG_WINDOW_DOLLARS,
    BOOK_WATCH_BIG_WINDOW_MAX_PCT,
    BOOK_WATCH_BIG_WINDOW_PCT,
    BOOK_WATCH_PRINT_KEEP_SEC,
    BOOK_WATCH_SWEEP_HOLD_SEC,
    BOOK_WATCH_SWEEP_SKIP_CONDITIONS,
)
from book_watch.matching import DEFAULT_MATCH, PRICE_EPS, MatchParams, claim
from book_watch.pace import LitPace
from sale_conditions import sets_price

SIDES = ("ask", "bid")
KIND = {"ask": "big_seller", "bid": "big_buyer"}
HOLDING, LEFT, EATEN, PULLED, LOST = "holding", "left", "eaten", "pulled", "lost"


@dataclass(frozen=True)
class BigParams:
    min_shares: float = BOOK_WATCH_BIG_MIN_SHARES
    min_dollars: float = BOOK_WATCH_BIG_MIN_DOLLARS
    median_mult: float = BOOK_WATCH_BIG_MEDIAN_MULT
    min_other_levels: int = BOOK_WATCH_BIG_MIN_OTHER_LEVELS
    min_hold_sec: float = BOOK_WATCH_BIG_MIN_HOLD_SEC
    window_dollars: float = BOOK_WATCH_BIG_WINDOW_DOLLARS
    window_pct: float = BOOK_WATCH_BIG_WINDOW_PCT
    window_max_pct: float = BOOK_WATCH_BIG_WINDOW_MAX_PCT
    taken_share: float = BOOK_WATCH_BIG_TAKEN_SHARE
    show_ended_sec: float = BOOK_WATCH_BIG_SHOW_ENDED_SEC
    back_sec: float = BOOK_WATCH_BIG_BACK_SEC

    def floor(self, price: float) -> float:
        """The fewest shares at ``price`` that are big: the share floor, or the dollar floor's shares."""
        return max(self.min_shares, self.min_dollars / price)

    def window(self, ref: float) -> float:
        """How far past the price a big size may sit: the larger of the cents and the percent, capped."""
        return min(max(self.window_dollars, self.window_pct * ref), self.window_max_pct * ref)


DEFAULT_BIG = BigParams()


@dataclass
class Wall:
    """One price on one side: a candidate until it has held, then called, then ended."""

    side: str
    price: float
    first_ts: float               # first seen big
    first_size: float
    from_start: bool              # big in the first book the tracker saw: it may have been there longer
    size_now: float = 0.0
    peak: float = 0.0
    traded: float = 0.0           # lit prints at its price since first seen
    median: float | None = None   # the other levels' median when it was called
    called_size: float | None = None
    called_ts: float | None = None
    dist_called: float | None = None  # how far past the price when it was called
    back: dict[str, float] | None = None  # walls pulled at this price shortly before it was called
    on_approach: bool | None = None  # pulled as the price came closer; None unless pulled
    state: str = HOLDING
    ended_ts: float | None = None
    how: str | None = None
    left: dict[str, float] | None = None
    ref_at_end: float | None = None


def _distance(side: str, price: float, ref: float | None) -> float | None:
    """How far past the price: over it for an ask, under it for a bid (0 or less: at the price)."""
    if ref is None:
        return None
    return round(price - ref if side == "ask" else ref - price, 6)


class BigWallTracker:
    def __init__(self, symbol: str, *, params: BigParams = DEFAULT_BIG, match: MatchParams = DEFAULT_MATCH) -> None:
        self.symbol = symbol
        self.p = params
        self.match = match
        self.walls: dict[str, dict[float, Wall]] = {s: {} for s in SIDES}
        self.ended: deque[Wall] = deque(maxlen=BOOK_WATCH_BIG_KEEP)
        self.pending: list[dict[str, Any]] = []
        self.prints: deque[list[float]] = deque()  # [ts, price, shares left to claim], lit and meaningful
        self.last: float | None = None
        self.last_ts: float | None = None
        self.views: dict[str, SideView] | None = None
        self.prev_ts: float | None = None
        self.fresh = True                          # the next book is the first since start or a reset
        self.levels = {s: 0 for s in SIDES}        # levels wholly in view on each side, last book
        # (side, price) a print went through -> when: IBKR's book can trail its tape and show the size there for
        # seconds more, so no new candidate starts there until the book shows it gone or the sweep hold passes.
        self.spent: dict[tuple[str, float], float] = {}
        self.pace = LitPace()                            # how fast it trades, for clear_sec (pace.py)
        self.version = 0                                 # moves whenever a called wall says something new

    # -- input ---------------------------------------------------------------

    def on_book(self, ts: float, views: dict[str, SideView],
                prev: dict[str, SideView] | None) -> list[dict[str, Any]]:
        out = self.tick(ts)
        self.pace.on_book(ts)
        ref = self._reference(views)
        for side in SIDES:
            view = views[side]
            shown = {px: sz for px, sz in view.levels.items() if in_view(px, side, view.cutoff)}
            self.levels[side] = len(shown)
            if prev is not None and collapsed(prev[side], view):
                out += self._lose_side(side, ts, "collapsed")  # a reset or a glitch: that side is unknown
                continue
            out += self._follow(side, ts, view, shown)
            for price, size in shown.items():
                if price in self.walls[side] or self._spent(side, price, size, ts):
                    continue
                if self._big(side, price, size, shown, ref) is not None:
                    self.walls[side][price] = Wall(side, price, ts, size, self.fresh, size_now=size, peak=size)
            out += self._call_due(side, ts, shown, ref)
        self.views, self.prev_ts, self.fresh = views, ts, False
        return out

    def on_print(self, ts: float, key: float, shares: float, *, lit: bool, conditions: Any) -> list[dict[str, Any]]:
        codes = str(conditions or "")
        ref = self._reference(self.views)  # the price before this print: how far past it a taken one sat
        if sets_price(codes):
            self.last, self.last_ts = key, ts
        out = self.tick(ts)
        self.pace.on_print(ts, shares, lit=lit, conditions=codes)
        if not lit or set(codes) & BOOK_WATCH_SWEEP_SKIP_CONDITIONS:
            return out
        self.prints.append([ts, key, shares])
        while self.prints and self.prints[0][0] < ts - BOOK_WATCH_PRINT_KEEP_SEC:
            self.prints.popleft()
        for side in SIDES:
            for price, wall in list(self.walls[side].items()):
                through = key > price + PRICE_EPS if side == "ask" else key < price - PRICE_EPS
                if through:
                    self.spent[(side, price)] = ts
                    if wall.called_ts is None:
                        del self.walls[side][price]  # traded through before it held: no seller there
                    else:
                        out += self._end(wall, EATEN, ts, "through", ref=ref)
                elif abs(key - price) <= PRICE_EPS:
                    wall.traded += shares
                    if wall.called_ts is not None:
                        self.version += 1
        return out

    def tick(self, now: float) -> list[dict[str, Any]]:
        """Judge every price that left the book once its settle time has passed."""
        out: list[dict[str, Any]] = []
        due = [d for d in self.pending if d["deadline"] <= now]
        if not due:
            return out
        self.pending = [d for d in self.pending if d["deadline"] > now]
        before, after = self.match.before_sec, self.match.after_sec
        for d in due:
            wall = d["wall"]
            if wall.state != LEFT:
                continue  # a print went through it first
            filled = claim(self.prints, d["t0"] - before, d["t1"] + after, wall.price, d["drop"])
            wall.left = {"before": d["before"], "after": d["after"], "filled": filled}
            taken = filled >= self.p.taken_share * d["drop"]
            out += self._end(wall, EATEN if taken else PULLED, d["t1"], "traded" if taken else "no_prints")
        return out

    def reset(self, ts: float | None) -> list[dict[str, Any]]:
        """The book restarted: no price it showed can be followed across it."""
        out: list[dict[str, Any]] = []
        for side in SIDES:
            out += self._lose_side(side, ts if ts is not None else (self.prev_ts or 0.0), "reset")
        self.views, self.fresh = None, True
        self.spent.clear()
        self.pace.reset()
        return out

    def lose_waiting(self, how: str) -> list[dict[str, Any]]:
        """Every wall that left and still waits on its prints, lost where it left: the tape that would judge it is
        missing (a recording gap, ``hidden_study.read``; never live, where the tape runs on past a book restart)."""
        waiting, self.pending = self.pending, []
        return [e for d in waiting if d["wall"].state == LEFT for e in self._end(d["wall"], LOST, d["t1"], how)]

    # -- the rule ------------------------------------------------------------

    def _reference(self, views: dict[str, SideView] | None) -> float | None:
        if self.last is not None:
            return self.last
        if views is None or views["ask"].best is None or views["bid"].best is None:
            return None
        return (views["ask"].best + views["bid"].best) / 2

    def _big(self, side: str, price: float, size: float, shown: dict[float, float],
             ref: float | None) -> float | None:
        """The other levels' median when ``price`` is big and in the window, else None."""
        if ref is None or size < self.p.floor(price):
            return None
        dist = _distance(side, price, ref)
        if dist is None or dist > self.p.window(ref) + PRICE_EPS:
            return None
        others = [sz for px, sz in shown.items() if px != price]
        if len(others) < self.p.min_other_levels:
            return None
        med = float(median(others))
        return med if size >= self.p.median_mult * med else None

    def _spent(self, side: str, price: float, size: float, ts: float) -> bool:
        """A print went through ``price`` and the book may not show it yet: not a new candidate."""
        at = self.spent.get((side, price))
        if at is None:
            return False
        if size < self.p.floor(price) or ts - at > BOOK_WATCH_SWEEP_HOLD_SEC:
            del self.spent[(side, price)]
            return False
        return True

    def _follow(self, side: str, ts: float, view: SideView, shown: dict[float, float]) -> list[dict[str, Any]]:
        """Each followed price against the new book: still there, left, or out of view."""
        out: list[dict[str, Any]] = []
        for price, wall in list(self.walls[side].items()):
            if wall.state == LEFT:
                continue
            if not in_view(price, side, view.cutoff):
                # Scrolled past the rows shown, or at the edge of them: unknown, never pulled.
                if wall.called_ts is None:
                    del self.walls[side][price]
                else:
                    out += self._end(wall, LOST, ts, "cut_off")
                continue
            size = shown.get(price, 0.0)
            if size < self.p.floor(price):
                if wall.called_ts is None:
                    del self.walls[side][price]
                    continue
                wall.state = LEFT
                self.pending.append({"wall": wall, "t0": self.prev_ts if self.prev_ts is not None else ts, "t1": ts,
                                     "before": wall.size_now, "after": size, "drop": wall.size_now - size,
                                     "deadline": ts + self.match.settle_sec})
                continue
            if wall.called_ts is not None and size != wall.size_now:
                self.version += 1
            wall.size_now = size
            wall.peak = max(wall.peak, size)
        return out

    def _call_due(self, side: str, ts: float, shown: dict[float, float], ref: float | None) -> list[dict[str, Any]]:
        """Every candidate that has stayed big long enough is called; one that no longer is, forgotten."""
        out: list[dict[str, Any]] = []
        for price, wall in list(self.walls[side].items()):
            if wall.called_ts is not None:
                continue
            med = self._big(side, price, shown.get(price, 0.0), shown, ref)
            if med is None:
                del self.walls[side][price]
            elif ts - wall.first_ts >= self.p.min_hold_sec:
                wall.called_ts, wall.median, wall.called_size = ts, med, wall.size_now
                wall.dist_called = _distance(side, price, ref)
                wall.back = self._back(side, price, ts)
                self.version += 1
                out.append(self._event(wall, ts))
        return out

    def _back(self, side: str, price: float, ts: float) -> dict[str, float] | None:
        """The walls pulled at ``price`` on ``side`` in the ``back_sec`` before ``ts``, or None."""
        gone = [w for w in self.ended if w.side == side and w.state == PULLED and abs(w.price - price) <= PRICE_EPS
                and w.ended_ts is not None and w.ended_ts >= ts - self.p.back_sec]
        if not gone:
            return None
        last = max(gone, key=lambda w: w.ended_ts or 0.0)
        size = last.left["before"] if last.left else last.size_now
        return {"pulled": len(gone), "last_ended_ts": round(last.ended_ts or 0.0, 3), "last_size": size}

    # -- ends ----------------------------------------------------------------

    def _lose_side(self, side: str, ts: float, how: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for price, wall in list(self.walls[side].items()):
            if wall.state == LEFT:
                continue  # it left before: the prints still judge it
            if wall.called_ts is None:
                del self.walls[side][price]
            else:
                out += self._end(wall, LOST, ts, how)
        return out

    def _end(self, wall: Wall, state: str, ts: float, how: str, *, ref: float | None = None) -> list[dict[str, Any]]:
        wall.state, wall.ended_ts, wall.how = state, ts, how
        wall.ref_at_end = ref if ref is not None else self._reference(self.views)
        if state == PULLED:
            dist = _distance(wall.side, wall.price, wall.ref_at_end)
            wall.on_approach = (wall.dist_called is not None and dist is not None
                                and dist < wall.dist_called - PRICE_EPS)
        self.version += 1
        if self.walls[wall.side].get(wall.price) is wall:
            del self.walls[wall.side][wall.price]
        self.ended.append(wall)
        return [self._event(wall, ts)]

    # -- readings ------------------------------------------------------------

    def _wall(self, wall: Wall, now: float, ref: float | None, per_sec: float | None = None) -> dict[str, Any]:
        at = wall.ended_ts if wall.ended_ts is not None else now
        dist = _distance(wall.side, wall.price, wall.ref_at_end if wall.ended_ts is not None else ref)
        base = wall.ref_at_end if wall.ended_ts is not None else ref
        return {
            "id": f"{int(wall.first_ts * 1000)}-{self.symbol}-{wall.side}-{wall.price:g}",
            "kind": KIND[wall.side], "side": wall.side, "price": wall.price, "state": wall.state,
            "size_first": wall.first_size, "size_now": wall.size_now, "size_peak": wall.peak,
            "traded": wall.traded, "median_level": wall.median,
            "multiple": round(wall.called_size / wall.median, 2) if wall.median and wall.called_size else None,
            "first_seen_ts": round(wall.first_ts, 3), "seen_from_start": wall.from_start,
            "called_ts": None if wall.called_ts is None else round(wall.called_ts, 3),
            "ended_ts": None if wall.ended_ts is None else round(wall.ended_ts, 3),
            "held_sec": round(max(0.0, at - wall.first_ts), 3),
            "distance": dist,
            "distance_pct": None if dist is None or not base else round(dist / base * 100, 3),
            "distance_called": wall.dist_called, "on_approach": wall.on_approach, "back": wall.back,
            "clear_sec": (round(wall.size_now / per_sec, 1) if per_sec and wall.ended_ts is None and wall.size_now > 0
                          else None),
            "how": wall.how, "left": wall.left,
        }

    def _event(self, wall: Wall, ts: float) -> dict[str, Any]:
        return {"event": "big", "symbol": self.symbol, "ts": round(ts, 3),
                **self._wall(wall, ts, self._reference(self.views), self.pace.rate(ts)[1])}

    def holding(self) -> bool:
        """Is any called price still there (its ``clear_sec`` moves with the pace even when nothing else does)?"""
        return any(w.called_ts is not None for walls in self.walls.values() for w in walls.values())

    def reading(self, now: float) -> dict[str, Any]:
        """Each side's called prices (nearest the price first), then those ended in the last
        ``show_ended_sec`` (newest first)."""
        ref = self._reference(self.views)
        pace, per_sec = self.pace.rate(now)
        sides: dict[str, list[dict[str, Any]]] = {}
        for side in SIDES:
            live = [self._wall(w, now, ref, per_sec) for w in self.walls[side].values() if w.called_ts is not None]
            live.sort(key=lambda w: (w["distance"] if w["distance"] is not None else float("inf")))
            gone = [self._wall(w, now, ref) for w in reversed(self.ended)
                    if w.side == side and w.ended_ts is not None and w.ended_ts >= now - self.p.show_ended_sec]
            sides[side] = live + gone
        return {
            "last": self.last, "last_ts": None if self.last_ts is None else round(self.last_ts, 3),
            "reference": ref, "reference_source": None if ref is None else ("last" if self.last is not None else "mid"),
            "window": None if ref is None else round(self.p.window(ref), 4), "pace": pace,
            "sellers": sides["ask"], "buyers": sides["bid"],
            "sides": {s: {"levels": self.levels[s], "enough": self.levels[s] > self.p.min_other_levels} for s in SIDES},
        }
