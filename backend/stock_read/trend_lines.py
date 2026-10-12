"""The obvious trend lines on a chart's own candles (ADR 036 amendment 2026-10-12). Pure.

Operator ask (2026-10-12): "When we see an obvious ascending line and descending line, can we have them part of
the strategy? Like it show in the chart obvious line for the long and short positions?"; "some tolerance because
I doubt there will just be perfect ascending or descending trend lines"; "It's like what visually make sense, and
I think we r gonna need that on the 1min and 5min charts". ADR 036 had left them out for want of a rule for which
two points to join. The rule:

- **Support** rises through the candles' swing lows, **resistance** falls through their swing highs (the level
  map's swing rule: a low under the two candles before it and no higher than the two after).
- A line joins two swing points. Its **band** is ``max(STOCK_READ_LINE_TOUCH_PCT x the line, STOCK_READ_LINE_TOUCH_MIN)``
  -- the flat top's tolerance -- because no stock prints a perfect line.
- A swing low **touches** a support line when its low reaches the band and its body stays over the band's floor:
  a wick may poke through, the body holds. A resistance line is the mirror.
- It is a line with ``STOCK_READ_LINE_MIN_TOUCHES`` touches or more over ``STOCK_READ_LINE_MIN_SPAN_BARS`` candles,
  no candle closing through the band from the first touch to the last, and a rise (fall) of
  ``STOCK_READ_LINE_MIN_RISE`` bands from the first touch to the last: a flatter one is a horizontal level, which
  the level map draws already (a double bottom, a triple top).
- **Broke**: the first candle after the last touch to close through the band. A broken line stays
  ``STOCK_READ_LINE_KEEP_BARS`` candles so the chart and the plan can say it broke, then goes. **Retested**: a
  later candle reached the band from the other side and closed back away from it (support became resistance).
- Per kind and chart: the holding line in play -- running within ``STOCK_READ_LINE_NEAR_PCT`` of the price now -- with
  the most touches (then the longest, then the latest), and the latest broken one, unless the holding line was
  touched after that break: the line was redrawn, and the old one is not drawn beside it.

The lines are read one step per candle, as the chart draws them, so a minute without a trade is no gap in a line.
Nothing here decides a trade: ``line_notes`` says what a plan's entry, stop and target have against them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from constants_stock_read import (
    STOCK_READ_LEVEL_SWING_BARS,
    STOCK_READ_LINE_KEEP_BARS,
    STOCK_READ_LINE_MAX_SWINGS,
    STOCK_READ_LINE_MIN_RISE,
    STOCK_READ_LINE_MIN_SPAN_BARS,
    STOCK_READ_LINE_MIN_TOUCHES,
    STOCK_READ_LINE_NEAR_PCT,
    STOCK_READ_LINE_TOUCH_MIN,
    STOCK_READ_LINE_TOUCH_PCT,
)
from stock_read.level_map import EPS, hhmm

SUPPORT = "support"
RESISTANCE = "resistance"
CHART_WORDS = {"one_minute": "1-min", "five_minute": "5-min"}


@dataclass(frozen=True)
class LineRules:
    touch_pct: float = STOCK_READ_LINE_TOUCH_PCT
    touch_min: float = STOCK_READ_LINE_TOUCH_MIN
    min_touches: int = STOCK_READ_LINE_MIN_TOUCHES
    min_rise: float = STOCK_READ_LINE_MIN_RISE
    min_span: int = STOCK_READ_LINE_MIN_SPAN_BARS
    keep: int = STOCK_READ_LINE_KEEP_BARS
    max_swings: int = STOCK_READ_LINE_MAX_SWINGS
    near_pct: float = STOCK_READ_LINE_NEAR_PCT
    swing: int = STOCK_READ_LEVEL_SWING_BARS

    def band(self, p: float) -> float:
        return max(self.touch_pct * abs(p), self.touch_min)


RULES = LineRules()


def swing_points(vals: list[float], sign: int, side: int) -> list[int]:
    """Indexes of the swing highs (``sign`` 1) or lows (-1): past the ``side`` candles before, at least even with
    the ``side`` after. The last ``side`` candles cannot be one yet."""
    s = [v * sign for v in vals]
    return [i for i in range(side, len(s) - side)
            if s[i] > max(s[i - side:i]) + EPS and s[i] >= max(s[i + 1:i + side + 1]) - EPS]


@dataclass
class _Trace:
    a: int
    slope: float
    p0: float
    touches: list[int]
    broke: int | None

    def at(self, i: int) -> float:
        return self.p0 + self.slope * (i - self.a)


def _trace(bars: list[dict[str, Any]], kind: str, swings: set[int], a: int, b: int,
           rules: LineRules) -> _Trace | None:
    """The line through swing points ``a`` and ``b`` walked from ``a`` to its break (or the last candle); None
    when a candle closes through it before ``b``."""
    key = "l" if kind == SUPPORT else "h"
    p0 = float(bars[a][key])
    slope = (float(bars[b][key]) - p0) / (b - a)
    up = kind == SUPPORT
    touches: list[int] = []
    for i in range(a, len(bars)):
        line = p0 + slope * (i - a)
        tol = rules.band(line)
        c = float(bars[i]["c"])
        if (c < line - tol) if up else (c > line + tol):
            if i <= b:
                return None
            return _Trace(a, slope, p0, touches, i)
        if i in swings:
            o = float(bars[i]["o"])
            if up and float(bars[i]["l"]) <= line + tol and min(o, c) >= line - tol:
                touches.append(i)
            elif not up and float(bars[i]["h"]) >= line - tol and max(o, c) <= line + tol:
                touches.append(i)
    return _Trace(a, slope, p0, touches, None)


def _shape(tr: _Trace, rules: LineRules) -> tuple[int, int, int] | None:
    """``(touches, span, last)`` of a line that is one under the rules, else None."""
    n = len(tr.touches)
    if n < rules.min_touches:
        return None
    first, last = tr.touches[0], tr.touches[-1]
    if last - first < rules.min_span:
        return None
    if abs(tr.at(last) - tr.at(first)) < rules.min_rise * rules.band(tr.at(first)) - EPS:
        return None
    return n, last - first, last


def _retest(bars: list[dict[str, Any]], kind: str, tr: _Trace, rules: LineRules) -> int | None:
    """The first candle after the break that reached the band from the other side and closed back away."""
    if tr.broke is None:
        return None
    for i in range(tr.broke + 1, len(bars)):
        line = tr.at(i)
        tol = rules.band(line)
        b = bars[i]
        if kind == SUPPORT and float(b["h"]) >= line - tol and float(b["c"]) < line - EPS:
            return i
        if kind == RESISTANCE and float(b["l"]) <= line + tol and float(b["c"]) > line + EPS:
            return i
    return None


def _wire(bars: list[dict[str, Any]], kind: str, tr: _Trace, home: str, price: float | None,
          rules: LineRules) -> dict[str, Any]:
    key = "l" if kind == SUPPORT else "h"
    last = len(bars) - 1
    first_t, last_t = tr.touches[0], tr.touches[-1]
    now_p = tr.at(last)
    tol = rules.band(now_p)
    side = None if price is None else ("above" if now_p > price + tol else "below" if now_p < price - tol else "at")
    dir_word = "ascending" if tr.slope > 0 else "descending"
    n = len(tr.touches)
    retest = _retest(bars, kind, tr, rules)
    broke = None
    if tr.broke is not None:
        broke = {"t": float(bars[tr.broke]["t"]), "p": round(tr.at(tr.broke), 4), "close": float(bars[tr.broke]["c"])}
    times = ", ".join(hhmm(bars[i]["t"]) for i in tr.touches)
    note = f"{n} touches: {times}"
    if broke is not None:
        note += f"; a candle closed {'under' if kind == SUPPORT else 'over'} it at {hhmm(broke['t'])}"
        if retest is not None:
            note += f", and the {hhmm(bars[retest]['t'])} candle tested it from the other side and turned"
    return {
        "id": f"{home}:{kind}:{int(float(bars[first_t]['t']))}",
        "home": home,
        "kind": kind,
        "dir": "up" if tr.slope > 0 else "down",
        "state": "holding" if tr.broke is None else "broken",
        "touches": [{"t": float(bars[i]["t"]), "p": round(tr.at(i), 4), "x": float(bars[i][key])} for i in tr.touches],
        "t1": float(bars[first_t]["t"]), "p1": round(tr.at(first_t), 4),
        "t2": float(bars[last_t]["t"]), "p2": round(tr.at(last_t), 4),
        "now_t": float(bars[last]["t"]), "now_p": round(now_p, 4),
        "slope": round(tr.slope, 6),
        "band": round(tol, 4),
        "side": side,
        "broke": broke,
        "retest_t": float(bars[retest]["t"]) if retest is not None else None,
        "label": f"{dir_word} {kind} · {n} touches",
        "tag": f"{'↗' if tr.slope > 0 else '↘'} {kind}",
        "note": note,
    }


def find(bars: list[dict[str, Any]], *, home: str, price: float | None,
         rules: LineRules = RULES) -> list[dict[str, Any]]:
    """The chart's lines from its closed candles (``{t, o, h, l, c}``, oldest first): per kind the holding line
    and the latest broken one still inside ``rules.keep`` candles of its break."""
    out: list[dict[str, Any]] = []
    if len(bars) < 2 * rules.swing + 3:
        return out
    last = len(bars) - 1
    for kind, key, sign in ((SUPPORT, "l", -1), (RESISTANCE, "h", 1)):
        pts = swing_points([float(b[key]) for b in bars], sign, rules.swing)[-rules.max_swings:]
        swings = set(pts)
        best_hold: tuple[tuple[int, int, int], _Trace] | None = None
        best_broke: tuple[tuple[int, int, int], _Trace] | None = None
        for j, a in enumerate(pts):
            pa = float(bars[a][key])
            for b in pts[j + 1:]:
                pb = float(bars[b][key])
                if (pb <= pa + EPS) if kind == SUPPORT else (pb >= pa - EPS):
                    continue
                tr = _trace(bars, kind, swings, a, b, rules)
                if tr is None:
                    continue
                score = _shape(tr, rules)
                if score is None:
                    continue
                if tr.broke is None:
                    if price is not None and abs(tr.at(last) - price) > rules.near_pct * price + EPS:
                        continue
                    if best_hold is None or score > best_hold[0]:
                        best_hold = (score, tr)
                elif last - tr.broke < rules.keep:
                    # The latest break first, then the most touches.
                    rank = (tr.broke, score[0], score[1], score[2])
                    if best_broke is None or rank > (best_broke[1].broke, *best_broke[0]):
                        best_broke = (score, tr)
        if best_hold is not None and best_broke is not None and best_hold[1].touches[-1] > (best_broke[1].broke or 0):
            best_broke = None
        for found in (best_hold, best_broke):
            if found is not None:
                out.append(_wire(bars, kind, found[1], home, price, rules))
    return out


def build(bars_1m: list[dict[str, Any]], bars_5m: list[dict[str, Any]], *, price: float | None) -> dict[str, Any]:
    """``{one_minute, five_minute}``: each chart's lines from its own candles."""
    return {"one_minute": find(bars_1m, home="one_minute", price=price),
            "five_minute": find(bars_5m, home="five_minute", price=price)}

