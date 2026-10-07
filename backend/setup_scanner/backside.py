"""Backside lower high: the first pullback mirrored for a short (ADR 049 section 5, pre-registered).

After every completed bar the detector reads the end of the day so far, the first pullback's stateless way
(``pullback.py``): for m = 1, 2, 3 the bar m bars back is tried as the fade's low and the bars after it as the
bounce; the first m that qualifies is the setup.

  fade       a bar whose low is at or under every low of the ``fade_lookback`` bars before it, at least
             ``fade_pct`` under the high of day through it
  bounce     the 1-3 bars after it: no new low under the fade's, every high under the high of day (a lower
             high), less than ``max_retrace`` of the fade taken back, every close at or under the EMA
  armed      trigger = the last bounce bar's low, entry one cent under it, buy stop one cent over the bounce's
             highest high, risk 3c-20c counting one cent of slippage, the last bar's MACD histogram under zero,
             the next bar inside the window (09:35-11:30)
  near       price within max(3c, 0.3%) over the trigger
  triggered  a live price at or under the entry (``detector_short``)

The board's other states are for the eye: ``leg`` (a fresh low -- wait for the bounce), ``pullback`` (a setup
exists but MACD, risk or the window blocks it), ``failed`` (the bounce broke a rule), ``watching``. A bounce
bar that makes a new low is the next fade. Target 1 is entry - target R x risk. Every number is a
``BacksideParams`` field a template sets (ADR 029). Pure: no I/O, no clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

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
    SETUP_KIND_BACKSIDE,
    SETUP_KIND_SECOND_BACKSIDE,
    SHORT_BACKSIDE_CUTOFF_ET,
    SHORT_BACKSIDE_FADE_LOOKBACK,
    SHORT_BACKSIDE_FADE_PCT,
    SHORT_BACKSIDE_MAX_BOUNCE_BARS,
    SHORT_BACKSIDE_MAX_RETRACE,
    SHORT_BACKSIDE_MIN_BOUNCE_BARS,
    SHORT_BACKSIDE_STALE_BARS,
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
class BacksideParams:
    fade_pct: float = SHORT_BACKSIDE_FADE_PCT
    fade_lookback: int = SHORT_BACKSIDE_FADE_LOOKBACK
    min_bounce_bars: int = SHORT_BACKSIDE_MIN_BOUNCE_BARS
    max_bounce_bars: int = SHORT_BACKSIDE_MAX_BOUNCE_BARS
    max_retrace: float = SHORT_BACKSIDE_MAX_RETRACE
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
    entry_cutoff: str = SHORT_BACKSIDE_CUTOFF_ET
    max_per_symbol_day: int = SHORT_MAX_PER_SYMBOL_DAY


def _pct(x: float) -> str:
    return f"{100 * x:.1f}"


@dataclass
class BacksideDetector(ShortTriggerDetector):
    p: BacksideParams = field(default_factory=BacksideParams)

    FIRST_KIND: ClassVar[str] = SETUP_KIND_BACKSIDE
    SECOND_KIND: ClassVar[str | None] = SETUP_KIND_SECOND_BACKSIDE

    def on_bars(self, bars: list[Bar]) -> list[tuple[str, dict]]:
        n = len(bars)
        self.series.update(bars)
        self.forming = None
        need = self.p.fade_lookback + 2
        if n < need:
            if self.state == SETUP_STATE_WATCHING:
                self.reason = f"warming up ({n}/{need} bars)"
            return []
        if self.nth >= self.p.max_per_symbol_day:
            return []
        s = self.series
        last = n - 1
        prev = self.armed if self.state in (SETUP_STATE_ARMED, SETUP_STATE_NEAR) else None

        cand, first_fail = None, None
        for m in range(self.p.min_bounce_bars, self.p.max_bounce_bars + 1):
            f_i = last - m
            fade = self._qualify_fade(bars, f_i)
            if fade is None:
                continue
            bounce = range(f_i + 1, last + 1)
            hi = max(s.h[i] for i in bounce)
            why = None
            if min(s.lo[i] for i in bounce) < fade["low"] - EPS:
                why = "made a new low under the fade's"
            elif hi >= fade["high"] - EPS:
                why = "the bounce reached the high of day -- not a lower high"
            elif (hi - fade["low"]) / max(fade["high"] - fade["low"], EPS) >= self.p.max_retrace - EPS:
                why = f"the bounce took back {_pct(self.p.max_retrace)}% of the fade"
            elif any(s.c[i] > s.e[i] * (1 + self.p.ema_tol) + EPS for i in bounce):
                why = "a bounce candle closed over the 9 EMA"
            if why:
                first_fail = first_fail or (fade, why)
                continue
            cand = (m, fade, hi)
            break

        if self.state == SETUP_STATE_TRIGGERED:
            fresh = self._qualify_fade(bars, last)
            new_fade = (cand and cand[1]["t"] != self.triggered.get("leg_t")) or (
                fresh and fresh["t"] != self.triggered.get("leg_t"))
            if not new_fade:
                return []                 # the trade is on; a new setup needs a new fade

        if cand is not None:
            return self._arm(bars, last, cand, prev)

        events: list[tuple[str, dict]] = []
        fresh = self._qualify_fade(bars, last)
        if fresh is not None:
            self.leg, self.armed = fresh, None
            was = self.state
            self._set(SETUP_STATE_LEG, f"new low {fresh['low']:.2f}, {_pct(fresh['pct'])}% off the {fresh['high']:.2f} "
                                       "high -- wait for the bounce")
            if prev is not None:
                events.append(("disarmed", self._key_view(prev)))
            if was != SETUP_STATE_LEG:
                events.append(("leg", self.view()))
            return events
        fail = first_fail or self._stale_fade(bars, last)
        self.armed = None
        if fail is not None:
            self.leg = fail[0]
            if self.state != SETUP_STATE_FAILED or self.reason != fail[1]:
                self._set(SETUP_STATE_FAILED, fail[1])
                if prev is not None:
                    events.append(("failed", self._key_view(prev, reason=fail[1])))
            return events
        self.leg = None
        self._set(SETUP_STATE_WATCHING, "no fresh fade")
        if prev is not None:
            events.append(("disarmed", self._key_view(prev, reason="no fresh fade")))
        return events

    def _arm(self, bars: list[Bar], last: int, cand: tuple, prev: dict | None) -> list[tuple[str, dict]]:
        m, fade, bounce_high = cand
        s, p = self.series, self.p
        events: list[tuple[str, dict]] = []
        self.leg = fade
        trig = s.lo[last]
        entry = round(trig - p.entry_offset, 4)
        stop = round(bounce_high + p.stop_offset, 4)
        risk = round(stop - entry, 4)
        target = short_target(entry, risk, p.target_r)
        blocked = window_blocked(p, bars[last].t + p.bar_sec)
        if blocked is None and p.macd_negative and s.hist[last] >= 0:
            blocked = "MACD positive -- not on the back side"
        if blocked is None:
            blocked = short_risk_blocked(p, risk, entry=entry)
        if blocked:
            self.armed = None
            self.forming = short_levels(trig, entry, stop, target, bars=m, blocked=blocked)
            self._set(SETUP_STATE_PULLBACK, blocked)
            if prev is not None:
                events.append(("disarmed", self._key_view(prev, reason=blocked)))
            return events
        if prev is not None and prev["leg_t"] != fade["t"]:
            events.append(("disarmed", self._key_view(prev, reason="a newer fade took over")))
            prev = None
        self.armed = {
            "leg_t": fade["t"], "trigger": round(trig, 4), "entry": entry, "stop": stop, "risk": risk,
            "target1": target, "pullback_bars": m, "leg_high": fade["high"], "leg_low": fade["low"],
            "leg_pct": fade["pct"], "armed_bar_t": bars[last].t,
            "armed_at": (prev or {}).get("armed_at") or bars[last].t + p.bar_sec, "kind": self.kind_now(),
            "detail": {"bounce_bars": m, "bounce_high": round(bounce_high, 4)},
        }
        self._set(SETUP_STATE_ARMED, f"short under {trig:.2f}, buy stop {stop:.2f}, risk {risk:.2f}")
        return events + self.arm_events(prev)

    def _qualify_fade(self, bars: list[Bar], f_i: int) -> dict | None:
        s, p = self.series, self.p
        if f_i < p.fade_lookback:
            return None
        low = s.lo[f_i]
        if low > min(s.lo[f_i - p.fade_lookback:f_i]) + EPS:
            return None
        hod = s.hod[f_i]
        if hod <= 0 or low <= 0 or (hod - low) / hod < p.fade_pct - EPS:
            return None
        return {"t": bars[f_i].t, "high": hod, "low": low, "pct": round((hod - low) / hod, 4)}

    def _stale_fade(self, bars: list[Bar], last: int) -> tuple[dict, str] | None:
        """A fade 4-10 bars back with no lower low since: the bounce ran too long."""
        for f_i in range(last - self.p.max_bounce_bars - 1, max(last - SHORT_BACKSIDE_STALE_BARS, -1), -1):
            fade = self._qualify_fade(bars, f_i)
            if fade is not None:
                if min(self.series.lo[f_i + 1:last + 1]) >= fade["low"] - EPS:
                    return fade, f"the bounce ran past {self.p.max_bounce_bars} candles"
                return None
        return None
