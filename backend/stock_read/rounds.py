"""The round numbers a price is watched at (operator report 2026-10-01). Pure.

A stock's round numbers scale with its price (``STOCK_READ_ROUND_LADDER``): the half and whole dollars
up to $25, the whole and $5 numbers to $50, the $5 and $10 numbers from $125 to $250, and so on, so a
minor round is always 2% of the price or more. ACN at $223 had read every half dollar as a level: 26
lines between its stop and its target, and its real tops and VWAP buried in zones of six half dollars.

Every reader of round numbers -- the level map, the plan's notes, marks and checks, and the read's
next-round row -- takes them from here, for the one price the read is about, so a target over $25 on a
$24.90 stock is read on the stock's scale. The level study measured half and whole dollars on $1-$20
stocks only (``measured``); on any other price the plan names the rounds and says they are not measured.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from constants_stock_read import (
    STOCK_READ_ROUND_LADDER,
    STOCK_READ_ROUND_MEASURED_MAX,
    STOCK_READ_ROUND_MEASURED_MIN,
    STOCK_READ_ROUND_NEAR_SHARE,
)

EPS = 1e-9
HALF_AND_WHOLE = (0.5, 1.0)


def money(x: float) -> str:
    """A step in a few characters: "$5", "$2.50", "$0.50"."""
    return f"${x:.0f}" if abs(x - round(x)) < EPS else f"${x:.2f}"


@dataclass(frozen=True)
class Rounds:
    """A price's two sizes of round number: every multiple of ``minor`` is one, and a multiple of
    ``major`` is the heavier kind (the map's ``whole``; the rest are its ``half``)."""

    minor: float
    major: float
    price: float

    @property
    def half_and_whole(self) -> bool:
        """The half and whole dollars: the rounds the level study and trial T7 are about."""
        return (self.minor, self.major) == HALF_AND_WHOLE

    @property
    def measured(self) -> bool:
        """The level study measured these rounds on a stock at this price."""
        return self.half_and_whole and STOCK_READ_ROUND_MEASURED_MIN <= self.price <= STOCK_READ_ROUND_MEASURED_MAX

    @property
    def near(self) -> float:
        """A target or stop this close to a round is on it (5c at a half dollar)."""
        return self.minor * STOCK_READ_ROUND_NEAR_SHARE

    @property
    def words(self) -> str:
        """"half and whole dollars", "$5 and $10 round numbers"."""
        if self.half_and_whole:
            return "half and whole dollars"
        return f"{money(self.minor)} and {money(self.major)} round numbers"

    def is_major(self, p: float) -> bool:
        return abs(p / self.major - round(p / self.major)) < EPS

    def name(self, p: float) -> str:
        """What one round is: "whole dollar", "half dollar", "$10 round number", "$5 round number"."""
        if self.half_and_whole:
            return "whole dollar" if self.is_major(p) else "half dollar"
        return f"{money(self.major if self.is_major(p) else self.minor)} round number"

    def above(self, p: float) -> float:
        """The next round strictly over ``p``."""
        return round((math.floor(p / self.minor + EPS) + 1) * self.minor, 2)

    def at_or_below(self, p: float) -> float:
        return round(math.floor(p / self.minor + EPS) * self.minor, 2)

    def between(self, lo: float, hi: float) -> list[float]:
        """Every round strictly between ``lo`` and ``hi``, cheapest first."""
        out, r = [], self.above(lo)
        while r < hi - EPS:
            out.append(r)
            r = round(r + self.minor, 2)
        return out

    def unmeasured(self) -> str:
        """The sentence that stands in for the study's figures where the study did not look."""
        return (f"Nova's level study measured half and whole dollars on $1-$20 stocks; how {self.words} hold "
                f"on a ${self.price:,.2f} stock is not measured.")

    def wire(self) -> dict[str, Any]:
        return {"minor": self.minor, "major": self.major, "measured": self.measured, "words": self.words}


def of(price: float | None) -> Rounds | None:
    """The round numbers of a stock at ``price``; None without a price."""
    if price is None or not price > 0:
        return None
    for top, minor, major in STOCK_READ_ROUND_LADDER:
        if price <= top + EPS:
            return Rounds(float(minor), float(major), float(price))
    return None

