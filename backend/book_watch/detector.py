"""One symbol's book watcher (ADR 031) -- pure: books and prints in, events out.

Every drop in resting size at a price wholly in view in two consecutive books
is judged ``BOOK_WATCH_SETTLE_SEC`` later against the lit prints at that price
inside the matching window: what printed is **filled**, the rest **pulled**. A
pull is **large** at ``BOOK_WATCH_LARGE_MIN_SHARES`` and
``BOOK_WATCH_LARGE_MEDIAN_MULT`` x the side's median level. Two flags, each with
its evidence: ``pulled_on_approach`` (a large pull after the price came toward
the size) and ``repeated_pulls`` (``BOOK_WATCH_REPEAT_COUNT`` large pulls on one
side inside ``BOOK_WATCH_REPEAT_WINDOW_SEC``). Hints consistent with spoofing,
never a detection. Events carry ``event``: ``pull`` | ``flag`` | ``minute``.
"""
from __future__ import annotations

from collections import deque
from itertools import pairwise
from statistics import median
from typing import Any

from book_watch.book import (
    SideView,
    distance_ticks,
    in_view,
    median_level,
    price_key,
    same_price,
    side_view,
)
from book_watch.constants_book_watch import (
    BOOK_WATCH_COLLAPSE_FROM,
    BOOK_WATCH_COLLAPSE_TO,
    BOOK_WATCH_FLAGS_KEEP,
    BOOK_WATCH_LARGE_MEDIAN_MULT,
    BOOK_WATCH_LARGE_MIN_SHARES,
    BOOK_WATCH_MATCH_SLACK_SEC,
    BOOK_WATCH_PRINT_KEEP_SEC,
    BOOK_WATCH_PULLS_KEEP,
    BOOK_WATCH_RATE_WINDOW_SEC,
    BOOK_WATCH_REPEAT_COUNT,
    BOOK_WATCH_REPEAT_WINDOW_SEC,
    BOOK_WATCH_SETTLE_SEC,
    BOOK_WATCH_STATS_WINDOW_SEC,
)

SIDES = ("bid", "ask")
_OPPOSITE = {"bid": "ask", "ask": "bid"}
_SIDE_WORD = {"bid": "bid", "ask": "offered"}


