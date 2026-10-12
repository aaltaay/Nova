"""The target menu (operator decisions 2026-10-09 and 2026-10-12, #845). Pure.

"These 2:1 ratio is too simple and should be completely removed": exits follow the levels the operator's
material sells at, in two halves. Every setup scanner, the stock read's plan and held card, and the eyes'
side-by-side scores take their targets from here, so a target means the same thing everywhere.

The kinds a strategy can pick for each half (a short mirrors every one under its entry):

  fixed          an amount over the entry (the material's 10-30c; 20c by default)
  next_level     1c under the next zone of today's map over the entry (half and whole dollars, the high of
                 day, VWAP, tested tops ...: ``stock_read.level_map``)
  pullback_high  the high the pullback came from (the leg, the pole, the break; a short: the low the bounce
                 came from) -- the setup names it, and a setup without one has none
  hod            1c under the high of day (a short: 1c over the low of day)

and the two defaults:

  round_or_fixed (target 1)  the fixed amount, or 1c under the next half / whole dollar (the stock's own round
                             scale, ``stock_read.rounds``) when that is closer
  hod_or_level   (target 2)  1c under the high of day when that is at least ``SETUPS_TARGET2_MIN_GAP`` past
                             target 1, else 1c under the next level of today's map past target 1, else none

A target nearer the entry than ``SETUPS_TARGET_MIN_GAIN`` is none: its level does not count. Target 1 that a
kind cannot give falls back to the fixed amount, and says so. Target 2 is any kind's price at least
``SETUPS_TARGET2_MIN_GAP`` past target 1, else none -- everything then sells at target 1
(``target1_fraction`` 1.0). With a target 2, ``split`` of the shares sell at target 1.

A stop choice sits beside the pattern's own: ``round`` puts it ``SETUPS_STOP_ROUND_CENTS`` under the nearest
half / whole dollar under the entry, when that risk is inside the strategy's cap and over its floor; otherwise
the pattern's stop stands, and says why.

The wire every setup row, plan and held block carries (``Targets.wire``): ``target1`` (the first half's
price), ``target2`` (float or null), ``target1_fraction`` (0.5 with a target 2, 1.0 without) and ``targets``
(``{first: {kind, price, why}, second: {kind, price, why} | null, hod, pullback_high, stop, rule}``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from constants_setups import (
    SETUPS_STOP_PATTERN,
    SETUPS_STOP_ROUND,
    SETUPS_STOP_ROUND_CENTS,
    SETUPS_TARGET1_DEFAULT,
    SETUPS_TARGET2_DEFAULT,
    SETUPS_TARGET2_MIN_GAP,
    SETUPS_TARGET_FIXED,
    SETUPS_TARGET_FIXED_DOLLARS,
    SETUPS_TARGET_HOD,
    SETUPS_TARGET_HOD_OR_LEVEL,
    SETUPS_TARGET_LEVEL_CENT,
    SETUPS_TARGET_MIN_GAIN,
    SETUPS_TARGET_NEXT_LEVEL,
    SETUPS_TARGET_NONE,
    SETUPS_TARGET_PULLBACK_HIGH,
    SETUPS_TARGET_ROUND_OR_FIXED,
    SETUPS_TARGET_SPLIT,
)
from stock_read import rounds

EPS = 1e-9
ROUND = "round"           # a first target that took the half / whole dollar (``round_or_fixed``)


@dataclass(frozen=True)
class TargetSpec:
    """One strategy's choice from the menu: a kind for each half, the fixed amount, the first half's share,
    and the stop."""

    first: str = SETUPS_TARGET1_DEFAULT
    second: str = SETUPS_TARGET2_DEFAULT
    fixed: float = SETUPS_TARGET_FIXED_DOLLARS
    split: float = SETUPS_TARGET_SPLIT
    stop: str = SETUPS_STOP_PATTERN

    def rule(self) -> dict[str, Any]:
        return {"first": self.first, "second": self.second, "fixed": round(self.fixed, 4),
                "split": round(self.split, 4), "stop": self.stop}


DEFAULT = TargetSpec()


def spec_of(values: dict[str, Any]) -> TargetSpec:
    """A template's menu choice (``setup_templates/params_targets.py``: values as the operator types them, the
    split in percent); a key a template saved before it existed reads the default."""
    d = DEFAULT

    def num(key: str, default: float, scale: float = 1.0) -> float:
        return float(values[key]) * scale if values.get(key) is not None else default

    return TargetSpec(first=str(values.get("target1_kind") or d.first), second=str(values.get("target2_kind") or d.second),
                      fixed=num("target_fixed", d.fixed), split=num("target_split_pct", d.split, 0.01),
                      stop=str(values.get("stop_kind") or d.stop))


@dataclass(frozen=True)
class Leg:
    """One half's target: what it came from (``kind``), its price and a few words."""

    kind: str
    price: float
    why: str

    def wire(self) -> dict[str, Any]:
        return {"kind": self.kind, "price": round(self.price, 4), "why": self.why}


