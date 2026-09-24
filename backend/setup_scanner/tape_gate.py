"""The tape gate: read the live Level 2 and time and sales at a trigger.

A setup on the bars is a hypothesis; the gate is the check the source
material makes before pressing buy (ADR 022, Bot-Trading-Plan section 2g):

  veto   the spread is too wide; a seller of 100k+ shares sits at the level;
         buyers are lifting the ask but it does not move (a hidden seller)
  wait   a 25k+ seller sits at the level and is not thinning; a burst of red
         on the tape; no green on the tape yet
  go     green on the tape (prints at the ask outweigh prints at the bid) and
         no wall at the level, or the wall is being eaten
  blind  no fresh book -- Nova holds no Level 2 line for the symbol

A template may decide the entry by the tape flow score instead (ADR 034,
``entry_mode``): ``gate`` is the rule above; ``score`` keeps the vetoes and a
wall that is not thinning, and replaces the green / red print counts with the
flow score at or over ``entry_min_score``; ``both`` needs the green prints and
the score. The flow reading rides on every answer as ``flow``.

Pure: the engine hands in the book samples and prints it saw in the window.
Prints carry the side the live tape stamped against the book at receipt
(``ibkr/tape_side.py``); off-exchange (FINRA / TRF) reports are left out, as
the material filters them.
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


def _wall(book: dict | None, trigger: float, band: float) -> tuple[float | None, float]:
    """Biggest single ask level from one cent under the trigger to ``band`` over it."""
    best_px, best_sz = None, 0.0
    for px, sz in _levels(book, "asks"):
        if trigger - 0.01 - 1e-9 <= px <= trigger + band + 1e-9 and sz > best_sz:
            best_px, best_sz = px, sz
    return best_px, best_sz


def _size_at(book: dict | None, price: float) -> float:
    return sum(sz for px, sz in _levels(book, "asks") if abs(px - price) < 1e-6)


def _score_check(flow: dict | None, p: GateParams) -> tuple[bool, str]:
    """Whether the flow score clears the template's entry minimum, and the reason in words."""
    if not isinstance(flow, dict) or flow.get("label") == TAPE_FLOW_BLIND:
        return False, "no flow reading"
    score = flow.get("score")
    if flow.get("label") == TAPE_FLOW_QUIET or score is None:
        return False, "the tape is too quiet to score"
    if score >= p.entry_min_score - 1e-9:
        return True, f"flow {score:+.2f} ({flow.get('label')})"
    return False, f"flow {score:+.2f} is under {p.entry_min_score:+.2f}"


def evaluate(*, trigger: float, now: float, books: Iterable[tuple[float, dict]],
             prints: Iterable[dict], p: GateParams = DEFAULT_GATE, flow: dict | None = None) -> dict[str, Any]:
    """Judge the tape at ``trigger`` from the samples inside the window ending at ``now``."""
    res = _evaluate(trigger=trigger, now=now, books=books, prints=prints, p=p, flow=flow)
    if flow is not None:
        res["flow"] = flow
        res["metrics"]["flow_score"] = flow.get("score")
    res["metrics"]["entry_mode"] = p.entry_mode
    return res


def _evaluate(*, trigger: float, now: float, books: Iterable[tuple[float, dict]],
              prints: Iterable[dict], p: GateParams, flow: dict | None) -> dict[str, Any]:
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

    wall_px, wall_sz = _wall(book, trigger, p.band)
    start_sz = _size_at(first_book, wall_px) if wall_px is not None else 0.0
    metrics.update({"wall_price": wall_px, "wall_size": wall_sz, "wall_size_start": start_sz})
    # A wall that was there at the start of the window and has been eaten below
    # the threshold is the strongest "go" the material describes -- say so.
    was_px, was_sz = _wall(first_book, trigger, p.band)
    if was_px is not None and was_sz >= p.wall and wall_sz < p.wall:
        left = _size_at(book, was_px)
        if left <= (1 - p.thin_fraction) * was_sz:
            reasons.append(f"seller at {was_px:.2f} thinning out ({was_sz / 1000:.0f}k to {left / 1000:.0f}k)")
            metrics["wall_thinning"] = True
    if wall_sz >= p.big_seller:
        vetoes.append(f"{wall_sz / 1000:.0f}k-share seller at {wall_px:.2f}")
    elif wall_sz >= p.wall:
        thinning = start_sz > 0 and wall_sz <= (1 - p.thin_fraction) * start_sz
        metrics["wall_thinning"] = thinning
        if thinning:
            reasons.append(f"seller at {wall_px:.2f} thinning ({start_sz / 1000:.0f}k to {wall_sz / 1000:.0f}k)")
        else:
            waits.append(f"{wall_sz / 1000:.0f}k-share seller at {wall_px:.2f} is not thinning")

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

    first_asks = _levels(first_book, "asks")
    start_ask = first_asks[0][0] if first_asks else None
    start_inside = first_asks[0][1] if first_asks else 0.0
    if (start_ask is not None and ask_vol > 0 and start_inside > 0
            and ask_vol >= p.hidden_mult * start_inside and best_ask <= start_ask + 1e-9):
        vetoes.append(f"hidden seller: {ask_vol / 1000:.1f}k bought at the ask and the ask did not move")
    use_prints = p.entry_mode in (TAPE_ENTRY_GATE, TAPE_ENTRY_BOTH)
    use_score = p.entry_mode in (TAPE_ENTRY_SCORE, TAPE_ENTRY_BOTH)
    if use_prints and bid_vol > 0 and bid_vol > p.red_mult * ask_vol:
        waits.append(f"burst of red on the tape ({bid_vol / 1000:.1f}k at the bid vs {ask_vol / 1000:.1f}k at the ask)")
    green = ask_n >= p.min_ask_prints and ask_vol > bid_vol
    metrics["green_flow"] = green
    score_ok, score_said = _score_check(flow, p) if use_score else (True, "")
    if not score_ok:
        waits.append(score_said)

    if vetoes:
        return {"verdict": TAPE_VERDICT_VETO, "reasons": vetoes + waits, "metrics": metrics}
    if waits:
        return {"verdict": TAPE_VERDICT_WAIT, "reasons": waits, "metrics": metrics}
    if use_prints and not green:
        return {"verdict": TAPE_VERDICT_WAIT, "reasons": ["no green on the tape yet"] + reasons, "metrics": metrics}
    if use_score:
        reasons.insert(0, score_said)
    if use_prints:
        reasons.insert(0, f"green on the tape ({ask_n} prints, {ask_vol / 1000:.1f}k at the ask)")
    if l1_only:
        reasons.append("top of book only -- no depth line")
    return {"verdict": TAPE_VERDICT_GO, "reasons": reasons, "metrics": metrics}
