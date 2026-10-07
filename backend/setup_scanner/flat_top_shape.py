"""The flat top's shape on completed candles (ADR 031, amended 2026-10-06): the level, the candles that
touched it, and the base under it.

The operator's material draws a flat top as a stock that ran up and then taps the same price -- the high of
day -- again and again: its candles' highs at or just under it, their closes a little under it, the 9 EMA
rising under them, until it breaks. A real one is never perfect, so a high within the tolerance under the
level touched it (``tolerance``: a share of the level or a dollar floor, whichever is more). A candle a cent or
two over the earlier touches, still inside the tolerance, is a touch too: the level is the high of day, and
every touch is read against it.

``find`` reads the candles at ``last``:

  level      the high of day so far (the trigger)
  zone       level less the tolerance: a candle whose high is at or over it touched the flat top
  first      the first touch: the earliest candle in the zone from which every later close stays within
             ``band`` under the level and every later low at or above the EMA (less ``ema_tol``), and whose
             run-up is an impulse: the level at least ``impulse_pct`` over the lowest low of the
             ``leg_window`` candles ending at it. The base is the candles after it.
  touches    every candle from the first on whose high touched the zone
  retested   a touch after the first made no new high: the level was tapped, not pushed through -- a run
             of rising highs a cent apart is a move, not a flat top

A flat top whose first touch is more than ``max_consol`` candles back is stale. A base of one candle is read
too, so a flat top shows forming at its second touch; arming needs ``min_consol``. With ``base_start =
"last_high"`` -- the research's P2 rule -- the first is the last candle at the high itself, the nearest that
leaves ``min_consol`` candles after it, and touches are counted from there; ``P2_RULE`` holds the values that
run it exactly. Pure: the lane's ``Series`` in, a ``Shape`` or a ``Miss`` out.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from constants_setups import SETUPS_FT_BASE_FIRST_TOUCH, SETUPS_FT_BASE_LAST_HIGH

EPS = 1e-9

# The research's pre-registered P2 rule (Bot-Trading-Plan section 2f) in the flat top's params: a template with
# these values runs it exactly -- the base right after the last candle at the high, 2-6 candles, no touch count.
P2_RULE: dict[str, Any] = {"base_start": SETUPS_FT_BASE_LAST_HIGH, "min_touches": 1, "touch_pct": 0.0,
                           "touch_dollars": 0.0, "max_consol": 6}


def pct_words(x: float) -> str:
    return f"{100 * x:.1f}".rstrip("0").rstrip(".")


def tolerance(p: Any, level: float) -> float:
    """How far under the flat top a high still touched it: ``touch_pct`` of the level or ``touch_dollars``,
    whichever is more."""
    return max(float(p.touch_pct) * level, float(p.touch_dollars))


@dataclass(frozen=True)
class Shape:
    """A flat top at ``last``: candle indexes into the lane's series."""

    first: int
    last: int
    level: float
    zone: float
    touches: tuple[int, ...]
    base_low: float
    impulse_low: float
    retested: bool

    @property
    def bars(self) -> int:
        """The base: candles after the first touch."""
        return self.last - self.first

    @property
    def pct(self) -> float:
        return round(self.level / self.impulse_low - 1, 4)


@dataclass(frozen=True)
class Miss:
    """Why no flat top stands at ``last``: the candle the base would start from, its impulse's low, the rule."""

    first: int
    impulse_low: float
    why: str


def impulse_low(s: Any, top: int, level: float, p: Any) -> float | None:
    """The lowest low of the ``leg_window`` candles ending at ``top`` when the level is an impulse over it."""
    low = min(s.lo[max(0, top - p.leg_window + 1):top + 1])
    if low <= 0 or level / low - 1 < p.impulse_pct:
        return None
    return low


def base_problem(s: Any, first: int, last: int, level: float, p: Any) -> str | None:
    """The rule a base candle after ``first`` broke, or None."""
    base = range(first + 1, last + 1)
    if any(s.c[i] < level * (1 - p.band) for i in base):
        return f"a base candle closed more than {pct_words(p.band)}% under the {level:.2f} high"
    if any(s.lo[i] < s.e[i] * (1 - p.ema_tol) for i in base):
        return "a base candle's low broke the 9 EMA"
    return None


def find(s: Any, last: int, p: Any) -> tuple[Shape | None, Miss | None]:
    """The flat top at ``last`` (its touches may be fewer than the rule needs), and why one was not taken.

    The ``Miss`` is the shortest base's broken rule, or -- for a flat top that began more than
    ``max_consol`` candles back -- that it went stale (then no shape is returned)."""
    level = s.hod[last]
    zone = level - tolerance(p, level)
    first_touch = p.base_start == SETUPS_FT_BASE_FIRST_TOUCH
    if first_touch:
        order = range(p.max_consol + p.leg_window, 0, -1)
    else:
        order = range(p.min_consol, p.max_consol + 1)
    miss: Miss | None = None
    for m in order:
        top = last - m
        if top < p.leg_window:
            continue
        if (s.h[top] < zone - EPS) if first_touch else (s.h[top] != level):
            continue
        low = impulse_low(s, top, level, p)
        if low is None:
            continue                  # no impulse into the level: not a flat top at all
        why = base_problem(s, top, last, level, p)
        if why:
            if first_touch or miss is None:
                miss = Miss(top, low, why)        # the shortest base's rule: the latest checked here
            continue
        if m > p.max_consol:
            return None, Miss(top, low, f"the base ran past {p.max_consol} candles without a break")
        touches = tuple(i for i in range(top, last + 1) if s.h[i] >= zone - EPS)
        retested = any(s.h[i] <= max(s.h[top:i]) + EPS for i in touches[1:])
        return Shape(first=top, last=last, level=level, zone=round(zone, 6), touches=touches,
                     base_low=min(s.lo[top + 1:last + 1]), impulse_low=low, retested=retested), miss
    return None, miss


def leg(s: Any, shape: Shape) -> dict[str, Any]:
    """The setup's context as the board, the journal and the charts carry it: the flat top from its first
    touch -- the level, the impulse's low, the base's candles, every touch ``[t, high]`` and the zone."""
    return {"t": s.t[shape.first], "high": shape.level, "low": shape.impulse_low, "pct": shape.pct,
            "bars": shape.bars, "touches": [[s.t[i], s.h[i]] for i in shape.touches], "zone": shape.zone}