@dataclass(frozen=True)
class Targets:
    first: Leg
    second: Leg | None
    split: float
    hod: float | None = None
    pullback_high: float | None = None
    stop: dict[str, Any] | None = None
    rule: dict[str, Any] | None = None

    @property
    def target1(self) -> float:
        return round(self.first.price, 4)

    @property
    def target2(self) -> float | None:
        return round(self.second.price, 4) if self.second is not None else None

    @property
    def fraction(self) -> float:
        """The share of the position that sells at target 1."""
        return round(self.split, 4) if self.second is not None else 1.0

    def wire(self) -> dict[str, Any]:
        return {
            "target1": self.target1, "target2": self.target2, "target1_fraction": self.fraction,
            "targets": {"first": self.first.wire(), "second": self.second.wire() if self.second else None,
                        "hod": _r(self.hod), "pullback_high": _r(self.pullback_high), "stop": self.stop,
                        "rule": self.rule},
        }


def _r(x: float | None) -> float | None:
    return None if x is None else round(float(x), 4)


def px(p: float) -> str:
    return f"{p:.2f}" if p >= 1 else f"{p:.4f}"


def cents(x: float) -> str:
    """An amount in a few characters: "20c" under a dollar, "$1.20" from one."""
    x = abs(x)
    return f"{round(x * 100):d}c" if x < 1 - EPS else f"${x:.2f}"


def zones_of(levels: Iterable[Any] | None) -> list[tuple[float, float, str]]:
    """``(lo, hi, tag)`` for each zone of a map (``level_map`` zones, ``{lo, hi, tag}``), or a bare price."""
    out: list[tuple[float, float, str]] = []
    for z in levels or []:
        if isinstance(z, dict):
            lo, hi = z.get("lo", z.get("price")), z.get("hi", z.get("price"))
            if lo is None or hi is None:
                continue
            out.append((float(lo), float(hi), str(z.get("tag") or z.get("label") or px(float(lo)))))
        else:
            out.append((float(z), float(z), px(float(z))))
    return out


class _Side:
    """A long reads up from the entry; a short is the same rules on the sign ``s``."""

    def __init__(self, short: bool):
        self.s = -1.0 if short else 1.0
        self.short = short

    def past(self, a: float, b: float, by: float = 0.0) -> bool:
        """``a`` at least ``by`` past ``b`` the trade's way."""
        return self.s * (a - b) >= by - EPS

    def under(self, level: float) -> float:
        """1c on this side of a level: under it for a long, over it for a short."""
        return round(level - self.s * SETUPS_TARGET_LEVEL_CENT, 4)

    def plus(self, base: float, amount: float) -> float:
        return round(base + self.s * amount, 4)


def _fixed(side: _Side, entry: float, amount: float) -> Leg:
    return Leg(SETUPS_TARGET_FIXED, side.plus(entry, amount), f"{'-' if side.short else '+'}{cents(amount)}")


def _round_leg(side: _Side, entry: float, base: float, gap: float) -> Leg | None:
    """1c under the first half / whole dollar past ``base`` (the stock's own round scale) that leaves
    ``gap``: a round too near is skipped for the next one."""
    rnd = rounds.of(entry)
    if rnd is None:
        return None
    step = rnd.below if side.short else rnd.above
    r = step(base)
    for _ in range(2):
        t = side.under(r)
        if side.past(t, base, gap):
            name = "" if rnd.half_and_whole else f" ({rnd.name(r)})"
            return Leg(ROUND, t, f"1c {'over' if side.short else 'under'} ${r:.2f}{name}")
        r = step(r)
    return None


def _level_leg(side: _Side, base: float, gap: float, levels: list[tuple[float, float, str]]) -> Leg | None:
    """1c under the first zone of today's map past ``base`` that leaves ``gap`` (a zone the price is in, or
    one too near, does not count)."""
    if side.short:
        ahead = sorted(((hi, tag) for lo, hi, tag in levels if hi < base - EPS), key=lambda x: -x[0])
    else:
        ahead = sorted(((lo, tag) for lo, hi, tag in levels if lo > base + EPS), key=lambda x: x[0])
    for edge, tag in ahead:
        t = side.under(edge)
        if side.past(t, base, gap):
            return Leg(SETUPS_TARGET_NEXT_LEVEL, t, f"1c {'over' if side.short else 'under'} {tag}")
    return None


