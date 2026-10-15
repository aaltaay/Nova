"""The ABCD (operator ask 2026-10-15) as a live state machine on one-minute candles. WATCH ONLY.

The shape is ``abcd_shape.py``'s, read after every completed candle:

  leg        a swing high that is the high of day, waiting for A (the pullback's low) or, A in, for B (a push that
             fails to clear the high) -- or B came too weak to count yet
  pullback   B and a higher low C so far, and one rule holds it back: MACD, the window, the risk (``forming`` keeps
             the levels it would arm with)
  armed      B and C: the trigger is B's high, the entry ``entry_offset`` over it, the stop ``stop_offset`` under C so
             far -- re-armed while C goes lower
  near       price within the near band of B
  triggered  a live price over B (the first pullback's trigger, ADR 022): the bar's open when it gapped over, and no
             trade when that gap pushes the risk over the cap
  failed     a low undercut A (stair-stepping down), or ``max_minutes`` from A passed without the break -- with B
             in or still awaited; the next ABCD needs a new high

Targets are the menu's (``targets.py``): by default the first half 1c under the high of day -- the material's first
target, a retest of the high -- and the second the next level past it. At most ``max_per_symbol_day`` ABCDs trigger
on one symbol a day; after one, the next needs a new high.

Watch only (``constants_bot.BOT_WATCH_ONLY_SETUPS``): its lane never proposes it or tells the bot, and
``setup_scanner.trade_verdict`` reads NOT A TRADE on it. Pure: no I/O, no clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from constants_setups import (
    SETUP_KIND_ABCD,
    SETUP_KIND_SECOND_ABCD,
    SETUP_STATE_ARMED,
    SETUP_STATE_FAILED,
    SETUP_STATE_LEG,
    SETUP_STATE_NEAR,
    SETUP_STATE_PULLBACK,
    SETUP_STATE_TRIGGERED,
    SETUP_STATE_WATCHING,
    SETUPS_ABCD_B_OVER_PCT,
    SETUPS_ABCD_BOUNCE,
    SETUPS_ABCD_C_UNDER_PCT,
    SETUPS_ABCD_ENTRY_CUTOFF_ET,
    SETUPS_ABCD_MAX_MINUTES,
    SETUPS_ABCD_MAX_PER_SYMBOL_DAY,
    SETUPS_ABCD_STOP_CAP_DOLLARS,
    SETUPS_ABCD_STOP_OFFSET_DOLLARS,
    SETUPS_ABCD_SWING_PCT,
    SETUPS_ABCD_TOL_DOLLARS,
    SETUPS_BAR_SEC,
    SETUPS_EMA_PERIOD,
    SETUPS_ENTRY_OFFSET_DOLLARS,
    SETUPS_MACD_FAST,
    SETUPS_MACD_POSITIVE,
    SETUPS_MACD_SIGNAL,
    SETUPS_MACD_SLOW,
    SETUPS_MIN_STOP_DOLLARS,
    SETUPS_NEAR_DOLLARS,
    SETUPS_NEAR_PCT,
    SETUPS_RISK_SLIPPAGE_DOLLARS,
    SETUPS_SESSION_START_ET,
    SETUPS_TARGET_HOD,
)
from setup_scanner import abcd_shape
from setup_scanner.abcd_shape import Shape
from setup_scanner.bars import Bar
from setup_scanner.detector import EPS, TriggerDetector, forming_levels, risk_blocked, window_blocked
from setup_scanner.targets import TargetSpec

# The menu's choice an ABCD starts from: the first half at the high of day, the second the default past it.
ABCD_TARGETS = TargetSpec(first=SETUPS_TARGET_HOD)


@dataclass(frozen=True)
class AbcdParams:
    swing_pct: float = SETUPS_ABCD_SWING_PCT
    b_over_pct: float = SETUPS_ABCD_B_OVER_PCT
    c_under_pct: float = SETUPS_ABCD_C_UNDER_PCT
    tol_dollars: float = SETUPS_ABCD_TOL_DOLLARS
    bounce: float = SETUPS_ABCD_BOUNCE
    max_minutes: int = SETUPS_ABCD_MAX_MINUTES
    stop_offset: float = SETUPS_ABCD_STOP_OFFSET_DOLLARS
    ema_period: int = SETUPS_EMA_PERIOD
    macd_positive: bool = SETUPS_MACD_POSITIVE
    macd_fast: int = SETUPS_MACD_FAST
    macd_slow: int = SETUPS_MACD_SLOW
    macd_signal: int = SETUPS_MACD_SIGNAL
    stop_cap: float = SETUPS_ABCD_STOP_CAP_DOLLARS
    min_stop: float = SETUPS_MIN_STOP_DOLLARS
    entry_offset: float = SETUPS_ENTRY_OFFSET_DOLLARS
    risk_slippage: float = SETUPS_RISK_SLIPPAGE_DOLLARS
    targets: TargetSpec = ABCD_TARGETS
    near_dollars: float = SETUPS_NEAR_DOLLARS
    near_pct: float = SETUPS_NEAR_PCT
    session_start: str = SETUPS_SESSION_START_ET
    entry_cutoff: str = SETUPS_ABCD_ENTRY_CUTOFF_ET
    max_per_symbol_day: int = SETUPS_ABCD_MAX_PER_SYMBOL_DAY
    bar_sec: int = SETUPS_BAR_SEC


def _min(n: int) -> str:
    return f"{n} minute{'' if n == 1 else 's'}"


@dataclass
class AbcdDetector(TriggerDetector):
    """One symbol's ABCD. ``on_bars`` after each completed candle; ``on_price`` triggers on the break of B."""

    p: AbcdParams = field(default_factory=AbcdParams)
    done_t: float | None = None     # the high whose ABCD triggered or failed: the next one needs a new high

    FIRST_KIND: ClassVar[str] = SETUP_KIND_ABCD
    SECOND_KIND: ClassVar[str | None] = SETUP_KIND_SECOND_ABCD

    def on_bars(self, bars: list[Bar]) -> list[tuple[str, dict]]:
        n = len(bars)
        self.series.update(bars)
        self.forming = None
        if n < 3:
            if self.state == SETUP_STATE_WATCHING:
                self.reason = f"warming up ({n}/3 bars)"
            return []
        if self.nth >= self.p.max_per_symbol_day:
            return []                     # the day's ABCDs on this symbol are used (or were, before a restart)
        s, last = self.series, n - 1
        shape = abcd_shape.read(s.h, s.lo, s.hod, self.p)
        prev = self.armed if self.state in (SETUP_STATE_ARMED, SETUP_STATE_NEAR) else None
        high_t = s.t[shape.high.i] if shape is not None else None
        if self.state == SETUP_STATE_TRIGGERED and (shape is None or high_t == self.done_t):
            return []                     # the trade is on; the next ABCD needs a new high
        if shape is None:
            return self._watch(prev, "no swing high at the high of day yet")
        if high_t == self.done_t:
            return [] if self.state == SETUP_STATE_FAILED else self._watch(prev, "the last ABCD under this high is done")
        self.leg = self._leg(shape)
        if shape.stage == "broken":
            return self._fail(prev, high_t, shape.why or "a low undercut A")
        # The window runs from A, whether B has come yet or not.
        if shape.a is not None and bars[last].t + self.p.bar_sec - s.t[shape.a.i] > self.p.max_minutes * 60 + EPS:
            words = "a break of B" if shape.stage == "formed" else "a B that fails under the high"
            return self._fail(prev, high_t, f"{_min(self.p.max_minutes)} from A without {words}: too slow")
        if shape.stage != "formed":
            return self._wait(prev, shape)
        return self._arm(bars, last, shape, prev)

    # -- the shape's leg ------------------------------------------------------
    def _leg(self, shape: Shape) -> dict[str, Any]:
        """The high, and A when it is in, as every setup's leg (``t`` the key: A's candle once A is in), with the
        shape's points for the chart."""
        s = self.series
        a = shape.a
        low = a.price if a is not None else min(s.lo[shape.high.i:])
        return {"t": s.t[a.i] if a is not None else s.t[shape.high.i], "high": round(shape.high.price, 4),
                "low": round(low, 4), "pct": round((shape.high.price - low) / shape.high.price, 4),
                "bars": len(s.t) - 1 - shape.high.i, "abcd": abcd_shape.points(shape, s.t)}

    def _watch(self, prev: dict | None, why: str) -> list[tuple[str, dict]]:
        self.leg = None
        self._set(SETUP_STATE_WATCHING, why)
        return [("disarmed", self._key_view(prev, reason=why))] if prev is not None else []

    def _wait(self, prev: dict | None, shape: Shape) -> list[tuple[str, dict]]:
        hi = shape.high.price
        if shape.stage == "a":
            why = f"high {hi:.2f}: pulling back -- wait for A, the pullback's low"
        elif shape.why:
            why = f"high {hi:.2f}, A {shape.a.price:.2f}: {shape.why}"
        else:
            why = f"high {hi:.2f}, A {shape.a.price:.2f} -- wait for B, a push that fails under {shape.b_max:.2f}"
        events: list[tuple[str, dict]] = []
        if prev is not None:
            events.append(("disarmed", self._key_view(prev, reason="B is no longer the newest high")))
        was = self.state
        self._set(SETUP_STATE_LEG, why)
        if was != SETUP_STATE_LEG:
            events.append(("leg", self.view()))
        return events

    def _fail(self, prev: dict | None, high_t: float, why: str) -> list[tuple[str, dict]]:
        self.armed, self.done_t = None, high_t
        self._set(SETUP_STATE_FAILED, why)
        return [("failed", self._key_view(prev, reason=why))] if prev is not None else []

    def _arm(self, bars: list[Bar], last: int, shape: Shape, prev: dict | None) -> list[tuple[str, dict]]:
        s, p = self.series, self.p
        a, b, c = shape.a, shape.b, shape.c
        trigger = round(b.price, 4)
        entry = round(trigger + p.entry_offset, 4)
        stop, stop_why = self.stop_at(entry, round(c.price - p.stop_offset, 4))
        risk = round(entry - stop, 4)
        aim = self.aim(entry, pullback_high=shape.high.price, stop=stop_why)
        head = f"A {a.price:.2f}, B {b.price:.2f} under the {shape.high.price:.2f} high, C {c.price:.2f}"
        blocked = window_blocked(p, bars[last].t + p.bar_sec)
        if blocked is None and p.macd_positive and s.hist[last] <= 0:
            blocked = "MACD negative -- not on the front side"
        if blocked is None:
            blocked = risk_blocked(p, risk, entry=entry)
        events: list[tuple[str, dict]] = []
        if blocked:
            self.armed = None
            self.forming = forming_levels(trigger, entry, stop, aim, bars=len(s.t) - 1 - a.i, blocked=blocked)
            self._set(SETUP_STATE_PULLBACK, f"{head}, but {blocked}")
            if prev is not None:
                events.append(("disarmed", self._key_view(prev, reason=blocked)))
            return events
        key = s.t[a.i]
        if prev is not None and prev["leg_t"] != key:
            events.append(("disarmed", self._key_view(prev, reason="a newer ABCD took over")))
            prev = None
        self.armed = {
            "leg_t": key, "trigger": trigger, "entry": entry, "stop": round(stop, 4), "risk": risk, **aim,
            "pullback_bars": len(s.t) - 1 - a.i, "leg_high": round(shape.high.price, 4), "leg_low": round(a.price, 4),
            "leg_pct": self.leg["pct"], "armed_bar_t": bars[last].t,
            "armed_at": (prev or {}).get("armed_at") or bars[last].t + p.bar_sec, "kind": self.kind_now(),
            "detail": {**self.leg["abcd"], "stop_offset": p.stop_offset, "max_minutes": p.max_minutes,
                       "deadline": key + p.max_minutes * 60},
        }
        self._set(SETUP_STATE_ARMED, f"{head} -- trigger {trigger:.2f}, stop {stop:.2f}, risk {risk:.2f}")
        return events + self.arm_events(prev)

    # -- live price -------------------------------------------------------
    def on_price(self, price: float, ts: float, *, bar_open: float | None = None) -> list[tuple[str, dict]]:
        deadline = ((self.armed or {}).get("detail") or {}).get("deadline")
        if (deadline is not None and self.state in (SETUP_STATE_ARMED, SETUP_STATE_NEAR)
                and ts > float(deadline) + EPS and price > float(self.armed["trigger"]) + EPS):
            self.last_price = price
            high = (self.armed.get("detail") or {}).get("high")
            return self._fail(self.armed, float(high[0]) if high else 0.0,
                              f"{_min(self.p.max_minutes)} from A without a break of B: too slow")
        events = super().on_price(price, ts, bar_open=bar_open)
        if self.state == SETUP_STATE_TRIGGERED and self.triggered is not None:
            self.done_t = self._high_t()
        return events

    def _high_t(self) -> float | None:
        pt = ((self.triggered or {}).get("detail") or {}).get("high")
        return float(pt[0]) if pt else None
