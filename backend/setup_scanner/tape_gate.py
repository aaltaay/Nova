"""The tape gate: read the live Level 2 and time and sales at a trigger.

A setup on the bars is a hypothesis; the gate is the check the source
material makes before pressing buy (ADR 022, Bot-Trading-Plan section 2g):

  veto   the spread is too wide; a seller of 100k+ shares sits at the level;
         buyers are lifting the ask but it does not move (a hidden seller)
  wait   a 25k+ seller sits at the level and is not thinning; a burst of red
         on the tape; no green on the tape yet
  go     green on the tape (prints at the ask outweigh prints at the bid) and
         no wall at the level, or the wall is being eaten
  blind  no fresh book -- Nova holds no Level 2 line for the symbol; or the
         window touches an IBKR feed gap, whose prints arrived in one burst (#673)

A short setup's gate is the mirror (ADR 049, ``side="short"``): its level is the bids from one cent over the
trigger down to ``band`` under it; a buyer there waits or vetoes; red on the tape (prints at the bid
outweighing the ask) is go; a green burst waits; a hidden buyer -- the bid sold into without moving down --
vetoes; a flow score at or under minus the entry minimum enters. The template keys are the long's; only their
words mirror.

A template may decide the entry by the tape flow score instead (ADR 034,
``entry_mode``): ``gate`` is the rule above; ``score`` keeps the vetoes and a
wall that is not thinning, and replaces the green / red print counts with the
flow score at or over ``entry_min_score``; ``both`` needs the green prints and
the score. The flow reading rides on every answer as ``flow``.

Pure: the engine hands in the book samples and prints it saw in the window.
Prints carry the side the live tape stamped against the book at receipt
(``ibkr/tape_side.py``); off-exchange (FINRA / TRF) reports are left out, as
the material filters them. Prints and book samples are stamped when they
arrive, so ``now`` must be on that clock: a lane reads a trigger when it sees
it (``Lane.read_at``), never at the price's own whole-second stamp, which would
leave out the prints that crossed the trigger (ADR 022 amendment 2026-09-30).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

from constants_setups import (
    TAPE_GATE_BAND_DOLLARS,
    TAPE_GATE_BIG_SELLER_SHARES,
    TAPE_GATE_HIDDEN_SELLER_MULT,
    TAPE_GATE_MIN_ASK_PRINTS,
    TAPE_GATE_RED_BURST_MULT,
    TAPE_GATE_SPREAD_MAX_DOLLARS,
    TAPE_GATE_SPREAD_MAX_PCT,
    TAPE_GATE_STALE_BOOK_SEC,
    TAPE_GATE_THIN_FRACTION,
    TAPE_GATE_WALL_SHARES,
    TAPE_GATE_WINDOW_SEC,
    TAPE_ENTRY_BOTH,
    TAPE_ENTRY_GATE,
    TAPE_ENTRY_MIN_SCORE,
    TAPE_ENTRY_SCORE,
    TAPE_FLOW_BLIND,
    TAPE_FLOW_QUIET,
    TAPE_VERDICT_BLIND,
    TAPE_VERDICT_GO,
    TAPE_VERDICT_VETO,
    TAPE_VERDICT_WAIT,
)
from setup_scanner import tape_gap

OFF_EXCHANGE = frozenset({"FINRA", "TRF", "ADF"})  # CHOSEN: IBKR's labels for trade reports


@dataclass(frozen=True)
class GateParams:
    window_sec: float = TAPE_GATE_WINDOW_SEC
    stale_book_sec: float = TAPE_GATE_STALE_BOOK_SEC
    spread_max: float = TAPE_GATE_SPREAD_MAX_DOLLARS
    spread_max_pct: float = TAPE_GATE_SPREAD_MAX_PCT
    band: float = TAPE_GATE_BAND_DOLLARS
    big_seller: float = TAPE_GATE_BIG_SELLER_SHARES
    wall: float = TAPE_GATE_WALL_SHARES
    thin_fraction: float = TAPE_GATE_THIN_FRACTION
    min_ask_prints: int = TAPE_GATE_MIN_ASK_PRINTS
    hidden_mult: float = TAPE_GATE_HIDDEN_SELLER_MULT
    red_mult: float = TAPE_GATE_RED_BURST_MULT
    entry_mode: str = TAPE_ENTRY_GATE
    entry_min_score: float = TAPE_ENTRY_MIN_SCORE


DEFAULT_GATE = GateParams()


def _num(value: object) -> float | None:
    """A finite number, else None: IBKR sends NaN for an unknown size or price."""
    try:
        x = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _levels(book: dict | None, side: str) -> list[tuple[float, float]]:
    out = []
    for lvl in (book or {}).get(side) or []:
        if not isinstance(lvl, dict):
            continue
        price, size = _num(lvl.get("price")), _num(lvl.get("size") or 0)
        if price is None or price <= 0 or size is None or size < 0:
            continue
        out.append((price, size))
    return out


@dataclass(frozen=True)
class _Side:
    """What the gate reads on each side, and the words it says (ADR 049: the short mirror)."""

    wall_book: str           # the book side the level sits on
    with_print: str          # prints that move the setup's way
    against_print: str
    trader: str              # who waits / vetoes at the level
    flow_word: str           # "green" for a long, "red" for a short
    burst_word: str
    hidden: str
    flow_key: str


_LONG = _Side("asks", "ask", "bid", "seller", "green", "red", "hidden seller: {k:.1f}k bought at the ask and the "
              "ask did not move", "green_flow")
_SHORT = _Side("bids", "bid", "ask", "buyer", "red", "green", "hidden buyer: {k:.1f}k sold at the bid and the bid "
               "did not move", "red_flow")


def _wall(book: dict | None, trigger: float, band: float, side: _Side = _LONG) -> tuple[float | None, float]:
    """Biggest single level at the setup's level: for a long the asks from one cent under the trigger to
    ``band`` over it; for a short the bids from one cent over it down to ``band`` under it."""
    best_px, best_sz = None, 0.0
    lo, hi = (trigger - 0.01, trigger + band) if side is _LONG else (trigger - band, trigger + 0.01)
    for px, sz in _levels(book, side.wall_book):
        if lo - 1e-9 <= px <= hi + 1e-9 and sz > best_sz:
            best_px, best_sz = px, sz
    return best_px, best_sz


def _size_at(book: dict | None, price: float, side: _Side = _LONG) -> float:
    return sum(sz for px, sz in _levels(book, side.wall_book) if abs(px - price) < 1e-6)


def _score_check(flow: dict | None, p: GateParams, side: _Side = _LONG) -> tuple[bool, str]:
    """Whether the flow score clears the template's entry minimum (for a short: at or under minus it), and
    the reason in words."""
    if not isinstance(flow, dict) or flow.get("label") == TAPE_FLOW_BLIND:
        return False, "no flow reading"
    score = flow.get("score")
    if flow.get("label") == TAPE_FLOW_QUIET or score is None:
        return False, "the tape is too quiet to score"
    if side is _SHORT:
        if score <= -p.entry_min_score + 1e-9:
            return True, f"flow {score:+.2f} ({flow.get('label')})"
        return False, f"flow {score:+.2f} is over {-p.entry_min_score:+.2f}"
    if score >= p.entry_min_score - 1e-9:
        return True, f"flow {score:+.2f} ({flow.get('label')})"
    return False, f"flow {score:+.2f} is under {p.entry_min_score:+.2f}"


def evaluate(*, trigger: float, now: float, books: Iterable[tuple[float, dict]],
             prints: Iterable[dict], p: GateParams = DEFAULT_GATE, flow: dict | None = None,
             gaps: Iterable[dict] | None = None, side: str = "long") -> dict[str, Any]:
    """Judge the tape at ``trigger`` from the samples inside the window ending at ``now``.

    ``metrics.read_at`` is ``now``: the moment the read stands for (ADR 022 amendment 2026-09-30).
    ``gaps`` are the live feed's gaps (``ibkr.feed_pulse``): a window that touches one reads
    ``blind`` with the gap as its reason (#673). ``side`` is the setup's (ADR 049): a short reads the
    mirror."""
    gap = tape_gap.touching(gaps, now - p.window_sec, now) if gaps else None
    if gap is not None:
        res = tape_gap.blind_gate(gap, now, p.window_sec)
    else:
        res = _evaluate(trigger=trigger, now=now, books=books, prints=prints, p=p, flow=flow,
                        mirror=_SHORT if side == "short" else _LONG)
    if flow is not None:
        res["flow"] = flow
        res["metrics"]["flow_score"] = flow.get("score")
    res["metrics"]["entry_mode"] = p.entry_mode
    res["metrics"]["read_at"] = now
    if side == "short":
        res["metrics"]["side"] = "short"
    return res


def _evaluate(*, trigger: float, now: float, books: Iterable[tuple[float, dict]],
              prints: Iterable[dict], p: GateParams, flow: dict | None, mirror: _Side = _LONG) -> dict[str, Any]:
    window = [(ts, b) for ts, b in books if now - p.window_sec <= ts <= now and b]
    reasons: list[str] = []
    metrics: dict[str, Any] = {"window_sec": p.window_sec}
    if not window or now - window[-1][0] > p.stale_book_sec:
        return {"verdict": TAPE_VERDICT_BLIND, "reasons": ["no fresh Level 2 -- open its Level 2 so the bot can read the tape"],
                "metrics": metrics}
    window.sort(key=lambda x: x[0])
    first_book, book = window[0][1], window[-1][1]
    bids, asks = _levels(book, "bids"), _levels(book, "asks")
    best_bid = bids[0][0] if bids else None
    best_ask = asks[0][0] if asks else None
    l1_only = bool(book.get("l1_fallback"))
    metrics.update({"best_bid": best_bid, "best_ask": best_ask, "book_age_sec": round(now - window[-1][0], 2),
                    "l1_only": l1_only})
    if best_bid is None or best_ask is None:
        return {"verdict": TAPE_VERDICT_BLIND, "reasons": ["the book has no bid or no ask"], "metrics": metrics}

    vetoes: list[str] = []
    waits: list[str] = []
    spread = round(best_ask - best_bid, 4)
    spread_cap = max(p.spread_max, p.spread_max_pct * best_ask)
    metrics["spread"] = spread
    if spread > spread_cap + 1e-9:
        vetoes.append(f"spread {spread:.2f} is wider than {spread_cap:.2f}")

    who = mirror.trader
    wall_px, wall_sz = _wall(book, trigger, p.band, mirror)
    start_sz = _size_at(first_book, wall_px, mirror) if wall_px is not None else 0.0
    metrics.update({"wall_price": wall_px, "wall_size": wall_sz, "wall_size_start": start_sz})
    # A wall that was there at the start of the window and has been eaten below
    # the threshold is the strongest "go" the material describes -- say so.
    was_px, was_sz = _wall(first_book, trigger, p.band, mirror)
    if was_px is not None and was_sz >= p.wall and wall_sz < p.wall:
        left = _size_at(book, was_px, mirror)
        if left <= (1 - p.thin_fraction) * was_sz:
            reasons.append(f"{who} at {was_px:.2f} thinning out ({was_sz / 1000:.0f}k to {left / 1000:.0f}k)")
            metrics["wall_thinning"] = True
    if wall_sz >= p.big_seller:
        vetoes.append(f"{wall_sz / 1000:.0f}k-share {who} at {wall_px:.2f}")
    elif wall_sz >= p.wall:
        thinning = start_sz > 0 and wall_sz <= (1 - p.thin_fraction) * start_sz
        metrics["wall_thinning"] = thinning
        if thinning:
            reasons.append(f"{who} at {wall_px:.2f} thinning ({start_sz / 1000:.0f}k to {wall_sz / 1000:.0f}k)")
        else:
            waits.append(f"{wall_sz / 1000:.0f}k-share {who} at {wall_px:.2f} is not thinning")

    ask_vol = bid_vol = 0.0
    ask_n = bid_n = 0
    for pr in prints:
        ts = _num(pr.get("ts") or 0)
        if ts is None or not (now - p.window_sec <= ts <= now):
            continue
        if str(pr.get("exchange") or "").upper() in OFF_EXCHANGE:
            continue
        size = _num(pr.get("size") or 0)
        if size is None or size <= 0:
            continue
        side = pr.get("side")
        if side == "ask":
            ask_vol += size
            ask_n += 1
        elif side == "bid":
            bid_vol += size
            bid_n += 1
    metrics.update({"ask_volume": ask_vol, "bid_volume": bid_vol, "ask_prints": ask_n, "bid_prints": bid_n})

    # The setup's side of the tape: a long's buyers lift the ask, a short's sellers hit the bid.
    long_side = mirror is _LONG
    with_vol, against_vol = (ask_vol, bid_vol) if long_side else (bid_vol, ask_vol)
    with_n = ask_n if long_side else bid_n
    first_inside = _levels(first_book, mirror.wall_book)
    start_px = first_inside[0][0] if first_inside else None
    start_inside = first_inside[0][1] if first_inside else 0.0
    best_px = best_ask if long_side else best_bid
    held = start_px is not None and (best_px <= start_px + 1e-9 if long_side else best_px >= start_px - 1e-9)
    if held and with_vol > 0 and start_inside > 0 and with_vol >= p.hidden_mult * start_inside:
        vetoes.append(mirror.hidden.format(k=with_vol / 1000))
    use_prints = p.entry_mode in (TAPE_ENTRY_GATE, TAPE_ENTRY_BOTH)
    use_score = p.entry_mode in (TAPE_ENTRY_SCORE, TAPE_ENTRY_BOTH)
    if use_prints and against_vol > 0 and against_vol > p.red_mult * with_vol:
        waits.append(f"burst of {mirror.burst_word} on the tape ({bid_vol / 1000:.1f}k at the bid vs "
                     f"{ask_vol / 1000:.1f}k at the ask)")
    moving = with_n >= p.min_ask_prints and with_vol > against_vol
    metrics[mirror.flow_key] = moving
    score_ok, score_said = _score_check(flow, p, mirror) if use_score else (True, "")
    if not score_ok:
        waits.append(score_said)

    if vetoes:
        return {"verdict": TAPE_VERDICT_VETO, "reasons": vetoes + waits, "metrics": metrics}
    if waits:
        return {"verdict": TAPE_VERDICT_WAIT, "reasons": waits, "metrics": metrics}
    if use_prints and not moving:
        return {"verdict": TAPE_VERDICT_WAIT, "reasons": [f"no {mirror.flow_word} on the tape yet"] + reasons,
                "metrics": metrics}
    if use_score:
        reasons.insert(0, score_said)
    if use_prints:
        reasons.insert(0, f"{mirror.flow_word} on the tape ({with_n} prints, {with_vol / 1000:.1f}k at the "
                          f"{mirror.with_print})")
    if l1_only:
        reasons.append("top of book only -- no depth line")
    return {"verdict": TAPE_VERDICT_GO, "reasons": reasons, "metrics": metrics}