def _hod_leg(side: _Side, base: float, gap: float, hod: float | None) -> Leg | None:
    if hod is None or hod <= 0:
        return None
    t = side.under(hod)
    if not side.past(t, base, gap):
        return None
    return Leg(SETUPS_TARGET_HOD, t, f"1c {'over LOD' if side.short else 'under HOD'} {px(hod)}")


def _pullback_leg(side: _Side, base: float, gap: float, high: float | None) -> Leg | None:
    if high is None or high <= 0 or not side.past(high, base, gap):
        return None
    return Leg(SETUPS_TARGET_PULLBACK_HIGH, round(high, 4),
               f"the {'bounce low' if side.short else 'pullback high'} {px(high)}")


def _kind(kind: str, side: _Side, entry: float, base: float, gap: float, *, fixed: float,
          levels: list[tuple[float, float, str]], hod: float | None, pullback_high: float | None) -> Leg | None:
    """The price a kind gives at least ``gap`` past ``base`` (the entry for target 1, target 1 for target 2)."""
    if kind == SETUPS_TARGET_FIXED:
        leg = _fixed(side, entry, fixed)
        return leg if side.past(leg.price, base, gap) else None
    if kind == SETUPS_TARGET_NEXT_LEVEL:
        return _level_leg(side, base, gap, levels)
    if kind == SETUPS_TARGET_HOD:
        return _hod_leg(side, base, gap, hod)
    if kind == SETUPS_TARGET_PULLBACK_HIGH:
        return _pullback_leg(side, base, gap, pullback_high)
    if kind == SETUPS_TARGET_ROUND_OR_FIXED:
        fixed_leg = _fixed(side, entry, fixed)
        rnd = _round_leg(side, entry, base, gap)
        return rnd if rnd is not None and side.s * (rnd.price - fixed_leg.price) < -EPS else fixed_leg
    if kind == SETUPS_TARGET_HOD_OR_LEVEL:
        return _hod_leg(side, base, gap, hod) or _level_leg(side, base, gap, levels)
    return None


def plan(spec: TargetSpec | None, *, side: str, entry: float, levels: Iterable[Any] | None = None,
         hod: float | None = None, pullback_high: float | None = None,
         stop: dict[str, Any] | None = None) -> Targets:
    """Both halves' targets for a trade entering at ``entry``, from what is known now: today's map
    (``levels``: zones or prices), the high of day (a short: the low of day) and the pullback's high (a
    short: the bounce's low)."""
    spec = spec or DEFAULT
    sd = _Side(side == "short")
    zs = zones_of(levels)
    kw = {"fixed": float(spec.fixed), "levels": zs, "hod": hod, "pullback_high": pullback_high}
    first = _kind(spec.first, sd, entry, entry, SETUPS_TARGET_MIN_GAIN, **kw)
    if first is None:
        fb = _fixed(sd, entry, float(spec.fixed))
        what = {SETUPS_TARGET_NEXT_LEVEL: "no level of today's map", SETUPS_TARGET_HOD: "the high of day is not",
                SETUPS_TARGET_PULLBACK_HIGH: "no pullback high"}.get(spec.first, "nothing")
        if sd.short:
            what = what.replace("high of day", "low of day").replace("pullback high", "bounce low")
        where = "under" if sd.short else "over"
        first = Leg(SETUPS_TARGET_FIXED, fb.price, f"{fb.why} ({what} {cents(SETUPS_TARGET_MIN_GAIN)}+ {where} the entry)")
    second = None
    if spec.second != SETUPS_TARGET_NONE:
        second = _kind(spec.second, sd, entry, first.price, SETUPS_TARGET2_MIN_GAP, **kw)
    return Targets(first=first, second=second, split=float(spec.split), hod=hod, pullback_high=pullback_high,
                   stop=stop, rule=spec.rule())


