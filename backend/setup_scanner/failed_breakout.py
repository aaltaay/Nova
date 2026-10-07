"""The failed breakout: the flat-top breakout mirrored for a short (ADR 049 section 7, pre-registered; its step 4
section names the CHOSEN numbers).

After every completed bar the detector looks back for the newest failure, statelessly (a seed after a restart
finds the same setup):

  flat top   the high of day before the poke, touched at least ``min_touches`` times in the ``lookback``
             candles before it: a touch is a high within ``max(touch_pct of it, touch_dollars)`` under it,
             the candle that made it included, and a touch after the first made no new high (retested, the
             flat top's touch rule)
  poke       the first candle whose high is at least ``poke_dollars`` over the flat top
  failure    the poke, or one of the ``fail_bars`` candles after it, closes back under the flat top -- the
             first such close; when they all close over it the breakout held, and the setup is over
  armed      at the failure candle's close: trigger = its low, entry one cent under it, buy stop one cent over
             the highest high since the poke; no MACD rule by default; the next minute inside the window
             (09:35-11:30); risk inside the band
  expires    the trigger prints within ``trigger_bars`` candles after the failure candle, else it fails; a close
             back over the flat top, or a high over the poke's, fails it before then

``leg`` is a poke over a tested flat top that has not failed yet. Every number is a ``FailedBreakoutParams``
field a template sets (ADR 029). Pure: no I/O, no clock.
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
    SETUP_KIND_FAILED_BREAKOUT,
    SETUP_KIND_SECOND_FAILED_BREAKOUT,
    SHORT_ENTRY_OFFSET_DOLLARS,
    SHORT_FAILED_BREAKOUT_CUTOFF_ET,
    SHORT_FB_FAIL_BARS,
    SHORT_FB_LOOKBACK,
    SHORT_FB_MACD_NEGATIVE,
    SHORT_FB_MIN_TOUCHES,
    SHORT_FB_POKE_DOLLARS,
    SHORT_FB_TOUCH_DOLLARS,
    SHORT_FB_TOUCH_PCT,
    SHORT_FB_TRIGGER_BARS,
    SHORT_MAX_PER_SYMBOL_DAY,
    SHORT_STOP_OFFSET_DOLLARS,
    SHORT_WINDOW_START_ET,
)
from setup_scanner.bars import Bar
from setup_scanner.detector import EPS, window_blocked
from setup_scanner.detector_short import ShortTriggerDetector, short_levels, short_risk_blocked, short_target


@dataclass(frozen=True)
class FailedBreakoutParams:
    touch_pct: float = SHORT_FB_TOUCH_PCT
    touch_dollars: float = SHORT_FB_TOUCH_DOLLARS
    min_touches: int = SHORT_FB_MIN_TOUCHES
    lookback: int = SHORT_FB_LOOKBACK
    poke_dollars: float = SHORT_FB_POKE_DOLLARS
    fail_bars: int = SHORT_FB_FAIL_BARS
    trigger_bars: int = SHORT_FB_TRIGGER_BARS
    ema_period: int = SETUPS_EMA_PERIOD
    macd_negative: bool = SHORT_FB_MACD_NEGATIVE
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
    entry_cutoff: str = SHORT_FAILED_BREAKOUT_CUTOFF_ET
    max_per_symbol_day: int = SHORT_MAX_PER_SYMBOL_DAY


@dataclass(frozen=True)
class _Found:
    """A failure: the poke ``p_i`` over the flat top ``level``, its touches, and the candle ``f_i`` that closed
    back under (None while the breakout has not failed yet)."""

    level: float
    zone: float
    p_i: int
    touches: tuple[int, ...]
    f_i: int | None


@dataclass
class FailedBreakoutDetector(ShortTriggerDetector):
    p: FailedBreakoutParams = field(default_factory=FailedBreakoutParams)

    FIRST_KIND: ClassVar[str] = SETUP_KIND_FAILED_BREAKOUT
    SECOND_KIND: ClassVar[str | None] = SETUP_KIND_SECOND_FAILED_BREAKOUT

    def on_bars(self, bars: list[Bar]) -> list[tuple[str, dict]]:
        n = len(bars)
        self.series.update(bars)
        self.forming = None
        need = self.p.lookback + 2
        if n < need:
            if self.state == SETUP_STATE_WATCHING:
                self.reason = f"warming up ({n}/{need} bars)"
            return []
        if self.nth >= self.p.max_per_symbol_day:
            return []
        last = n - 1
        prev = self.armed if self.state in (SETUP_STATE_ARMED, SETUP_STATE_NEAR) else None
        found, why = self._find(last)

        if self.state == SETUP_STATE_TRIGGERED:
            if found is None or bars[found.p_i].t == self.triggered.get("leg_t"):
                return []                 # the trade is on; a new setup needs a new poke

        events: list[tuple[str, dict]] = []
        if found is not None and found.f_i is not None:
            return self._arm(bars, last, found, prev)
        if found is not None:            # a poke that has not failed yet
            self.leg, self.armed = self._leg(bars, found, last), None
            was = self.state
            self._set(SETUP_STATE_LEG, f"poked over the {found.level:.2f} flat top ({len(found.touches)} touches) -- "
                                       "wait for a close back under it")
            if prev is not None:
                events.append(("disarmed", self._key_view(prev, reason="a newer poke took over")))
            if was != SETUP_STATE_LEG:
                events.append(("leg", self.view()))
            return events
        self.armed = None
        if why is not None:
            leg, reason = why
            self.leg = leg
            if self.state != SETUP_STATE_FAILED or self.reason != reason:
                self._set(SETUP_STATE_FAILED, reason)
                if prev is not None:
                    events.append(("failed", self._key_view(prev, reason=reason)))
            return events
        self.leg = None
        self._set(SETUP_STATE_WATCHING, "no poke over a tested flat top")
        if prev is not None:
            events.append(("disarmed", self._key_view(prev, reason="no poke over a tested flat top")))
        return events

    # -- the pattern ----------------------------------------------------------
    def _touches(self, p_i: int, level: float) -> tuple[float, tuple[int, ...]]:
        s, p = self.series, self.p
        zone = level - max(p.touch_pct * level, p.touch_dollars)
        lo = max(0, p_i - p.lookback)
        return zone, tuple(i for i in range(lo, p_i) if s.h[i] >= zone - EPS)

    def _poke(self, p_i: int) -> tuple[float, float, tuple[int, ...]] | None:
        """``(level, zone, touches)`` when candle ``p_i`` is the first poke over a tested flat top."""
        s, p = self.series, self.p
        if p_i < 1:
            return None
        level = s.hod[p_i - 1]
        if s.h[p_i] < level + p.poke_dollars - EPS:
            return None
        zone, touches = self._touches(p_i, level)
        if len(touches) < p.min_touches:
            return None
        # The flat top's touch rule (ADR 031 amendment): a touch after the first made no new high -- the level
        # was tested, not pushed through. Highs rising a cent at a time are a move, not a flat top.
        if p.min_touches > 1 and not any(s.h[i] <= max(s.h[j] for j in touches if j < i) + EPS for i in touches[1:]):
            return None
        return level, zone, touches

    def _find(self, last: int) -> tuple[_Found | None, tuple[dict, str] | None]:
        """The newest failure in reach of ``last`` (or a poke still waiting on one), and -- when none stands -- the
        leg and rule of the last one that ended."""
        s, p = self.series, self.p
        ended: tuple[dict, str] | None = None
        for f_back in range(0, p.trigger_bars + 1):
            f_i = last - f_back
            for p_i in range(f_i - p.fail_bars, f_i + 1):
                if p_i < 1:
                    continue
                poke = self._poke(p_i)
                if poke is None:
                    continue
                level, zone, touches = poke
                closes = range(p_i, f_i)
                if any(s.c[i] < level - EPS for i in closes) or s.c[f_i] >= level - EPS:
                    continue              # f_i is not the first close back under
                after = range(f_i + 1, last + 1)
                high = max(s.h[p_i:f_i + 1])
                found = _Found(level, zone, p_i, touches, f_i)
                if any(s.c[i] >= level - EPS for i in after):
                    ended = ended or (self._leg_at(found, last), "closed back over the flat top")
                    continue
                if any(s.h[i] > high + EPS for i in after):
                    ended = ended or (self._leg_at(found, last), "made a new high over the poke")
                    continue
                return found, None
        # No failure in reach: a poke still inside its fail window, or one that held or went stale.
        for p_i in range(last, max(last - p.fail_bars - 1, 0), -1):
            poke = self._poke(p_i)
            if poke is None:
                continue
            level, zone, touches = poke
            if all(s.c[i] >= level - EPS for i in range(p_i, last + 1)):
                if last - p_i < p.fail_bars:
                    return _Found(level, zone, p_i, touches, None), None
                return None, (self._leg_at(_Found(level, zone, p_i, touches, None), last),
                              f"the breakout held: {p.fail_bars + 1} candles closed over the flat top")
        stale = self._stale(last)
        return None, ended or stale

    def _stale(self, last: int) -> tuple[dict, str] | None:
        """A failure just past its trigger window: no breakdown came."""
        s, p = self.series, self.p
        f_i = last - p.trigger_bars - 1
        for p_i in range(f_i - p.fail_bars, f_i + 1):
            if p_i < 1 or f_i < 1:
                continue
            poke = self._poke(p_i)
            if poke is None:
                continue
            level, zone, touches = poke
            if any(s.c[i] < level - EPS for i in range(p_i, f_i)) or s.c[f_i] >= level - EPS:
                continue
            found = _Found(level, zone, p_i, touches, f_i)
            return self._leg_at(found, last), f"no breakdown within {p.trigger_bars} candles"
        return None

    def _leg_at(self, found: _Found, last: int) -> dict[str, Any]:
        return self._leg(None, found, last)

    def _leg(self, bars: list[Bar] | None, found: _Found, last: int) -> dict[str, Any]:
        s = self.series
        end = found.f_i if found.f_i is not None else last
        high = max(s.h[found.p_i:end + 1])
        return {"t": s.t[found.p_i], "high": high, "low": found.level,
                "pct": round((high - found.level) / found.level, 4) if found.level > 0 else 0.0,
                "bars": len(found.touches), "touches": [[s.t[i], s.h[i]] for i in found.touches],
                "zone": round(found.zone, 6)}

    def _arm(self, bars: list[Bar], last: int, found: _Found, prev: dict | None) -> list[tuple[str, dict]]:
        s, p = self.series, self.p
        f_i = found.f_i
        assert f_i is not None
        events: list[tuple[str, dict]] = []
        self.leg = self._leg(bars, found, last)
        trig = s.lo[f_i]
        high = max(s.h[found.p_i:f_i + 1])
        entry = round(trig - p.entry_offset, 4)
        stop = round(high + p.stop_offset, 4)
        risk = round(stop - entry, 4)
        target = short_target(entry, risk, p.target_r)
        blocked = window_blocked(p, bars[f_i].t + p.bar_sec)
        if blocked is None and p.macd_negative and s.hist[f_i] >= 0:
            blocked = "MACD positive -- not on the back side"
        if blocked is None:
            blocked = short_risk_blocked(p, risk, entry=entry)
        if blocked:
            self.armed = None
            self.forming = short_levels(trig, entry, stop, target, bars=len(found.touches), blocked=blocked)
            self._set(SETUP_STATE_PULLBACK, blocked)
            if prev is not None:
                events.append(("disarmed", self._key_view(prev, reason=blocked)))
            return events
        key = bars[found.p_i].t
        if prev is not None and prev["leg_t"] != key:
            events.append(("disarmed", self._key_view(prev, reason="a newer poke took over")))
            prev = None
        self.armed = {
            "leg_t": key, "trigger": round(trig, 4), "entry": entry, "stop": stop, "risk": risk, "target1": target,
            "pullback_bars": f_i - found.p_i + 1, "leg_high": high, "leg_low": found.level,
            "leg_pct": self.leg["pct"], "armed_bar_t": bars[f_i].t,
            "armed_at": (prev or {}).get("armed_at") or bars[f_i].t + p.bar_sec, "kind": self.kind_now(),
            "detail": {"level": found.level, "zone": round(found.zone, 6), "touches": self.leg["touches"],
                       "poke_t": bars[found.p_i].t, "failed_bar_t": bars[f_i].t},
        }
        self._set(SETUP_STATE_ARMED, f"failed back under the {found.level:.2f} flat top: short under {trig:.2f}, "
                                     f"buy stop {stop:.2f}, risk {risk:.2f}")
        return events + self.arm_events(prev)
