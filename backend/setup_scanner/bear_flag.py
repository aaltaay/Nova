"""The bear flag: the bull flag mirrored for a short (ADR 049 section 6, pre-registered).

After every completed bar the detector reads the candles at the end of the day so far:

  pole       at least ``pole_min_bars`` consecutive red candles (close under open) ending at the pole bottom;
             their drop, highest high to lowest low over the highest high, at least ``pole_min_pct``; the last
             pole candle's volume at least the first's
  flag       ``min_flag_bars``-``max_flag_bars`` candles right after the pole bottom, each green or a doji
             (close at or over its open) and none with a low under the candle before it (drifting up); the
             flag's high takes back no more than ``max_retrace`` of the pole; the flag's average volume under
             the pole's; every flag close at or under the EMA
  rejected   the day's highest-volume candle so far is green; the pole-bottom candle's lower wick is more
             than ``max_pole_wick`` of its range
  armed      trigger = the last flag candle's low, entry one cent under it, buy stop one cent over the flag's
             highest high, the last flag candle's MACD histogram under zero, the next minute inside the window
             (09:35-15:30), risk inside the band counting one cent of slippage
  near / triggered   every short's (``detector_short.py``)

``leg`` is a pole (wait for the flag); ``pullback`` a flag one rule blocks; ``failed`` a flag that broke a rule.
A volume Nova does not know (a bar with no volume) never fails a volume rule. Every number is a
``BearFlagParams`` field a template sets (ADR 029). Pure: no I/O, no clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from constants_setups import (
    SETUP_STATE_ARMED,
    SETUP_STATE_FAILED,
    SETUP_STATE_LEG,
    SETUP_STATE_NEAR,
    SETUP_STATE_PULLBACK,
    SETUP_STATE_TRIGGERED,
    SETUP_STATE_WATCHING,
    SETUPS_BAR_SEC,
    SETUPS_EMA_PERIOD,
    SETUPS_EMA_TOLERANCE,
    SETUPS_MACD_FAST,
    SETUPS_MACD_SIGNAL,
    SETUPS_MACD_SLOW,
    SETUPS_MIN_STOP_DOLLARS,
    SETUPS_NEAR_DOLLARS,
    SETUPS_NEAR_PCT,
    SETUPS_RISK_SLIPPAGE_DOLLARS,
    SETUPS_STOP_CAP_DOLLARS,
    SETUPS_TARGET_R,
)
from constants_short_setups import (
    SETUP_KIND_BEAR_FLAG,
    SETUP_KIND_SECOND_BEAR_FLAG,
    SHORT_BEAR_FLAG_CUTOFF_ET,
    SHORT_BF_EMA_HOLD,
    SHORT_BF_FLAG_VOLUME_LIGHTER,
    SHORT_BF_MAX_FLAG_BARS,
    SHORT_BF_MAX_POLE_WICK,
    SHORT_BF_MAX_RETRACE,
    SHORT_BF_MIN_FLAG_BARS,
    SHORT_BF_POLE_MIN_BARS,
    SHORT_BF_POLE_MIN_PCT,
    SHORT_BF_POLE_VOLUME_RISING,
    SHORT_BF_REJECT_GREEN_VOLUME_HIGH,
    SHORT_ENTRY_OFFSET_DOLLARS,
    SHORT_MACD_NEGATIVE,
    SHORT_MAX_PER_SYMBOL_DAY,
    SHORT_STOP_OFFSET_DOLLARS,
    SHORT_WINDOW_START_ET,
)
from setup_scanner.bars import Bar
from setup_scanner.detector import EPS, window_blocked
from setup_scanner.detector_short import ShortTriggerDetector, short_levels, short_risk_blocked, short_target


@dataclass(frozen=True)
class BearFlagParams:
    pole_min_bars: int = SHORT_BF_POLE_MIN_BARS
    pole_min_pct: float = SHORT_BF_POLE_MIN_PCT
    pole_volume_rising: bool = SHORT_BF_POLE_VOLUME_RISING
    min_flag_bars: int = SHORT_BF_MIN_FLAG_BARS
    max_flag_bars: int = SHORT_BF_MAX_FLAG_BARS
    max_retrace: float = SHORT_BF_MAX_RETRACE
    flag_volume_lighter: bool = SHORT_BF_FLAG_VOLUME_LIGHTER
    ema_hold: bool = SHORT_BF_EMA_HOLD
    reject_green_volume_high: bool = SHORT_BF_REJECT_GREEN_VOLUME_HIGH
    max_pole_wick: float | None = SHORT_BF_MAX_POLE_WICK
    ema_period: int = SETUPS_EMA_PERIOD
    ema_tol: float = SETUPS_EMA_TOLERANCE
    macd_negative: bool = SHORT_MACD_NEGATIVE
    macd_fast: int = SETUPS_MACD_FAST
    macd_slow: int = SETUPS_MACD_SLOW
    macd_signal: int = SETUPS_MACD_SIGNAL
    stop_cap: float = SETUPS_STOP_CAP_DOLLARS
    bar_sec: int = SETUPS_BAR_SEC
    min_stop: float = SETUPS_MIN_STOP_DOLLARS
    entry_offset: float = SHORT_ENTRY_OFFSET_DOLLARS
    stop_offset: float = SHORT_STOP_OFFSET_DOLLARS
    risk_slippage: float = SETUPS_RISK_SLIPPAGE_DOLLARS
    target_r: float = SETUPS_TARGET_R
    near_dollars: float = SETUPS_NEAR_DOLLARS
    near_pct: float = SETUPS_NEAR_PCT
    session_start: str = SHORT_WINDOW_START_ET
    entry_cutoff: str = SHORT_BEAR_FLAG_CUTOFF_ET
    max_per_symbol_day: int = SHORT_MAX_PER_SYMBOL_DAY


def _red(o: float, c: float) -> bool:
    return c < o - EPS


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _pct(x: float) -> str:
    return f"{100 * x:.1f}".rstrip("0").rstrip(".")


@dataclass
class BearFlagDetector(ShortTriggerDetector):
    p: BearFlagParams = field(default_factory=BearFlagParams)

    FIRST_KIND: ClassVar[str] = SETUP_KIND_BEAR_FLAG
    SECOND_KIND: ClassVar[str | None] = SETUP_KIND_SECOND_BEAR_FLAG

    def on_bars(self, bars: list[Bar]) -> list[tuple[str, dict]]:
        n = len(bars)
        self.series.update(bars)
        self.forming = None
        need = self.p.pole_min_bars + self.p.min_flag_bars
        if n < need:
            if self.state == SETUP_STATE_WATCHING:
                self.reason = f"warming up ({n}/{need} bars)"
            return []
        if self.nth >= self.p.max_per_symbol_day:
            return []
        last = n - 1
        prev = self.armed if self.state in (SETUP_STATE_ARMED, SETUP_STATE_NEAR) else None
        run = self._green_run(last)
        pole = self._pole(bars, last - run) if last - run >= 0 else None

        if self.state == SETUP_STATE_TRIGGERED:
            fresh = self._pole(bars, last)
            new = (pole is not None and pole["t"] != self.triggered.get("leg_t")) or (
                fresh is not None and fresh["t"] != self.triggered.get("leg_t"))
            if not new:
                return []                 # the trade is on; a new setup needs a new pole

        events: list[tuple[str, dict]] = []
        if run == 0:
            fresh = self._pole(bars, last)
            if fresh is not None and self._pole_fault(fresh) is None:
                self.leg, self.armed = fresh, None
                was = self.state
                self._set(SETUP_STATE_LEG, f"pole: {fresh['bars']} red candles, -{_pct(fresh['pct'])}% to "
                                           f"{fresh['low']:.2f} -- wait for the flag")
                if prev is not None:
                    events.append(("disarmed", self._key_view(prev, reason="a red candle closed without a new low")))
                if was != SETUP_STATE_LEG:
                    events.append(("leg", self.view()))
                return events
            return self._fail_or_watch(prev, None, "no pole" if prev is None
                                       else "a red candle closed without making a new low -- the flag is over")
        if pole is None:
            return self._fail_or_watch(prev, None, "no pole before the green candles")
        fault = self._pole_fault(pole)
        if fault:
            return self._fail_or_watch(prev, pole, fault, failed=True)
        if run < self.p.min_flag_bars:
            self.leg, self.armed = pole, None
            self.forming = self._partial_flag(bars, last, pole, run)
            self._set(SETUP_STATE_LEG, f"pole -{_pct(pole['pct'])}% to {pole['low']:.2f}; {run} green candle so far "
                                       f"-- a flag needs {self.p.min_flag_bars}")
            if prev is not None:
                events.append(("disarmed", self._key_view(prev, reason="the flag is not formed")))
            return events
        if run > self.p.max_flag_bars:
            return self._fail_or_watch(prev, pole, f"the flag ran past {self.p.max_flag_bars} candles -- too much "
                                                   "buying", failed=True)
        fault = self._flag_fault(pole, last - run + 1, last)
        if fault:
            return self._fail_or_watch(prev, pole, fault, failed=True)
        return self._arm(bars, last, pole, run, prev)

    def _levels(self, last: int, run: int) -> tuple[float, float, float, float, float]:
        s, p = self.series, self.p
        flag_high = max(s.h[last - run + 1:last + 1])
        trig = s.lo[last]
        entry = round(trig - p.entry_offset, 4)
        stop = round(flag_high + p.stop_offset, 4)
        risk = round(stop - entry, 4)
        return trig, entry, stop, risk, short_target(entry, risk, p.target_r)

    def _arm(self, bars: list[Bar], last: int, pole: dict, run: int, prev: dict | None) -> list[tuple[str, dict]]:
        s, p = self.series, self.p
        events: list[tuple[str, dict]] = []
        self.leg = pole
        first = last - run + 1
        trig, entry, stop, risk, target = self._levels(last, run)
        blocked = self._blocked(bars, last, risk, entry)
        if blocked:
            self.armed = None
            self.forming = short_levels(trig, entry, stop, target, bars=run, blocked=blocked)
            self._set(SETUP_STATE_PULLBACK, f"flag of {run} candles, but {blocked}")
            if prev is not None:
                events.append(("disarmed", self._key_view(prev, reason=blocked)))
            return events
        if prev is not None and prev["leg_t"] != pole["t"]:
            events.append(("disarmed", self._key_view(prev, reason="a newer pole took over")))
            prev = None
        self.armed = {
            "leg_t": pole["t"], "trigger": round(trig, 4), "entry": entry, "stop": stop, "risk": risk,
            "target1": target, "pullback_bars": run, "leg_high": pole["high"], "leg_low": pole["low"],
            "leg_pct": pole["pct"], "armed_bar_t": bars[last].t,
            "armed_at": (prev or {}).get("armed_at") or bars[last].t + p.bar_sec, "kind": self.kind_now(),
            "detail": {"pole_bars": pole["bars"], "flag_bars": run, "pole_volume": pole["volume"],
                       "flag_volume": round(_avg(s.v[first:last + 1]), 1), "volume_known": pole["volume"] > 0},
        }
        self._set(SETUP_STATE_ARMED, f"flag of {run} over the {pole['low']:.2f} pole: short under {trig:.2f}, "
                                     f"buy stop {stop:.2f}, risk {risk:.2f}")
        return events + self.arm_events(prev)

    def _blocked(self, bars: list[Bar], last: int, risk: float, entry: float) -> str | None:
        p = self.p
        why = window_blocked(p, bars[last].t + p.bar_sec)
        if why is None and p.macd_negative and self.series.hist[last] >= 0:
            why = "MACD positive -- not on the back side"
        return why if why is not None else short_risk_blocked(p, risk, entry=entry)

    def _partial_flag(self, bars: list[Bar], last: int, pole: dict, run: int) -> dict[str, Any]:
        """A flag shorter than the rule asks: the levels it would arm with now (ADR 036)."""
        trig, entry, stop, risk, target = self._levels(last, run)
        need = self.p.min_flag_bars - run
        blocked = self._flag_fault(pole, last - run + 1, last) or self._blocked(bars, last, risk, entry)
        return short_levels(trig, entry, stop, target, bars=run, blocked=blocked,
                            waiting=f"{need} more green or doji candle{'' if need == 1 else 's'}")

    # -- the pattern ----------------------------------------------------------
    def _green_run(self, last: int) -> int:
        """Green or doji candles at the end of the day so far."""
        s = self.series
        i = last
        while i >= 0 and not _red(s.o[i], s.c[i]):
            i -= 1
        return last - i

    def _pole(self, bars: list[Bar], bottom: int) -> dict[str, Any] | None:
        """The pole ending at ``bottom``, or None when the candles there are not one."""
        s, p = self.series, self.p
        if bottom < 0 or not _red(s.o[bottom], s.c[bottom]):
            return None
        start = bottom
        while start - 1 >= 0 and _red(s.o[start - 1], s.c[start - 1]):
            start -= 1
        count = bottom - start + 1
        if count < p.pole_min_bars:
            return None
        high, low = max(s.h[start:bottom + 1]), min(s.lo[start:bottom + 1])
        if high <= 0 or low <= 0:
            return None
        drop = (high - low) / high
        if drop < p.pole_min_pct - EPS:
            return None
        return {"t": bars[bottom].t, "high": high, "low": low, "pct": round(drop, 4), "bars": count,
                "start": start, "bottom": bottom, "volume": round(_avg(s.v[start:bottom + 1]), 1)}

    def _pole_fault(self, pole: dict) -> str | None:
        s, p = self.series, self.p
        first, bottom = pole["start"], pole["bottom"]
        if p.pole_volume_rising and pole["bars"] >= 2 and s.v[first] > 0 and s.v[bottom] < s.v[first]:
            return (f"the pole's volume fell ({int(s.v[bottom]):,} on its last candle, {int(s.v[first]):,} on its "
                    "first) -- the drop is tiring")
        if p.max_pole_wick is not None:
            rng = s.h[bottom] - s.lo[bottom]
            wick = min(s.o[bottom], s.c[bottom]) - s.lo[bottom]
            if rng > EPS and wick / rng > p.max_pole_wick + EPS:
                return f"the pole's bottom candle left a {_pct(wick / rng)}% lower tail"
        return None

    def _flag_fault(self, pole: dict, first: int, last: int) -> str | None:
        s, p = self.series, self.p
        for n, i in enumerate(range(first, last + 1), start=1):
            if s.lo[i] < s.lo[i - 1] - EPS:
                return f"flag candle {n} made a lower low than the candle before it"
        flag_high = max(s.h[first:last + 1])
        span = max(pole["high"] - pole["low"], EPS)
        taken = (flag_high - pole["low"]) / span
        if taken > p.max_retrace + EPS:
            return f"the flag took back {_pct(taken)}% of the pole -- more than {_pct(p.max_retrace)}%"
        if p.flag_volume_lighter and pole["volume"] > 0:
            flag_volume = _avg(s.v[first:last + 1])
            if flag_volume >= pole["volume"] - EPS:
                return (f"the flag's volume ({int(flag_volume):,} a candle) is not lighter than the pole's "
                        f"({int(pole['volume']):,})")
        if p.ema_hold and any(s.c[i] > s.e[i] * (1 + p.ema_tol) + EPS for i in range(first, last + 1)):
            return "a flag candle closed over the 9 EMA"
        if p.reject_green_volume_high:
            i = s.vmax_i[last]                # the first candle with the day's biggest volume
            if s.v[i] > 0 and s.c[i] > s.o[i] + EPS:
                return "the day's highest-volume candle is green -- buyers, not sellers, own the day"
        return None

    def _fail_or_watch(self, prev: dict | None, pole: dict | None, why: str, *, failed: bool = False
                       ) -> list[tuple[str, dict]]:
        events: list[tuple[str, dict]] = []
        self.armed = None
        if failed and pole is not None:
            self.leg = pole
            if self.state != SETUP_STATE_FAILED or self.reason != why:
                self._set(SETUP_STATE_FAILED, why)
                if prev is not None:
                    events.append(("failed", self._key_view(prev, reason=why)))
            return events
        self.leg = None
        self._set(SETUP_STATE_WATCHING, why)
        if prev is not None:
            events.append(("disarmed", self._key_view(prev, reason=why)))
        return events
