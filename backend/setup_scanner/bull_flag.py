"""The bull flag as a live state machine on one-minute bars (ADR 031).

Pre-registered in ADR 031 from the operator's material, never tested on bars:
its read-out is its first test. After every completed bar the detector reads
the candles at the end of the day so far:

  pole       at least ``pole_min_bars`` consecutive green candles (close over
             open) ending at the pole top; their rise, lowest low to highest
             high, at least ``pole_min_pct`` or ``pole_min_dollars``; the last
             pole candle's volume at least the first's
  flag       ``min_flag_bars``-``max_flag_bars`` candles right after the pole top,
             each red or a doji (close at or under its open) and none with a
             high over the candle before it; the flag low gives back no more
             than ``max_retrace`` of the pole; the flag's average volume under
             the pole's; every flag close at or above the EMA
  rejected   the day's highest-volume candle so far is red; the pole-top
             candle's upper wick is more than ``max_pole_wick`` of its range
  armed      trigger = the last flag candle's high (the material's "first
             candle to make a new high" trades through it); entry one cent
             over; stop = the flag low; the last flag candle's MACD histogram
             above zero; the next minute inside the entry window; risk inside
             the band counting one cent of slippage
  near / triggered   every setup's (``setup_scanner/detector.py``)

The board's other states are for the eye: ``leg`` (a pole -- wait for the
flag), ``pullback`` (a flag, but one rule blocks it), ``failed`` (the flag broke
a rule), ``watching``. A volume Nova does not know (a bar with no volume) never
fails a volume rule: the check is skipped and ``detail.volume_known`` says so.

Every number is a ``BullFlagParams`` field a template sets (ADR 029). At most
``max_per_symbol_day`` setups trigger on one symbol a day -- the first and the
second flag. Pure: no I/O, no clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from constants_setups import (
    SETUP_KIND_BULL_FLAG,
    SETUP_KIND_SECOND_BULL_FLAG,
    SETUP_STATE_ARMED,
    SETUP_STATE_FAILED,
    SETUP_STATE_LEG,
    SETUP_STATE_NEAR,
    SETUP_STATE_PULLBACK,
    SETUP_STATE_TRIGGERED,
    SETUP_STATE_WATCHING,
    SETUPS_BF_EMA_HOLD,
    SETUPS_BF_EMA_TOUCH_PCT,
    SETUPS_BF_FLAG_VOLUME_LIGHTER,
    SETUPS_BF_MAX_FLAG_BARS,
    SETUPS_BF_MAX_PER_SYMBOL_DAY,
    SETUPS_BF_MAX_POLE_WICK,
    SETUPS_BF_MAX_RETRACE,
    SETUPS_BF_MIN_FLAG_BARS,
    SETUPS_BF_POLE_MIN_BARS,
    SETUPS_BF_POLE_MIN_DOLLARS,
    SETUPS_BF_POLE_MIN_PCT,
    SETUPS_BF_POLE_VOLUME_RISING,
    SETUPS_BF_REJECT_RED_VOLUME_HIGH,
    SETUPS_BF_REQUIRE_HOD,
    SETUPS_EMA_PERIOD,
    SETUPS_EMA_TOLERANCE,
    SETUPS_ENTRY_CUTOFF_ET,
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
    SETUPS_STOP_CAP_DOLLARS,
    SETUPS_TARGET_FIXED_DOLLARS,
    SETUPS_TARGET_MODE,
    SETUPS_TARGET_R,
)
from setup_scanner.bars import Bar
from setup_scanner.detector import EPS, TriggerDetector, forming_levels, risk_blocked, window_blocked


@dataclass(frozen=True)
class BullFlagParams:
    pole_min_bars: int = SETUPS_BF_POLE_MIN_BARS
    pole_min_pct: float = SETUPS_BF_POLE_MIN_PCT
    pole_min_dollars: float | None = SETUPS_BF_POLE_MIN_DOLLARS
    pole_volume_rising: bool = SETUPS_BF_POLE_VOLUME_RISING
    min_flag_bars: int = SETUPS_BF_MIN_FLAG_BARS
    max_flag_bars: int = SETUPS_BF_MAX_FLAG_BARS
    max_retrace: float = SETUPS_BF_MAX_RETRACE
    flag_volume_lighter: bool = SETUPS_BF_FLAG_VOLUME_LIGHTER
    ema_hold: bool = SETUPS_BF_EMA_HOLD
    ema_touch_pct: float | None = SETUPS_BF_EMA_TOUCH_PCT
    reject_red_volume_high: bool = SETUPS_BF_REJECT_RED_VOLUME_HIGH
    max_pole_wick: float | None = SETUPS_BF_MAX_POLE_WICK
    require_hod: bool = SETUPS_BF_REQUIRE_HOD
    ema_period: int = SETUPS_EMA_PERIOD
    ema_tol: float = SETUPS_EMA_TOLERANCE
    macd_positive: bool = SETUPS_MACD_POSITIVE
    macd_fast: int = SETUPS_MACD_FAST
    macd_slow: int = SETUPS_MACD_SLOW
    macd_signal: int = SETUPS_MACD_SIGNAL
    stop_cap: float = SETUPS_STOP_CAP_DOLLARS
    min_stop: float = SETUPS_MIN_STOP_DOLLARS
    entry_offset: float = SETUPS_ENTRY_OFFSET_DOLLARS
    risk_slippage: float = SETUPS_RISK_SLIPPAGE_DOLLARS
    target_mode: str = SETUPS_TARGET_MODE
    target_r: float = SETUPS_TARGET_R
    target_fixed: float = SETUPS_TARGET_FIXED_DOLLARS
    near_dollars: float = SETUPS_NEAR_DOLLARS
    near_pct: float = SETUPS_NEAR_PCT
    session_start: str = SETUPS_SESSION_START_ET
    entry_cutoff: str = SETUPS_ENTRY_CUTOFF_ET
    max_per_symbol_day: int = SETUPS_BF_MAX_PER_SYMBOL_DAY

    def target1(self, pole_high: float, entry: float, risk: float) -> float:
        """``leg_or_r``: the pole high or R x risk, whichever is higher; ``leg``: the pole
        high (the material's first target) -- R x risk when the pole high is not above the
        entry; ``fixed``: a fixed amount over the entry."""
        if self.target_mode == "fixed":
            return round(entry + self.target_fixed, 4)
        by_r = entry + self.target_r * risk
        if self.target_mode == "leg":
            return round(pole_high if pole_high > entry + EPS else by_r, 4)
        return round(max(pole_high, by_r), 4)


def _green(o: float, c: float) -> bool:
    return c > o + EPS


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _pct(x: float) -> str:
    return f"{100 * x:.1f}".rstrip("0").rstrip(".")


@dataclass
class BullFlagDetector(TriggerDetector):
    p: BullFlagParams = field(default_factory=BullFlagParams)

    FIRST_KIND: ClassVar[str] = SETUP_KIND_BULL_FLAG
    SECOND_KIND: ClassVar[str | None] = SETUP_KIND_SECOND_BULL_FLAG

    # -- bar close ---------------------------------------------------------
    def on_bars(self, bars: list[Bar]) -> list[tuple[str, dict]]:
        n = len(bars)
        self.series.update(bars)
        self.forming = None
        need = self.p.pole_min_bars + self.p.min_flag_bars
        if n < need:
            if self.state == SETUP_STATE_WATCHING:
                self.reason = f"warming up ({n}/{need} bars)"
            return []
        if self.state == SETUP_STATE_TRIGGERED and self.nth >= self.p.max_per_symbol_day:
            return []                     # the first and second flag are used
        last = n - 1
        prev = self.armed if self.state in (SETUP_STATE_ARMED, SETUP_STATE_NEAR) else None
        run = self._red_run(last)
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
                self._set(SETUP_STATE_LEG, f"pole: {fresh['bars']} green candles, +{_pct(fresh['pct'])}% to "
                                           f"{fresh['high']:.2f} -- wait for the flag")
                if prev is not None:
                    events.append(("disarmed", self._key_view(prev, reason="a green candle closed without a new high")))
                if was != SETUP_STATE_LEG:
                    events.append(("leg", self.view()))
                return events
            return self._fail_or_watch(prev, None, "no pole" if prev is None
                                       else "a green candle closed without making a new high -- the flag is over")
        if pole is None:
            return self._fail_or_watch(prev, None, "no pole before the red candles")
        fault = self._pole_fault(pole)
        if fault:
            return self._fail_or_watch(prev, pole, fault, failed=True)
        if run < self.p.min_flag_bars:
            self.leg, self.armed = pole, None
            self.forming = self._partial_flag(bars, last, pole, run)
            self._set(SETUP_STATE_LEG, f"pole +{_pct(pole['pct'])}% to {pole['high']:.2f}; {run} red candle so far -- "
                                       f"a flag needs {self.p.min_flag_bars} (one is a micro pullback)")
            if prev is not None:
                events.append(("disarmed", self._key_view(prev, reason="the flag is not formed")))
            return events
        if run > self.p.max_flag_bars:
            return self._fail_or_watch(prev, pole, f"the flag ran past {self.p.max_flag_bars} candles -- too much selling",
                                       failed=True)
        fault = self._flag_fault(bars, pole, last - run + 1, last)
        if fault:
            return self._fail_or_watch(prev, pole, fault, failed=True)
        return self._arm(bars, last, pole, run, prev)

    def _arm(self, bars: list[Bar], last: int, pole: dict, run: int, prev: dict | None) -> list[tuple[str, dict]]:
        s, p = self.series, self.p
        events: list[tuple[str, dict]] = []
        self.leg = pole
        first = last - run + 1
        flag_low = min(s.lo[first:last + 1])
        trig = s.h[last]
        entry = round(trig + p.entry_offset, 4)
        risk = round(entry - flag_low, 4)
        blocked = self._blocked(bars, last, risk)
        if blocked:
            self.armed = None
            self.forming = forming_levels(trig, entry, flag_low, p.target1(pole["high"], entry, risk), bars=run,
                                          blocked=blocked)
            self._set(SETUP_STATE_PULLBACK, f"flag of {run} candles, but {blocked}")
            if prev is not None:
                events.append(("disarmed", self._key_view(prev, reason=blocked)))
            return events
        if prev is not None and prev["leg_t"] != pole["t"]:
            events.append(("disarmed", self._key_view(prev, reason="a newer pole took over")))
            prev = None
        self.armed = {
            "leg_t": pole["t"], "trigger": round(trig, 4), "entry": entry, "stop": round(flag_low, 4),
            "risk": risk, "target1": p.target1(pole["high"], entry, risk),
            "pullback_bars": run, "leg_high": pole["high"], "leg_low": pole["low"], "leg_pct": pole["pct"],
            "armed_bar_t": bars[last].t, "armed_at": (prev or {}).get("armed_at") or bars[last].t + 60,
            "kind": self.kind_now(),
            "detail": {"pole_bars": pole["bars"], "flag_bars": run, "pole_volume": pole["volume"],
                       "flag_volume": round(_avg(s.v[first:last + 1]), 1), "volume_known": pole["volume"] > 0},
        }
        self._set(SETUP_STATE_ARMED, f"flag of {run} under the {pole['high']:.2f} pole: trigger {trig:.2f}, "
                                     f"stop {flag_low:.2f}, risk {risk:.2f}")
        return events + self.arm_events(prev)

    def _blocked(self, bars: list[Bar], last: int, risk: float) -> str | None:
        """Why a flag ending at ``last`` would not arm: the window, the MACD, then the risk."""
        p = self.p
        why = window_blocked(p, bars[last].t + 60)
        if why is None and p.macd_positive and self.series.hist[last] <= 0:
            why = "MACD negative -- not on the front side"
        return why if why is not None else risk_blocked(p, risk)

    def _partial_flag(self, bars: list[Bar], last: int, pole: dict, run: int) -> dict[str, Any]:
        """A flag shorter than the rule asks: the levels it would arm with if it were complete now
        (ADR 036) -- what still blocks it, and how many candles it waits for."""
        s, p = self.series, self.p
        first = last - run + 1
        flag_low = min(s.lo[first:last + 1])
        trig = s.h[last]
        entry = round(trig + p.entry_offset, 4)
        risk = round(entry - flag_low, 4)
        need = p.min_flag_bars - run
        blocked = self._flag_fault(bars, pole, first, last) or self._blocked(bars, last, risk)
        return forming_levels(trig, entry, flag_low, p.target1(pole["high"], entry, risk), bars=run, blocked=blocked,
                              waiting=f"{need} more red or doji candle{'' if need == 1 else 's'}")

    # -- the pattern ----------------------------------------------------------
    def _red_run(self, last: int) -> int:
        """Red or doji candles at the end of the day so far."""
        s = self.series
        i = last
        while i >= 0 and not _green(s.o[i], s.c[i]):
            i -= 1
        return last - i

    def _pole(self, bars: list[Bar], top: int) -> dict[str, Any] | None:
        """The pole ending at ``top``, or None when the candles there are not one."""
        s, p = self.series, self.p
        if top < 0 or not _green(s.o[top], s.c[top]):
            return None
        start = top
        while start - 1 >= 0 and _green(s.o[start - 1], s.c[start - 1]):
            start -= 1
        count = top - start + 1
        if count < p.pole_min_bars:
            return None
        high, low = max(s.h[start:top + 1]), min(s.lo[start:top + 1])
        if low <= 0:
            return None
        pct = high / low - 1
        if pct < p.pole_min_pct - EPS and (p.pole_min_dollars is None or high - low < p.pole_min_dollars - EPS):
            return None
        if p.require_hod and high < s.hod[top] - EPS:
            return None
        return {"t": bars[top].t, "high": high, "low": low, "pct": round(pct, 4), "bars": count,
                "start": start, "top": top, "volume": round(_avg(s.v[start:top + 1]), 1)}

    def _pole_fault(self, pole: dict) -> str | None:
        s, p = self.series, self.p
        first, top = pole["start"], pole["top"]
        if p.pole_volume_rising and pole["bars"] >= 2 and s.v[first] > 0 and s.v[top] < s.v[first]:
            return (f"the pole's volume fell ({int(s.v[top]):,} on its last candle, {int(s.v[first]):,} on its first) "
                    "-- the move is tiring")
        if p.max_pole_wick is not None:
            rng = s.h[top] - s.lo[top]
            wick = s.h[top] - max(s.o[top], s.c[top])
            if rng > EPS and wick / rng > p.max_pole_wick + EPS:
                return f"the pole's top candle left a {_pct(wick / rng)}% topping tail"
        return None

    def _flag_fault(self, bars: list[Bar], pole: dict, first: int, last: int) -> str | None:
        s, p = self.series, self.p
        for n, i in enumerate(range(first, last + 1), start=1):
            if s.h[i] > s.h[i - 1] + EPS:
                return f"flag candle {n} made a higher high than the candle before it"
        flag_low = min(s.lo[first:last + 1])
        span = max(pole["high"] - pole["low"], EPS)
        given = (pole["high"] - flag_low) / span
        if given > p.max_retrace + EPS:
            return f"the flag gave back {_pct(given)}% of the pole -- more than {_pct(p.max_retrace)}%"
        if p.flag_volume_lighter and pole["volume"] > 0:
            flag_volume = _avg(s.v[first:last + 1])
            if flag_volume >= pole["volume"] - EPS:
                return (f"the flag's volume ({int(flag_volume):,} a candle) is not lighter than the pole's "
                        f"({int(pole['volume']):,})")
        if p.ema_hold and any(s.c[i] < s.e[i] * (1 - p.ema_tol) - EPS for i in range(first, last + 1)):
            return "a flag candle closed under the 9 EMA"
        if p.ema_touch_pct is not None and s.e[last] > 0:
            off = abs(flag_low - s.e[last]) / s.e[last]
            if off > p.ema_touch_pct + EPS:
                return f"the flag's low stayed {_pct(off)}% off the 9 EMA -- the rule asks within {_pct(p.ema_touch_pct)}%"
        if p.reject_red_volume_high:
            i = s.vmax_i[last]                # the first candle with the day's biggest volume
            if s.v[i] > 0:
                if s.c[i] < s.o[i] - EPS:
                    return "the day's highest-volume candle is red -- sellers, not buyers, own the day"
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
