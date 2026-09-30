"""Size that traded at a price beyond the most the book ever showed there: hidden sellers and
hidden buyers (ADR 033 amendment, 2026-09-30).

The mirror of a pull. A pull is size the book showed that left without trading; a hidden seller
is size that traded at the offer beyond the most the book ever showed there. Each side follows one
**stretch**: the price its prints keep landing at -- buyers lifting the offer on the ask side,
sellers hitting the bid on the bid side. Every counted print there joins it, including prints at
that price after the size shown there is gone, and the stretch weighs what printed there against
the most the book showed there, from ``BOOK_WATCH_HIDDEN_SHOWN_BEFORE_SEC`` before its first print.

A stretch holds while its side's prints stay at its price. It ends when a print goes through it
(``broke``), when its side's prints move the other way (``moved``: the offer came down, the bid
went up), after ``BOOK_WATCH_HIDDEN_GAP_SEC`` without a print at it (``faded``), at a cross print
(``auction``) or when the book restarts (``reset``). It is a **hidden seller** (the ask) or a
**hidden buyer** (the bid) once its price has held ``BOOK_WATCH_HIDDEN_MIN_HOLD_SEC`` since its first
print, at least ``BOOK_WATCH_HIDDEN_MIN_SHARES`` printed there and at least
``BOOK_WATCH_HIDDEN_SHOWN_MULT`` x the most the book showed there; its hidden size is what printed
beyond that most. The hold keeps a sweep out: a buyer taking the whole offer prints at a price and
through it within milliseconds, and no one held anything. A stretch the book could not follow throughout (a side that collapsed, its price
cut off below the rows shown, a reset) is never flagged.

Counted: lit prints, odd lots included, while the book is fresh (a book within
``BOOK_WATCH_IDLE_SEC``: a Session Record can keep the tape after its depth line is gone). Never
counted: off-exchange (FINRA) reports, cross prints and volume-only prints
(``BOOK_WATCH_AUCTION_CONDITIONS``, ``BOOK_WATCH_HIDDEN_SKIP_CONDITIONS``).

Why the most shown, not the prints no drop claimed: on the Session Records 60-75% of the lit volume
at the quote matched no fall in the size shown within the watcher's matching window -- the book and
the tape arrive up to seconds apart, and a level refilled between two books never shows the fall --
so a per-print count is mostly timing. The most shown needs no timing. One reserve (iceberg) order
and several orders refilling one price look the same here; either way more traded there than the
book showed. A hint -- never a detection.

Pure: books and prints in, ``hidden`` events out. ``history`` (a list) keeps every stretch with a
trace of its prints, for the study (``hidden_study.py``); the live watcher passes none.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from book_watch.book import SideView, collapsed, in_view
from book_watch.constants_book_watch import (
    BOOK_WATCH_AUCTION_CONDITIONS,
    BOOK_WATCH_HIDDEN_GAP_SEC,
    BOOK_WATCH_HIDDEN_KEEP,
    BOOK_WATCH_HIDDEN_MIN_HOLD_SEC,
    BOOK_WATCH_HIDDEN_MIN_SHARES,
    BOOK_WATCH_HIDDEN_SHOWN_BEFORE_SEC,
    BOOK_WATCH_HIDDEN_SHOWN_MULT,
    BOOK_WATCH_HIDDEN_SKIP_CONDITIONS,
    BOOK_WATCH_HIDDEN_UPDATE_SEC,
    BOOK_WATCH_IDLE_SEC,
    BOOK_WATCH_STATS_WINDOW_SEC,
)

SIDES = ("bid", "ask")
# Prices are keys rounded to 6 places (book.price_key), so one price is exactly one key. Never half a
# tick: a midpoint print at 3.655 sits between 3.65 and 3.66, at neither side's price.
EPS = 1e-7
KIND = {"ask": "hidden_seller", "bid": "hidden_buyer"}
HOLDING = "holding"


@dataclass(frozen=True)
class HiddenParams:
    min_shares: float = BOOK_WATCH_HIDDEN_MIN_SHARES
    shown_mult: float = BOOK_WATCH_HIDDEN_SHOWN_MULT
    gap_sec: float = BOOK_WATCH_HIDDEN_GAP_SEC
    min_hold_sec: float = BOOK_WATCH_HIDDEN_MIN_HOLD_SEC
    shown_before_sec: float = BOOK_WATCH_HIDDEN_SHOWN_BEFORE_SEC
    update_sec: float = BOOK_WATCH_HIDDEN_UPDATE_SEC


DEFAULT_HIDDEN = HiddenParams()


@dataclass
class Stretch:
    """One side printing at one price, against the most the book showed there."""

    side: str
    price: float
    started_ts: float
    last_ts: float
    shown_max: float = 0.0
    shown_now: float | None = None
    printed: float = 0.0
    prints: int = 0
    refills: int = 0              # the size shown there grew again while it held
    uncertain: str | None = None  # why the book could not follow it: "collapsed" | "cut_off" | "reset"
    state: str = HOLDING
    ended_ts: float | None = None
    flagged_ts: float | None = None
    sent_printed: float = 0.0
    sent_ts: float = float("-inf")
    trace: list[tuple[float, float, float]] | None = None  # (print ts, printed, shown_max), for the study

    @property
    def hidden(self) -> float:
        """What printed there beyond the most the book showed there."""
        return max(0.0, self.printed - self.shown_max)


class HiddenTracker:
    def __init__(self, symbol: str, *, params: HiddenParams = DEFAULT_HIDDEN,
                 history: list[Stretch] | None = None) -> None:
        self.symbol = symbol
        self.p = params
        self.history = history
        self.active: dict[str, Stretch | None] = {s: None for s in SIDES}
        self.books: deque[tuple[float, dict[str, SideView]]] = deque()
        self.flagged: deque[Stretch] = deque(maxlen=BOOK_WATCH_HIDDEN_KEEP)
        self.kept: deque[dict[str, Any]] = deque(maxlen=BOOK_WATCH_HIDDEN_KEEP)
        self.seq = 0

    # -- input ---------------------------------------------------------------

    def on_book(self, ts: float, views: dict[str, SideView], prev: dict[str, SideView] | None) -> None:
        self.books.append((ts, views))
        while len(self.books) > 1 and self.books[1][0] <= ts - self.p.shown_before_sec:
            self.books.popleft()
        for side in SIDES:
            st = self.active[side]
            if st is None:
                continue
            if prev is not None and collapsed(prev[side], views[side]):
                st.uncertain = st.uncertain or "collapsed"
            self._shown(st, views[side])

    def on_print(self, ts: float, key: float, shares: float, *, lit: bool, conditions: Any,
                 views: dict[str, SideView] | None, book_ts: float | None) -> list[dict[str, Any]]:
        codes = set(str(conditions or ""))
        if codes & BOOK_WATCH_AUCTION_CONDITIONS:
            return self._end_all("auction", ts)
        out = self.tick(ts)
        if not lit or codes & BOOK_WATCH_HIDDEN_SKIP_CONDITIONS:
            return out
        if views is None or book_ts is None or ts - book_ts > BOOK_WATCH_IDLE_SEC:
            return out  # no fresh book to weigh it against
        side = self._side(key, views)
        if side is None:
            return out  # inside the spread, or a locked book: neither side's price
        st = self.active[side]
        if st is not None and abs(key - st.price) > EPS:
            through = key > st.price if side == "ask" else key < st.price
            out += self._close(st, "broke" if through else "moved", ts)
            st = None
        if st is None:
            st = self._open(side, key, ts)
        st.printed += shares
        st.prints += 1
        st.last_ts = ts
        if st.trace is not None:
            st.trace.append((ts, st.printed, st.shown_max))
        if st.flagged_ts is None:
            if (st.uncertain is None and ts - st.started_ts >= self.p.min_hold_sec
                    and st.printed >= self.p.min_shares and st.printed >= self.p.shown_mult * st.shown_max):
                st.flagged_ts = ts
                self.flagged.append(st)
                out.append(self._event(st, ts))
        elif st.printed > st.sent_printed and ts - st.sent_ts >= self.p.update_sec:
            out.append(self._event(st, ts))
        return out

    def tick(self, now: float) -> list[dict[str, Any]]:
        """End every stretch without a print at its price for ``gap_sec``."""
        out: list[dict[str, Any]] = []
        for side in SIDES:
            st = self.active[side]
            if st is not None and now - st.last_ts > self.p.gap_sec:
                out += self._close(st, "faded", st.last_ts + self.p.gap_sec)
        return out

    def reset(self, ts: float | None) -> list[dict[str, Any]]:
        """The book restarted: what it showed before is not comparable."""
        self.books.clear()
        return self._end_all("reset", ts, uncertain="reset")

    # -- readings ------------------------------------------------------------

    def side_totals(self, now: float) -> dict[str, float]:
        """Each side's hidden size at the prices flagged in the stats window (holding, or ended in it)."""
        out = {s: 0.0 for s in SIDES}
        for st in self.flagged:
            if st.state == HOLDING or (st.ended_ts is not None and st.ended_ts >= now - BOOK_WATCH_STATS_WINDOW_SEC):
                out[st.side] += st.hidden
        return out

    def recent(self, since: float | None = None) -> list[dict[str, Any]]:
        """The newest word on each flagged stretch (only those sent after ``since`` when given), newest first."""
        latest: dict[str, dict[str, Any]] = {}
        for ev in self.kept:
            if since is None or ev["ts"] > since:
                latest[ev["id"]] = ev
        return sorted(latest.values(), key=lambda e: e["ts"], reverse=True)

    # -- stretches -----------------------------------------------------------

    def _side(self, key: float, views: dict[str, SideView]) -> str | None:
        ask, bid = views["ask"].best, views["bid"].best
        at_ask = (ask is not None and key >= ask - EPS) or self._at("ask", key)
        at_bid = (bid is not None and key <= bid + EPS) or self._at("bid", key)
        if at_ask == at_bid:
            return None
        return "ask" if at_ask else "bid"

    def _at(self, side: str, key: float) -> bool:
        st = self.active[side]
        return st is not None and abs(st.price - key) <= EPS

    def _open(self, side: str, key: float, ts: float) -> Stretch:
        st = Stretch(side, key, ts, ts, trace=[] if self.history is not None else None)
        newest = self.books[-1][0] if self.books else None
        for bts, views in self.books:  # what the book showed there from shown_before_sec before the first print
            if bts >= ts - self.p.shown_before_sec or bts == newest:
                self._shown(st, views[side])
        st.refills = 0  # the size growing before the first print is no refill
        self.active[side] = st
        if self.history is not None:
            self.history.append(st)
        return st

    @staticmethod
    def _shown(st: Stretch, view: SideView) -> None:
        if not in_view(st.price, st.side, view.cutoff):
            st.uncertain = st.uncertain or "cut_off"
            return
        size = view.levels.get(st.price, 0.0)
        if st.shown_now is not None and size > st.shown_now:
            st.refills += 1
        st.shown_now = size
        st.shown_max = max(st.shown_max, size)

    def _end_all(self, state: str, ts: float | None, *, uncertain: str | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for side in SIDES:
            st = self.active[side]
            if st is not None:
                st.uncertain = st.uncertain or uncertain
                out += self._close(st, state, ts if ts is not None else st.last_ts)
        return out

    def _close(self, st: Stretch, state: str, ts: float) -> list[dict[str, Any]]:
        st.state, st.ended_ts = state, ts
        if self.active[st.side] is st:
            self.active[st.side] = None
        return [self._event(st, ts)] if st.flagged_ts is not None else []

    def _event(self, st: Stretch, now: float) -> dict[str, Any]:
        st.sent_printed, st.sent_ts = st.printed, now
        self.seq += 1
        event = {
            "event": "hidden", "id": f"{int(st.started_ts * 1000)}-{self.symbol}-{st.side}-{st.price:g}",
            "kind": KIND[st.side], "symbol": self.symbol, "ts": round(now, 3), "side": st.side,
            "price": st.price, "state": st.state, "hidden": st.hidden, "printed": st.printed,
            "shown_max": st.shown_max, "shown_now": st.shown_now, "prints": st.prints, "refills": st.refills,
            "started_ts": round(st.started_ts, 3), "last_print_ts": round(st.last_ts, 3),
            "flagged_ts": round(st.flagged_ts, 3) if st.flagged_ts is not None else None,
            "ended_ts": round(st.ended_ts, 3) if st.ended_ts is not None else None,
        }
        self.kept.append({**event, "seq": self.seq})
        return event
