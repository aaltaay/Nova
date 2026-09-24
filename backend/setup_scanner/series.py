"""One symbol's bar arrays and indicators, extended a bar at a time (ADR 029).

The pullback detector re-reads the whole day after every bar. Recomputing the
EMA, MACD and the high of day over every bar each time is O(n) per bar -- fine
for one live lane, but a replay rebuilding a day for several templates would
pay O(n^2). ``Series`` keeps the arrays and extends them with the same
recurrences in the same order, so every value is bit-for-bit what the full
recomputation gives (the research harness's ``ema`` / ``macd_hist``). A change
at the front (a seed that prepends older bars) rebuilds from scratch. Pure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


def ema(values: list[float], n: int) -> list[float]:
    if not values:
        return []
    a = 2.0 / (n + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(a * v + (1 - a) * out[-1])
    return out


def macd_hist(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> list[float]:
    f, s = ema(closes, fast), ema(closes, slow)
    line = [x - y for x, y in zip(f, s, strict=True)]
    sig = ema(line, signal)
    return [x - y for x, y in zip(line, sig, strict=True)]


def _extend_ema(out: list[float], values: Sequence[float], start: int, n: int) -> None:
    a = 2.0 / (n + 1)
    for i in range(start, len(values)):
        v = values[i]
        out.append(v if not out else a * v + (1 - a) * out[-1])


@dataclass
class Series:
    """Arrays over completed bars: opens, highs, lows, closes, volumes, the running
    high of day, the EMA and the MACD histogram, for one set of periods."""

    ema_period: int = 9
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    t: list[float] = field(default_factory=list)
    o: list[float] = field(default_factory=list)
    h: list[float] = field(default_factory=list)
    lo: list[float] = field(default_factory=list)
    c: list[float] = field(default_factory=list)
    v: list[float] = field(default_factory=list)
    hod: list[float] = field(default_factory=list)      # hod[i] = max(h[: i + 1])
    hod_i: list[int] = field(default_factory=list)      # the latest bar at that high (ties move it on)
    vmax_i: list[int] = field(default_factory=list)     # the first bar with the day's biggest volume so far
    e: list[float] = field(default_factory=list)        # ema(c, ema_period)
    _fast: list[float] = field(default_factory=list)
    _slow: list[float] = field(default_factory=list)
    _line: list[float] = field(default_factory=list)
    _sig: list[float] = field(default_factory=list)
    hist: list[float] = field(default_factory=list)

    def reset(self) -> None:
        for arr in (self.t, self.o, self.h, self.lo, self.c, self.v, self.hod, self.hod_i, self.vmax_i, self.e,
                    self._fast, self._slow, self._line, self._sig, self.hist):
            arr.clear()

    def update(self, bars: Sequence) -> None:
        """Bring the arrays up to ``bars`` (oldest first, each with t / o / h / lo / c / v)."""
        n = len(self.t)
        if n and (n > len(bars) or bars[0].t != self.t[0] or bars[n - 1].t != self.t[-1]):
            self.reset()
            n = 0
        for b in bars[n:]:
            self.t.append(b.t)
            self.o.append(b.o)
            self.h.append(b.h)
            self.lo.append(b.lo)
            self.c.append(b.c)
            self.v.append(float(getattr(b, "v", 0.0) or 0.0))
            i = len(self.h) - 1
            if not self.hod or b.h >= self.hod[-1]:
                self.hod.append(b.h)
                self.hod_i.append(i)
            else:
                self.hod.append(self.hod[-1])
                self.hod_i.append(self.hod_i[-1])
            self.vmax_i.append(i if not self.vmax_i or self.v[i] > self.v[self.vmax_i[-1]] else self.vmax_i[-1])
        _extend_ema(self.e, self.c, n, self.ema_period)
        _extend_ema(self._fast, self.c, n, self.macd_fast)
        _extend_ema(self._slow, self.c, n, self.macd_slow)
        for i in range(n, len(self.c)):
            self._line.append(self._fast[i] - self._slow[i])
        _extend_ema(self._sig, self._line, n, self.macd_signal)
        for i in range(n, len(self.c)):
            self.hist.append(self._line[i] - self._sig[i])

    def prior_high(self, i: int) -> float | None:
        """max(h[:i]) -- the high of day before bar ``i`` (None for the first bar)."""
        return self.hod[i - 1] if i > 0 else None

    def last_values(self) -> dict[str, float | int] | None:
        """The indicators at the last completed bar -- the values the gates read (ADR 035) -- or
        None before the first bar."""
        if not self.c:
            return None
        return {"bars_as_of": self.t[-1], "bars": len(self.c), "close": self.c[-1], "ema": round(self.e[-1], 6),
                "macd_line": round(self._line[-1], 6), "macd_signal": round(self._sig[-1], 6),
                "macd_hist": round(self.hist[-1], 6), "hod": self.hod[-1]}
