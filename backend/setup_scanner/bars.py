"""The setup scanner's one-minute bars for one symbol.

Live bars come from ``ibkr/l1_minute`` -- the minute buckets Nova already
builds from the IBKR Level 1 lines of the scanner rosters and the HOD Momo
active set (open / high / low / close from the Level 1 last, volume from the
change in cumulative day volume). A print that fell between two Level 1
updates can be missing from a bar's range; these bars feed the detector and
are never drawn as a chart. The day so far is seeded once from the bar store
(``bars_intraday``), the same bars the chart reads. A minute with no update
has no bar, like the flat files the research used.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from constants_setups import SETUPS_BAR_SEC

MAX_BARS_PER_SYMBOL = 16 * 60  # 04:00-20:00


@dataclass
class Bar:
    t: float      # epoch seconds, start of the minute
    o: float
    h: float
    lo: float     # the bar's low (wire key "l")
    c: float
    v: float = 0.0

    def as_dict(self) -> dict:
        return {"t": self.t, "o": self.o, "h": self.h, "l": self.lo, "c": self.c, "v": self.v}


def minute_start(ts: float) -> float:
    return float(int(ts // SETUPS_BAR_SEC) * SETUPS_BAR_SEC)


def bar_from(raw: dict[str, Any]) -> Bar | None:
    """A bar from an ``l1_minute`` payload or a bar-store row ({t,o,h,l,c,v})."""
    try:
        t = raw["t"]
        if isinstance(t, str):
            from datetime import datetime

            t = datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
        bar = Bar(float(t), float(raw["o"]), float(raw["h"]), float(raw["l"]), float(raw["c"]),
                  float(raw.get("v") or 0.0))
    except (KeyError, TypeError, ValueError):
        return None
    if not (bar.h >= bar.lo > 0):
        return None
    return bar


@dataclass
class MinuteBars:
    """Completed bars for one symbol, oldest first."""

    symbol: str
    completed: list[Bar] = field(default_factory=list)
    open_bar_open: float | None = None   # open of the minute now forming (for gap-over fills)

    def append(self, bar: Bar) -> bool:
        """Add a completed bar. A bar at or before the last one is ignored (seed overlap)."""
        if self.completed and bar.t <= self.completed[-1].t:
            return False
        self.completed.append(bar)
        if len(self.completed) > MAX_BARS_PER_SYMBOL:
            del self.completed[: len(self.completed) - MAX_BARS_PER_SYMBOL]
        return True

    def seed(self, bars: Iterable[Bar]) -> int:
        """Warm up with stored bars older than anything live. Returns the count kept."""
        first_live = self.completed[0].t if self.completed else None
        older = sorted((b for b in bars if first_live is None or b.t < first_live), key=lambda b: b.t)
        self.completed = older + self.completed
        return len(older)
