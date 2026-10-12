"""The candle that bottoms a pullback (#847): the pullback dip's two entries, read on completed candles. Pure.

The operator's material buys a pullback at its bottom two ways:

  wick   the bottoming wick -- the dip being bought: the pullback's newest candle makes the pullback's low (or ties
         it), its lower wick is at least ``wick_min`` of its range and ``wick_min_dollars``, and it closes at least
         ``close_min`` of the way up its range. Red or green: the wick is the read.
  green  the first candle to close green: the first pullback candle that closes over its open after at least
         ``min_red`` red ones (a close under the open). Only the first counts: once it has come, a later green is
         not it.

``read`` answers for the pullback's newest candle (the last of ``pullback``, the candles after the leg high):
``Entry(ok, why, final, detail)`` -- ``ok`` it is the entry, else ``why`` it is not; ``final`` when no later
candle of this pullback can be the entry (its first green close came and went). ``detail`` carries the candle's
numbers for the row and the chart: ``entry_mode``, ``entry_bar_t``, ``range``, ``lower_wick``, ``wick_pct`` (the
lower wick over the range), ``close_pct`` (0 at the low, 1 at the high) and ``red_bars`` (the red candles before
it in the pullback).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from constants_setups import SETUPS_DIP_ENTRY_GREEN, SETUPS_DIP_ENTRY_WICK
from setup_scanner.bars import Bar

EPS = 1e-9
# What a forming dip waits for, in the reason and the plan.
WAITING = {SETUPS_DIP_ENTRY_WICK: "a bottoming wick", SETUPS_DIP_ENTRY_GREEN: "the first green close"}


@dataclass(frozen=True)
class Entry:
    ok: bool
    why: str
    final: bool = False
    detail: dict[str, Any] = field(default_factory=dict)


def is_red(b: Bar) -> bool:
    return b.c < b.o - EPS


def is_green(b: Bar) -> bool:
    return b.c > b.o + EPS


def shape(b: Bar) -> dict[str, float]:
    """A candle's range, its lower wick (from the lower of open and close to the low), the wick's share of the
    range and where it closed in the range (0 at the low, 1 at the high)."""
    rng = b.h - b.lo
    lower = max(min(b.o, b.c) - b.lo, 0.0)
    return {"range": round(rng, 4), "lower_wick": round(lower, 4),
            "wick_pct": round(lower / rng, 4) if rng > EPS else 0.0,
            "close_pct": round((b.c - b.lo) / rng, 4) if rng > EPS else 0.0}


def _pct(x: float) -> str:
    return f"{round(x * 100):d}%"


def _cents(x: float) -> str:
    return f"{round(x * 100):d}c"


def _reds(pullback: Sequence[Bar]) -> int:
    return sum(1 for b in pullback[:-1] if is_red(b))


def wick(pullback: Sequence[Bar], p: Any) -> Entry:
    """The newest candle as a bottoming wick: the pullback's low, a long lower wick, a close high in the candle."""
    b = pullback[-1]
    s = shape(b)
    detail = {"entry_mode": SETUPS_DIP_ENTRY_WICK, "entry_bar_t": b.t, **s, "red_bars": _reds(pullback)}
    earlier = [x.lo for x in pullback[:-1]]
    if earlier and b.lo > min(earlier) + EPS:
        return Entry(False, f"the last candle's low {b.lo:.2f} is over the pullback's low {min(earlier):.2f}",
                     detail=detail)
    if s["range"] <= EPS:
        return Entry(False, "the last candle did not move", detail=detail)
    if s["wick_pct"] + EPS < p.wick_min or s["lower_wick"] + EPS < p.wick_min_dollars:
        return Entry(False, f"the last candle's lower wick is {_cents(s['lower_wick'])}, {_pct(s['wick_pct'])} of it -- "
                            f"a bottoming wick is {_pct(p.wick_min)} and {_cents(p.wick_min_dollars)} or more",
                     detail=detail)
    if s["close_pct"] + EPS < p.close_min:
        return Entry(False, f"the last candle closed {_pct(s['close_pct'])} up its range -- a bottoming wick closes "
                            f"{_pct(p.close_min)} up or more", detail=detail)
    return Entry(True, f"a bottoming wick: a {_cents(s['lower_wick'])} lower wick, {_pct(s['wick_pct'])} of the "
                       f"candle, closing {_pct(s['close_pct'])} up it", detail=detail)


def first_green(pullback: Sequence[Bar], min_red: int) -> int | None:
    """The index in ``pullback`` of its first candle that closes green after ``min_red`` red ones, else None."""
    reds = 0
    for i, b in enumerate(pullback):
        if reds >= min_red and is_green(b):
            return i
        if is_red(b):
            reds += 1
    return None


def green(pullback: Sequence[Bar], p: Any) -> Entry:
    """The newest candle as the first green close after ``min_red`` red pullback candles."""
    b = pullback[-1]
    reds = _reds(pullback)
    detail = {"entry_mode": SETUPS_DIP_ENTRY_GREEN, "entry_bar_t": b.t, **shape(b), "red_bars": reds}
    k = first_green(pullback, p.min_red)
    if k is None:
        if reds + (1 if is_red(b) else 0) < p.min_red:
            return Entry(False, f"{reds + (1 if is_red(b) else 0)} red candle(s) so far -- the entry is the first "
                                f"green close after {p.min_red}", detail=detail)
        return Entry(False, "no green close yet", detail=detail)
    if k < len(pullback) - 1:
        ago = len(pullback) - 1 - k
        return Entry(False, f"the first green close came {ago} candle{'' if ago == 1 else 's'} ago and was not the "
                            "entry", final=True, detail=detail)
    return Entry(True, f"the first green close after {reds} red candle{'' if reds == 1 else 's'}", detail=detail)


def read(mode: str, pullback: Sequence[Bar], p: Any) -> Entry:
    """The pullback's newest candle under the template's entry (``wick`` or ``green``)."""
    return green(pullback, p) if mode == SETUPS_DIP_ENTRY_GREEN else wick(pullback, p)
