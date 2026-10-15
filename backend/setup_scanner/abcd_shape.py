"""The ABCD's shape on completed one-minute candles (operator ask 2026-10-15). Pure: the candles in, the shape out.

The operator's material draws it: the stock squeezes to the high of day, pulls back (A), pushes up and fails to make
a new high (B -- "either double-topped, or it didn't even make it to the top"), dips to a higher low (C), and breaks
the high of B (D). Real candles are never that clean, so the swings and the tolerances are read the way the flat top
reads its touches:

  swings     a zigzag: a high is a swing high once price has come down ``swing_pct`` from it, a low a swing low once
             price has come up ``swing_pct`` from it. Smaller wiggles are inside one swing.
  the high   the newest swing high that is the high of day and clears the swing high before it by more than the
             tolerance. A swing high inside the tolerance over the high is a double top: it is a B, not a new high.
  A          the first swing low after the high.
  B          the newest swing high after A. It fails the high: at most ``b_over_pct`` (or a cent) over it. It takes
             back at least ``bounce`` of the high-to-A drop: a real push, not a bounce off the low.
  C          the lowest low since B, so far. Every low after A stays at most ``c_under_pct`` (or a cent) under A: a
             lower low breaks the pattern ("we're stair stepping down").

``read`` answers where it stands now: no high to read from, waiting for A, waiting for B, broken (the reason), or
formed (B and the C so far, with the levels the detector arms with). The window (A to the break of B within
``max_minutes``) is the detector's, which knows the clock.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

EPS = 1e-9
HIGH, LOW = "H", "L"


@dataclass(frozen=True)
class Pivot:
    i: int
    price: float
    kind: str              # HIGH or LOW
    confirmed: bool        # False: the swing still running at the newest candle


@dataclass(frozen=True)
class Shape:
    """Where the ABCD stands at the newest candle. ``stage``: ``a`` (waiting for A), ``b`` (A in, waiting for B),
    ``formed`` (B and a C so far), or ``broken`` (``why``)."""

    stage: str
    high: Pivot
    a: Pivot | None = None
    b: Pivot | None = None
    c: Pivot | None = None        # the lowest low since B (formed only)
    b_max: float = 0.0            # the highest a B may reach: the high plus its tolerance
    a_floor: float = 0.0          # the lowest any low after A may reach: A minus its tolerance
    why: str | None = None


def tolerance(price: float, pct: float, dollars: float) -> float:
    """``pct`` of ``price`` or ``dollars``, whichever is more (the flat top's touch, ``flat_top_shape.tolerance``)."""
    return max(float(pct) * float(price), float(dollars))


def zigzag(h: Sequence[float], lo: Sequence[float], swing: float) -> list[Pivot]:
    """Alternating swing highs and lows over the candles, oldest first; the last one is the swing still running.

    It starts looking for a high from the first candle (a day opens on its way somewhere): a high is confirmed when a
    later low is ``swing`` under it, a low when a later high is ``swing`` over it."""
    if not h:
        return []
    out: list[Pivot] = []
    up, ei, ev = True, 0, h[0]
    for i in range(len(h)):
        if up:
            if h[i] >= ev:
                ei, ev = i, h[i]
            elif lo[i] <= ev * (1 - swing) + EPS:
                out.append(Pivot(ei, ev, HIGH, True))
                up, ei, ev = False, i, lo[i]
        else:
            if lo[i] <= ev:
                ei, ev = i, lo[i]
            elif h[i] >= ev * (1 + swing) - EPS:
                out.append(Pivot(ei, ev, LOW, True))
                up, ei, ev = True, i, h[i]
    out.append(Pivot(ei, ev, HIGH if up else LOW, False))
    return out


def _high(pivots: list[Pivot], hod: Sequence[float], p: Any) -> int | None:
    """The index in ``pivots`` of the high the ABCD reads from (the module's "the high"), or None."""
    at: int | None = None
    for k, pv in enumerate(pivots):
        if pv.kind != HIGH or not pv.confirmed or pv.price < hod[pv.i] - EPS:
            continue
        prev = pivots[at].price if at is not None else None
        if prev is None or pv.price > prev + tolerance(prev, p.b_over_pct, p.tol_dollars) + EPS:
            at = k
    return at


def read(h: Sequence[float], lo: Sequence[float], hod: Sequence[float], p: Any) -> Shape | None:
    """The ABCD at the newest candle (``h``, ``lo``: the day's candles' highs and lows; ``hod`` the high of day
    through each), or None while no swing high is the high of day."""
    pivots = zigzag(h, lo, p.swing_pct)
    k = _high(pivots, hod, p)
    if k is None:
        return None
    high = pivots[k]
    b_max = high.price + tolerance(high.price, p.b_over_pct, p.tol_dollars)
    rest = pivots[k + 1:]
    if not rest or not rest[0].confirmed:
        return Shape("a", high, b_max=b_max)
    a = rest[0]
    a_floor = a.price - tolerance(a.price, p.c_under_pct, p.tol_dollars)
    after = range(a.i + 1, len(lo))
    under = next((i for i in after if lo[i] < a_floor - EPS), None)
    if under is not None:
        return Shape("broken", high, a=a, b_max=b_max, a_floor=a_floor,
                     why=f"a low of {lo[under]:.2f} undercut A {a.price:.2f}: stair-stepping down")
    highs = [pv for pv in rest[1:] if pv.kind == HIGH and pv.confirmed]
    if not highs:
        return Shape("b", high, a=a, b_max=b_max, a_floor=a_floor)
    b = highs[-1]
    if b.price - a.price < p.bounce * (high.price - a.price) - EPS:
        return Shape("b", high, a=a, b=b, b_max=b_max, a_floor=a_floor,
                     why=f"B {b.price:.2f} took back under {round(p.bounce * 100):d}% of the drop to A: "
                         "wait for a real push")
    ci = min(range(b.i + 1, len(lo)), key=lambda i: (lo[i], -i))
    return Shape("formed", high, a=a, b=b, c=Pivot(ci, lo[ci], LOW, False), b_max=b_max, a_floor=a_floor)


def points(s: Shape, t: Sequence[float]) -> dict[str, Any]:
    """The shape for the wire: each point ``[candle time, price]`` (None until it is in), and the tolerances."""
    def pt(pv: Pivot | None) -> list[float] | None:
        return None if pv is None else [t[pv.i], round(pv.price, 4)]
    return {"high": pt(s.high), "a": pt(s.a), "b": pt(s.b), "c": pt(s.c),
            "b_max": round(s.b_max, 4), "a_floor": round(s.a_floor, 4) if s.a is not None else None}
