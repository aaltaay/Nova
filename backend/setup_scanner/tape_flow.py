"""The tape flow score: who is winning the tape right now, as one number (ADR 034).

maintainer: one-concern the flow score's one rule, summed two ways (a list of prints, or a prefix-sum index)

Four readings over the last ``window_sec``, each from -1 (sellers) to +1 (buyers):

  imbalance  shares printed at the ask minus shares printed at the bid, over
             both. Lit prints only (FINRA / TRF / ADF reports are left out, as
             the tape gate leaves them out); a print between the bid and the
             ask counts for neither side.
  pace       how fast the tape runs against its own last ``baseline_sec``: 0
             at or under its usual pace, full strength at ``pace_full`` times
             it, signed by the imbalance -- speed says how hard, not which way.
  drift      where the price went: the last price-setting print against the
             first one in the window, full strength at ``drift_full`` of price.
  book       the displayed depth in the top ``book_levels`` prices a side, from
             a fresh book: bid shares minus ask shares, over both.

The score is the weighted mean of the readings Nova could take. One it could
not take -- no fresh book, no baseline yet, a single price -- drops out of the
mean and reads ``None``, never 0. Labels: ``burst`` at or over ``burst_at``,
``flush`` at or under minus ``flush_at``, ``quiet`` when fewer than
``min_prints`` lit prints or ``min_shares`` shares printed at the bid or the
ask (too little tape to say), ``blind`` when there is no print and no book at
all, else ``neutral``.

It describes the tape; it predicts nothing by itself. Whether a flush or a
burst says anything about the next minute is what ``eyes/flow_study.py``
measures. ``FlushPolicy`` / ``flush_action`` are what a template does about a
flush while a trade is on -- the scoring exit and Nova's bot read the same rule.

Pure: prints and books in, a dict out. ``evaluate`` sums a list of prints (the
live lanes); ``FlowIndex`` sums a whole recording by prefix sums (the replayed
eyes and the study). Both hand the same sums to ``score_from``.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Any, Iterable

from constants_setups import (
    FLUSH_EXIT_EXIT,
    FLUSH_EXIT_HOLD_SEC,
    FLUSH_EXIT_MIN_R,
    FLUSH_EXIT_OFF,
    FLUSH_EXIT_TRAIL_R,
    TAPE_FLOW_BASELINE_SEC,
    TAPE_FLOW_BLIND,
    TAPE_FLOW_BOOK_LEVELS,
    TAPE_FLOW_BURST,
    TAPE_FLOW_BURST_AT,
    TAPE_FLOW_DRIFT_FULL,
    TAPE_FLOW_FLUSH,
    TAPE_FLOW_FLUSH_AT,
    TAPE_FLOW_MIN_PRINTS,
    TAPE_FLOW_MIN_SHARES,
    TAPE_FLOW_NEUTRAL,
    TAPE_FLOW_PACE_FULL,
    TAPE_FLOW_QUIET,
    TAPE_FLOW_W_BOOK,
    TAPE_FLOW_W_DRIFT,
    TAPE_FLOW_W_IMBALANCE,
    TAPE_FLOW_W_PACE,
    TAPE_FLOW_WINDOW_SEC,
    TAPE_GATE_STALE_BOOK_SEC,
)
from sale_conditions import row_sets_price
from setup_scanner.tape_gate import OFF_EXCHANGE

READINGS = ("imbalance", "pace", "drift", "book")


@dataclass(frozen=True)
class FlowParams:
    window_sec: float = TAPE_FLOW_WINDOW_SEC
    baseline_sec: float = TAPE_FLOW_BASELINE_SEC
    min_prints: int = TAPE_FLOW_MIN_PRINTS
    min_shares: float = TAPE_FLOW_MIN_SHARES
    pace_full: float = TAPE_FLOW_PACE_FULL
    drift_full: float = TAPE_FLOW_DRIFT_FULL
    book_levels: int = TAPE_FLOW_BOOK_LEVELS
    stale_book_sec: float = TAPE_GATE_STALE_BOOK_SEC
    w_imbalance: float = TAPE_FLOW_W_IMBALANCE
    w_pace: float = TAPE_FLOW_W_PACE
    w_drift: float = TAPE_FLOW_W_DRIFT
    w_book: float = TAPE_FLOW_W_BOOK
    burst_at: float = TAPE_FLOW_BURST_AT
    flush_at: float = TAPE_FLOW_FLUSH_AT

    @property
    def history_sec(self) -> float:
        """How far back a reading looks: the baseline, which ends where the window starts."""
        return max(self.baseline_sec, self.window_sec)


DEFAULT_FLOW = FlowParams()


@dataclass(frozen=True)
class FlushPolicy:
    mode: str = FLUSH_EXIT_OFF
    hold_sec: float = FLUSH_EXIT_HOLD_SEC
    trail_r: float = FLUSH_EXIT_TRAIL_R
    min_r: float | None = FLUSH_EXIT_MIN_R

    @property
    def active(self) -> bool:
        return self.mode != FLUSH_EXIT_OFF


@dataclass
class FlowSums:
    """What one reading adds up; every field is filled by either summing path."""

    ask_shares: float = 0.0
    bid_shares: float = 0.0
    ask_prints: int = 0
    bid_prints: int = 0
    between_shares: float = 0.0
    window_lit_shares: float = 0.0     # every lit print in the window, sided or not (the pace)
    baseline_lit_shares: float = 0.0
    baseline_sec: float = 0.0          # seconds of baseline the prints actually cover
    first_px: float | None = None      # first and last price-setting print in the window
    last_px: float | None = None
    price_prints: int = 0
    any_print: bool = False            # any print in the window or the baseline
    bid_depth: float | None = None
    ask_depth: float | None = None
    best_bid: float | None = None
    best_ask: float | None = None


def _num(value: object) -> float | None:
    try:
        x = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _lit(pr: dict) -> bool:
    return str(pr.get("exchange") or "").upper() not in OFF_EXCHANGE


def depth(book: dict | None, levels: int) -> tuple[float | None, float | None, float | None, float | None]:
    """``(bid shares, ask shares, best bid, best ask)`` over the top ``levels`` prices a side.

    Venue rows at one price are summed; a side with no usable row is ``None`` (unknown), never 0."""
    def side(rows: Any, best_high: bool) -> tuple[float | None, float | None]:
        by_price: dict[float, float] = {}
        for lvl in rows or []:
            if not isinstance(lvl, dict):
                continue
            px, sz = _num(lvl.get("price")), _num(lvl.get("size") or 0)
            if px is None or px <= 0 or sz is None or sz < 0:
                continue
            by_price[px] = by_price.get(px, 0.0) + sz
        if not by_price:
            return None, None
        prices = sorted(by_price, reverse=best_high)[:max(1, int(levels))]
        return sum(by_price[p] for p in prices), prices[0]

    bid_sz, best_bid = side((book or {}).get("bids"), True)
    ask_sz, best_ask = side((book or {}).get("asks"), False)
    return bid_sz, ask_sz, best_bid, best_ask


def score_from(s: FlowSums, p: FlowParams = DEFAULT_FLOW) -> dict[str, Any]:
    """The one rule: four readings, their weighted mean, and a label."""
    sided = s.ask_shares + s.bid_shares
    imbalance = (s.ask_shares - s.bid_shares) / sided if sided > 0 else None
    pace, pace_ratio = None, None
    if imbalance is not None and s.baseline_sec >= p.window_sec:
        rate = s.window_lit_shares / p.window_sec
        base = s.baseline_lit_shares / s.baseline_sec
        if base > 0:
            pace_ratio = rate / base
            strength = _clip((pace_ratio - 1.0) / max(p.pace_full - 1.0, 1e-9), 0.0, 1.0)
        else:
            strength = 1.0 if rate > 0 else 0.0      # a quiet baseline and a busy window: all pace
        pace = math.copysign(strength, imbalance) if imbalance != 0 else 0.0
    drift, drift_pct = None, None
    if s.price_prints >= 2 and s.first_px and s.last_px is not None and p.drift_full > 0:
        drift_pct = (s.last_px - s.first_px) / s.first_px
        drift = _clip(drift_pct / p.drift_full)
    book = None
    if s.bid_depth is not None and s.ask_depth is not None and s.bid_depth + s.ask_depth > 0:
        book = (s.bid_depth - s.ask_depth) / (s.bid_depth + s.ask_depth)
    readings = {"imbalance": imbalance, "pace": pace, "drift": drift, "book": book}
    weights = {"imbalance": p.w_imbalance, "pace": p.w_pace, "drift": p.w_drift, "book": p.w_book}
    used = sum(w for k, w in weights.items() if readings[k] is not None and w > 0)
    score = None
    if used > 0:
        score = round(_clip(sum(weights[k] * readings[k] for k in READINGS
                                if readings[k] is not None and weights[k] > 0) / used), 3)
    if not s.any_print and s.bid_depth is None and s.ask_depth is None:
        label = TAPE_FLOW_BLIND
    elif s.ask_prints + s.bid_prints < p.min_prints or sided < p.min_shares or score is None:
        label = TAPE_FLOW_QUIET
    elif score >= p.burst_at:
        label = TAPE_FLOW_BURST
    elif score <= -p.flush_at:
        label = TAPE_FLOW_FLUSH
    else:
        label = TAPE_FLOW_NEUTRAL
    return {
        "score": score, "label": label,
        "readings": {k: None if v is None else round(v, 3) for k, v in readings.items()},
        "metrics": {"window_sec": p.window_sec, "ask_shares": s.ask_shares, "bid_shares": s.bid_shares,
                    "ask_prints": s.ask_prints, "bid_prints": s.bid_prints, "between_shares": s.between_shares,
                    "pace_ratio": None if pace_ratio is None else round(pace_ratio, 3),
                    "baseline_sec": round(s.baseline_sec, 1),
                    "drift_pct": None if drift_pct is None else round(drift_pct * 100, 3),
                    "bid_depth": s.bid_depth, "ask_depth": s.ask_depth,
                    "best_bid": s.best_bid, "best_ask": s.best_ask},
    }


def _bounds(now: float, p: FlowParams, history_from: float | None) -> tuple[float, float]:
    """``(start, window start)``: the baseline runs [start, window start), the window [window start, now]."""
    w0 = now - p.window_sec
    start = now - p.history_sec
    if history_from is not None:
        start = max(start, float(history_from))
    return start, w0


def _book_into(s: FlowSums, books: Iterable[tuple[float, dict]], now: float, p: FlowParams) -> None:
    latest = None
    for ts, book in books:
        t = _num(ts)
        if t is None or t > now or not book:
            continue
        if latest is None or t >= latest[0]:
            latest = (t, book)
    if latest is not None and now - latest[0] <= p.stale_book_sec:
        s.bid_depth, s.ask_depth, s.best_bid, s.best_ask = depth(latest[1], p.book_levels)


def evaluate(*, now: float, books: Iterable[tuple[float, dict]], prints: Iterable[dict],
             p: FlowParams = DEFAULT_FLOW, history_from: float | None = None) -> dict[str, Any]:
    """Read the flow at ``now`` from a list of prints and book samples (the live lanes).

    ``history_from`` is the earliest moment the prints can vouch for (when the feed
    started listening): the baseline never counts time before it as quiet."""
    start, w0 = _bounds(now, p, history_from)
    s = FlowSums(baseline_sec=max(0.0, w0 - start))
    first_ts = last_ts = None
    for pr in prints:
        ts, size = _num(pr.get("ts")), _num(pr.get("size") or 0)
        if ts is None or ts < start or ts > now or size is None or size <= 0:
            continue
        s.any_print = True
        lit = _lit(pr)
        if ts < w0:
            if lit:
                s.baseline_lit_shares += size
            continue
        if lit:
            s.window_lit_shares += size
        px = _num(pr.get("price"))
        if px is not None and px > 0 and row_sets_price(pr):
            s.price_prints += 1
            if first_ts is None or ts < first_ts:
                first_ts, s.first_px = ts, px
            if last_ts is None or ts >= last_ts:
                last_ts, s.last_px = ts, px
        if not lit:
            continue
        side = pr.get("side")
        if side == "ask":
            s.ask_shares += size
            s.ask_prints += 1
        elif side == "bid":
            s.bid_shares += size
            s.bid_prints += 1
        elif side == "between":
            s.between_shares += size
    _book_into(s, books, now, p)
    return score_from(s, p)


class FlowIndex:
    """A whole recording's prints and books, summed once, read at any moment in O(log n).

    Same rule as ``evaluate`` (a test holds them equal): prints in arrival order,
    FINRA / TRF / ADF out of the sided and pace sums, the book from the newest
    sample at or before the moment."""

    def __init__(self, prints: list[dict], books: list[tuple[float, dict]]):
        rows = []
        for pr in prints:
            ts, size = _num(pr.get("ts")), _num(pr.get("size") or 0)
            if ts is None or size is None or size <= 0:
                continue
            rows.append((ts, size, _lit(pr), pr.get("side"), pr))
        rows.sort(key=lambda r: r[0])
        self.ts = [r[0] for r in rows]
        self._lit = self._cum(r[1] if r[2] else 0.0 for r in rows)
        self._ask = self._cum(r[1] if r[2] and r[3] == "ask" else 0.0 for r in rows)
        self._bid = self._cum(r[1] if r[2] and r[3] == "bid" else 0.0 for r in rows)
        self._btw = self._cum(r[1] if r[2] and r[3] == "between" else 0.0 for r in rows)
        self._ask_n = self._cum(1 if r[2] and r[3] == "ask" else 0 for r in rows)
        self._bid_n = self._cum(1 if r[2] and r[3] == "bid" else 0 for r in rows)
        priced = [(r[0], _num(r[4].get("price"))) for r in rows if row_sets_price(r[4])]
        priced = [(t, px) for t, px in priced if px is not None and px > 0]
        self.price_ts = [t for t, _ in priced]
        self.price_px = [px for _, px in priced]
        ordered = sorted(((float(t), b) for t, b in books if b and _num(t) is not None), key=lambda x: x[0])
        self.book_ts = [t for t, _ in ordered]
        self._books = [b for _, b in ordered]
        self._depth: dict[tuple[int, int], tuple] = {}

    @staticmethod
    def _cum(values: Iterable[float]) -> list[float]:
        out, total = [0.0], 0.0
        for v in values:
            total += v
            out.append(total)
        return out

    def book_at(self, now: float, stale_sec: float) -> tuple[int, dict] | None:
        i = bisect.bisect_right(self.book_ts, now) - 1
        if i < 0 or now - self.book_ts[i] > stale_sec:
            return None
        return i, self._books[i]

    def depth_at(self, now: float, p: FlowParams) -> tuple:
        hit = self.book_at(now, p.stale_book_sec)
        if hit is None:
            return None, None, None, None
        key = (hit[0], int(p.book_levels))
        if key not in self._depth:
            self._depth[key] = depth(hit[1], p.book_levels)
        return self._depth[key]

    def last_price(self, now: float, since: float | None = None) -> float | None:
        """The last price-setting print at or before ``now`` (and at or after ``since``)."""
        i = bisect.bisect_right(self.price_ts, now) - 1
        if i < 0 or (since is not None and self.price_ts[i] < since):
            return None
        return self.price_px[i]

    def sums(self, now: float, p: FlowParams = DEFAULT_FLOW, history_from: float | None = None) -> FlowSums:
        start, w0 = _bounds(now, p, history_from)
        a = bisect.bisect_left(self.ts, start)
        b = max(a, bisect.bisect_right(self.ts, now))      # nothing is vouched for when start is after now
        w = min(b, max(a, bisect.bisect_left(self.ts, w0)))
        s = FlowSums(baseline_sec=max(0.0, w0 - start), any_print=b > a,
                     ask_shares=self._ask[b] - self._ask[w], bid_shares=self._bid[b] - self._bid[w],
                     ask_prints=int(self._ask_n[b] - self._ask_n[w]), bid_prints=int(self._bid_n[b] - self._bid_n[w]),
                     between_shares=self._btw[b] - self._btw[w],
                     window_lit_shares=self._lit[b] - self._lit[w], baseline_lit_shares=self._lit[w] - self._lit[a])
        pa = bisect.bisect_left(self.price_ts, max(w0, start))
        pb = bisect.bisect_right(self.price_ts, now)
        if pb > pa:
            s.price_prints = pb - pa
            s.first_px, s.last_px = self.price_px[pa], self.price_px[pb - 1]
        s.bid_depth, s.ask_depth, s.best_bid, s.best_ask = self.depth_at(now, p)
        return s

    def evaluate(self, now: float, p: FlowParams = DEFAULT_FLOW, history_from: float | None = None) -> dict[str, Any]:
        return score_from(self.sums(now, p, history_from), p)


def flush_action(policy: FlushPolicy, *, label: str | None, price: float | None, ts: float, entry: float,
                 risk: float, stop: float, since: float) -> dict[str, Any] | None:
    """What a template does about one reading while a trade is on; ``None`` when nothing.

    Only a ``flush`` counts, only ``hold_sec`` after ``since`` (the entry), and with
    ``min_r`` set only while the trade is up at least that many R. ``exit`` gets out;
    ``tighten`` moves the stop to ``trail_r`` R under the price -- up only, never down."""
    if not policy.active or label != TAPE_FLOW_FLUSH or price is None or risk <= 0:
        return None
    if ts < since + policy.hold_sec:
        return None
    r_now = (float(price) - entry) / risk
    if policy.min_r is not None and r_now < policy.min_r:
        return None
    if policy.mode == FLUSH_EXIT_EXIT:
        return {"action": "exit", "r_now": round(r_now, 3)}
    new_stop = round(float(price) - policy.trail_r * risk, 4)
    if new_stop <= stop + 1e-9:
        return None
    return {"action": "tighten", "stop": new_stop, "r_now": round(r_now, 3)}


def brief(flow: dict | None) -> dict | None:
    """The score and label alone, for the places that carry a tape read in short."""
    if not isinstance(flow, dict):
        return None
    return {"score": flow.get("score"), "label": flow.get("label")}