def stop_for(spec: TargetSpec | None, *, side: str, entry: float, pattern_stop: float, cap: float | None,
             min_stop: float | None = None, slippage: float = 0.0) -> tuple[float, dict[str, Any]]:
    """``(stop, why)``: the pattern's stop, or with ``spec.stop == "round"`` ``SETUPS_STOP_ROUND_CENTS``
    under the nearest half / whole dollar under the entry (over it for a short) when that risk -- with
    ``slippage`` -- is inside ``cap`` and at least ``min_stop``."""
    spec = spec or DEFAULT
    short = side == "short"
    pattern = {"kind": SETUPS_STOP_PATTERN, "why": "the pattern's stop"}
    if spec.stop != SETUPS_STOP_ROUND:
        return round(pattern_stop, 4), pattern
    rnd = rounds.of(entry)
    if rnd is None:
        return round(pattern_stop, 4), pattern | {"why": "the pattern's stop (no round scale without a price)"}
    r = rnd.above(entry) if short else rnd.below(entry)
    stop = round(r + SETUPS_STOP_ROUND_CENTS if short else r - SETUPS_STOP_ROUND_CENTS, 4)
    risk = (stop - entry) if short else (entry - stop)
    word = "over" if short else "under"
    if cap is not None and risk + slippage > cap + EPS:
        return round(pattern_stop, 4), pattern | {
            "why": f"the pattern's stop: {cents(SETUPS_STOP_ROUND_CENTS)} {word} ${r:.2f} would risk {risk:.2f}, "
                   f"over the {cap:.2f} cap"}
    if min_stop is not None and risk + slippage < min_stop - EPS:
        return round(pattern_stop, 4), pattern | {
            "why": f"the pattern's stop: {cents(SETUPS_STOP_ROUND_CENTS)} {word} ${r:.2f} would risk {risk:.2f}, "
                   f"under the {min_stop:.2f} floor"}
    if stop <= 0:
        return round(pattern_stop, 4), pattern
    return stop, {"kind": SETUPS_STOP_ROUND, "why": f"{cents(SETUPS_STOP_ROUND_CENTS)} {word} ${r:.2f}",
                  "round": r}


_MAP_CACHE: dict[tuple, list[dict[str, Any]]] = {}
_MAP_CACHE_MAX = 512


def day_map(series: Any, price: float | None) -> list[dict[str, Any]]:
    """Today's map from a lane's own candles, read as the stock read's ``level_map`` reads it: the high and low
    of day, the premarket high, the 09:30 open, the tops and bottoms tested twice or more, the session VWAP
    and the round numbers near ``price``, merged into zones. Yesterday's levels are not the scanner's to know.
    The candles' levels are kept per candle set (every lane of a symbol reads the same minutes)."""
    from constants_stock_read import STOCK_READ_LEVEL_MERGE_PCT
    from stock_read import level_map

    n = len(series.t)
    members: list[dict[str, Any]] = []
    if n:
        key = (n, series.t[0], series.t[-1], series.h[-1], series.lo[-1], series.c[-1], series.v[-1],
               series.hod[-1], series.lod[-1])
        members = _MAP_CACHE.get(key)  # type: ignore[assignment]
        if members is None:
            bars = [{"t": series.t[i], "o": series.o[i], "h": series.h[i], "l": series.lo[i], "c": series.c[i],
                     "v": series.v[i]} for i in range(n)]
            members = level_map.candle_members(bars)
            vw = series.vw[-1] if series.vw else None
            if vw is not None:
                members.append(level_map.member("vwap", vw, note="the session VWAP"))
            if len(_MAP_CACHE) >= _MAP_CACHE_MAX:
                _MAP_CACHE.clear()
            _MAP_CACHE[key] = members
    every = list(members) + level_map.round_members(price)
    if not every:
        return []
    return level_map.zones(every, price=price, home="intraday", merge_pct=STOCK_READ_LEVEL_MERGE_PCT)


def words(kind: str, *, second: bool = False, fixed: float = SETUPS_TARGET_FIXED_DOLLARS) -> str:
    """A kind in a few words, for a plan's rule line and the Bots page."""
    return {
        SETUPS_TARGET_FIXED: f"{cents(fixed)} past the entry",
        SETUPS_TARGET_NEXT_LEVEL: "1c before the next level of today's map" + (" past target 1" if second else ""),
        SETUPS_TARGET_PULLBACK_HIGH: "the pullback's high",
        SETUPS_TARGET_HOD: "1c before the high of day",
        SETUPS_TARGET_ROUND_OR_FIXED: f"{cents(fixed)}, or 1c before a half / whole dollar when that is closer",
        SETUPS_TARGET_HOD_OR_LEVEL: "1c before the high of day, else 1c before the next level past target 1",
        SETUPS_TARGET_NONE: "none: everything sells at target 1",
    }.get(kind, kind)