def _minute(ts: float) -> int:
    return int(ts // 60 * 60)


def _money(price: float) -> str:
    return f"{price:.2f}" if price >= 1 else f"{price:.4f}"


class SymbolWatch:
    def __init__(self, symbol: str, *, num_rows: int) -> None:
        self.symbol = symbol
        self.num_rows = num_rows
        self.prev: dict[str, SideView] | None = None
        self.prev_ts: float | None = None
        # (side, price) -> {posted_ts, dist_post, opp_at_post}; posted_ts None = seen, not seen arriving.
        self.tracked: dict[tuple[str, float], dict[str, Any]] = {}
        self.prints: deque[list[float]] = deque()  # [ts, price, shares left to claim]
        self.pending: list[dict[str, Any]] = []
        # Every print at or through each side's best, for the size traded against a level while it rested.
        self.side_volume = {"bid": 0.0, "ask": 0.0}
        self.large_by_side: dict[str, deque[tuple[float, float, float]]] = {s: deque() for s in SIDES}
        self.last_repeat: dict[str, float | None] = {s: None for s in SIDES}
        self.book_times: deque[float] = deque()
        self.window: deque[tuple[float, float, float, bool]] = deque()  # ts, pulled, filled, large
        self.flags: deque[dict[str, Any]] = deque(maxlen=BOOK_WATCH_FLAGS_KEEP)
        self.pulls: deque[dict[str, Any]] = deque(maxlen=BOOK_WATCH_PULLS_KEEP)
        self.books = 0
        self.prints_seen = 0
        self.since: float | None = None
        self.last_book_ts: float | None = None
        self.bucket: dict[str, Any] | None = None

    # -- input ---------------------------------------------------------------

    def on_book(self, ts: float, bids: list[Any], asks: list[Any]) -> list[dict[str, Any]]:
        out = self.tick(ts)
        cur = {"bid": side_view(bids, "bid", self.num_rows), "ask": side_view(asks, "ask", self.num_rows)}
        self.books += 1
        self.since = ts if self.since is None else self.since
        self.last_book_ts = ts
        self.book_times.append(ts)
        while self.book_times and self.book_times[0] < ts - BOOK_WATCH_RATE_WINDOW_SEC:
            self.book_times.popleft()
        out += self._roll(ts, books=1)
        for side in SIDES:
            prev = self.prev[side] if self.prev is not None else None
            self._compare(side, prev, cur[side], ts)
        self.prev, self.prev_ts = cur, ts
        return out

    def on_print(self, ts: float, price: Any, size: Any, *, lit: bool) -> list[dict[str, Any]]:
        out = self.tick(ts)
        key = price_key(price)
        try:
            shares = float(size)
        except (TypeError, ValueError):
            return out
        if key is None or shares <= 0:
            return out
        self.prints_seen += 1
        out += self._roll(ts, prints=1)
        if self.prev is not None:
            ask, bid = self.prev["ask"].best, self.prev["bid"].best
            if ask is not None and key >= ask:
                self.side_volume["ask"] += shares
            elif bid is not None and key <= bid:
                self.side_volume["bid"] += shares
        if lit:
            self.prints.append([ts, key, shares])
        while self.prints and self.prints[0][0] < ts - BOOK_WATCH_PRINT_KEEP_SEC:
            self.prints.popleft()
        return out

    def reset(self) -> None:
        """IBKR restarted the book (error 317, a new request): what came before is not comparable."""
        self.prev = None
        self.prev_ts = None
        self.tracked.clear()

    def tick(self, now: float) -> list[dict[str, Any]]:
        """Judge every drop whose settle time has passed."""
        out: list[dict[str, Any]] = []
        due = [p for p in self.pending if p["deadline"] <= now]
        if not due:
            return out
        self.pending = [p for p in self.pending if p["deadline"] > now]
        for drop in due:
            out += self._judge(drop)
        return out

    def flush(self) -> list[dict[str, Any]]:
        """End of input (a replay): judge everything and close the minute."""
        out = self.tick(float("inf"))
        if self.bucket is not None:
            out.append(self._close_bucket())
        return out

    # -- comparing two books -------------------------------------------------

    def _compare(self, side: str, prev: SideView | None, cur: SideView, ts: float) -> None:
        if prev is None or (len(cur.levels) <= BOOK_WATCH_COLLAPSE_TO and len(prev.levels) >= BOOK_WATCH_COLLAPSE_FROM):
            # First book, or a side that collapsed at once (a reset, a glitch): nothing is judged.
            self._forget(side)
            for price in cur.levels:
                self.tracked[(side, price)] = {"posted_ts": None, "dist_post": None, "opp_at_post": None}
            return
        for price, before in prev.levels.items():
            if not in_view(price, side, prev.cutoff):
                continue
            if not in_view(price, side, cur.cutoff):
                self.tracked.pop((side, price), None)  # scrolled out of view: unknown, never pulled
                continue
            after = cur.levels.get(price, 0.0)
            if after < before:
                info = self.tracked.get((side, price)) or {}
                self.pending.append({
                    "deadline": ts + BOOK_WATCH_SETTLE_SEC, "t0": self.prev_ts, "t1": ts, "side": side,
                    "price": price, "drop": before - after, "before": before, "after": after,
                    "distance": distance_ticks(side, price, prev.best), "dist_post": info.get("dist_post"),
                    "posted_ts": info.get("posted_ts"), "opp_at_post": info.get("opp_at_post"),
                    "median": median_level(prev.levels, exclude=price),
                })
            if after <= 0:
                self.tracked.pop((side, price), None)
        for price in cur.levels:
            key = (side, price)
            if key in self.tracked:
                continue
            arrived = in_view(price, side, prev.cutoff) and prev.levels.get(price, 0.0) <= 0
            self.tracked[key] = {
                "posted_ts": ts if arrived else None,
                "dist_post": distance_ticks(side, price, cur.best) if arrived else None,
                "opp_at_post": self.side_volume[_OPPOSITE[side]] if arrived else None,
            }

    def _forget(self, side: str) -> None:
        for key in [k for k in self.tracked if k[0] == side]:
            del self.tracked[key]

    # -- judging a drop ------------------------------------------------------

    def _claim(self, drop: dict[str, Any]) -> float:
        """Shares printed at the level's price in the window, claimed oldest first."""
        start = (drop["t0"] if drop["t0"] is not None else drop["t1"]) - BOOK_WATCH_MATCH_SLACK_SEC
        end = drop["t1"] + BOOK_WATCH_MATCH_SLACK_SEC
        need = drop["drop"]
        filled = 0.0
        for row in self.prints:
            if filled >= need:
                break
            ts, price, left = row
            if ts <= start or ts > end or left <= 0 or not same_price(price, drop["price"]):
                continue
            take = min(left, need - filled)
            row[2] = left - take
            filled += take
        return filled

    def _judge(self, drop: dict[str, Any]) -> list[dict[str, Any]]:
        filled = self._claim(drop)
        pulled = max(0.0, drop["drop"] - filled)
        med = drop["median"]
        large = pulled >= BOOK_WATCH_LARGE_MIN_SHARES and (med is None or pulled >= BOOK_WATCH_LARGE_MEDIAN_MULT * med)
        t1 = drop["t1"]
        self.window.append((t1, pulled, filled, large))
        while self.window and self.window[0][0] < t1 - BOOK_WATCH_STATS_WINDOW_SEC:
            self.window.popleft()
        out = self._roll(t1, pulled=pulled, filled=filled, large=int(large))
        if not large:
            return out
        side = drop["side"]
        opp = drop["opp_at_post"]
        dist, dist_post = drop["distance"], drop["dist_post"]
        approached = None if dist is None or dist_post is None else dist < dist_post
        pull = {
            "event": "pull", "symbol": self.symbol, "ts": round(t1, 3), "side": side, "price": drop["price"],
            "pulled": pulled, "filled": filled, "level_before": drop["before"], "level_after": drop["after"],
            "median_level": med, "distance_ticks": dist, "distance_at_post_ticks": dist_post,
            "lifetime_sec": None if drop["posted_ts"] is None else round(t1 - drop["posted_ts"], 3),
            "approached": approached,
            "opposite_volume": None if opp is None else self.side_volume[_OPPOSITE[side]] - opp,
        }
        self.pulls.append(pull)
        out.append(pull)
        if approached and dist_post is not None and dist_post >= 1:
            out.append(self._flag("pulled_on_approach", pull, (
                f"{pulled:,.0f} shares {_SIDE_WORD[side]} at {_money(drop['price'])} pulled after the price came "
                f"{dist_post - dist} tick(s) toward it; {filled:,.0f} of the drop traded there")))
        out += self._repeat(side, pull)
        return out

    def _repeat(self, side: str, pull: dict[str, Any]) -> list[dict[str, Any]]:
        ts = pull["ts"]
        recent = self.large_by_side[side]
        recent.append((ts, pull["price"], pull["pulled"]))
        while recent and recent[0][0] < ts - BOOK_WATCH_REPEAT_WINDOW_SEC:
            recent.popleft()
        last = self.last_repeat[side]
        if len(recent) < BOOK_WATCH_REPEAT_COUNT or (last is not None and ts - last < BOOK_WATCH_REPEAT_WINDOW_SEC):
            return []
        self.last_repeat[side] = ts
        pulls = [{"ts": t, "price": p, "pulled": s} for t, p, s in recent]
        flag = self._flag("repeated_pulls", pull, (
            f"{len(pulls)} large {_SIDE_WORD[side]} levels pulled in {BOOK_WATCH_REPEAT_WINDOW_SEC:.0f} s "
            f"without trading ({sum(s for _, _, s in recent):,.0f} shares)"))
        flag["price"] = None
        flag["shares"] = sum(s for _, _, s in recent)
        flag["evidence"] = {"count": len(pulls), "window_sec": BOOK_WATCH_REPEAT_WINDOW_SEC, "pulls": pulls}
        return [flag]

    def _flag(self, kind: str, pull: dict[str, Any], why: str) -> dict[str, Any]:
        evidence = {k: v for k, v in pull.items() if k not in ("event", "symbol", "ts", "side", "price")}
        flag = {
            "event": "flag", "id": f"{int(pull['ts'] * 1000)}-{self.symbol}-{kind}", "kind": kind,
            "symbol": self.symbol, "ts": pull["ts"], "side": pull["side"], "price": pull["price"],
            "shares": pull["pulled"], "why": why, "evidence": evidence,
        }
        self.flags.append(flag)
        if self.bucket is not None:
            self.bucket["flags"] += 1
        return flag

    # -- readings ------------------------------------------------------------

    def _roll(self, ts: float, **add: float) -> list[dict[str, Any]]:
        """Add to the current minute; a new minute closes the old one as an event."""
        out: list[dict[str, Any]] = []
        minute = _minute(ts)
        if self.bucket is not None and minute > self.bucket["minute_ts"]:
            out.append(self._close_bucket())
        if self.bucket is None or minute > self.bucket["minute_ts"]:
            self.bucket = {"minute_ts": minute, "books": 0, "prints": 0, "pulled": 0.0, "filled": 0.0,
                           "pulls": 0, "fills": 0, "large": 0, "flags": 0}
        b = self.bucket
        b["books"] += int(add.get("books", 0))
        b["prints"] += int(add.get("prints", 0))
        b["pulled"] += add.get("pulled", 0.0)
        b["filled"] += add.get("filled", 0.0)
        b["pulls"] += int(add.get("pulled", 0.0) > 0)
        b["fills"] += int(add.get("filled", 0.0) > 0)
        b["large"] += int(add.get("large", 0))
        return out

    def _close_bucket(self) -> dict[str, Any]:
        b, self.bucket = self.bucket, None
        return {"event": "minute", "symbol": self.symbol, "minute_ts": b["minute_ts"], "books": b["books"],
                "prints": b["prints"], "pulled_shares": b["pulled"], "filled_shares": b["filled"],
                "pulls": b["pulls"], "fills": b["fills"], "large_pulls": b["large"], "flags": b["flags"]}

    def feed(self, now: float) -> dict[str, Any]:
        """How fast the book arrives: the measured rate, never a claimed one."""
        times = [t for t in self.book_times if t >= now - BOOK_WATCH_RATE_WINDOW_SEC]
        gaps = [b - a for a, b in pairwise(times)]
        return {
            "books": self.books, "prints": self.prints_seen,
            "books_per_sec": round(len(times) / BOOK_WATCH_RATE_WINDOW_SEC, 2),
            "median_gap_ms": round(median(gaps) * 1000, 1) if gaps else None,
            "last_book_age_ms": None if self.last_book_ts is None else round((now - self.last_book_ts) * 1000, 1),
            "window_sec": BOOK_WATCH_RATE_WINDOW_SEC,
        }

    def totals(self, now: float) -> dict[str, Any]:
        rows = [r for r in self.window if r[0] >= now - BOOK_WATCH_STATS_WINDOW_SEC]
        return {
            "window_sec": BOOK_WATCH_STATS_WINDOW_SEC,
            "pulled_shares": sum(r[1] for r in rows), "filled_shares": sum(r[2] for r in rows),
            "pulls": sum(1 for r in rows if r[1] > 0), "fills": sum(1 for r in rows if r[2] > 0),
            "large_pulls": sum(1 for r in rows if r[3]),
        }
