"""Lost VWAP: red to green mirrored for a short (ADR 049 section 8, pre-registered; its step 4 section names the
CHOSEN readings).

One try a day. After every completed bar:

  open       the first candle at or after ``open_at`` (09:30); every close from it up to the loss sits at or
             over the session VWAP (the scanner's own, ``Series.vw``: the chart's rule) -- a day whose opening
             candle closes under VWAP is out
  loss       the first close under VWAP
  retest     a later candle whose high comes within ``max(retest_pct of VWAP, retest_dollars)`` under VWAP, or
             over it, and closes under it: VWAP turned it back. A close back over VWAP before the retest ends the
             day. A retest before the window opens (09:35) is not the try.
  armed      at the retest's close: trigger = its low, entry one cent under it, buy stop one cent over the higher
             of VWAP and the retest's high; the next minute inside the window (09:35-12:00); risk inside the
             band -- a risk outside it spends the day's try
  after      armed until it triggers, a candle closes back over VWAP (the day ends) or the window closes

Every number is a ``LostVwapParams`` field a template sets (ADR 029). Pure: no I/O, no clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from constants_setups import (
    SETUP_STATE_ARMED,
    SETUP_STATE_FAILED,
    SETUP_STATE_LEG,
    SETUP_STATE_NEAR,
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
    SETUP_KIND_LOST_VWAP,
    SHORT_ENTRY_OFFSET_DOLLARS,
    SHORT_LOST_VWAP_CUTOFF_ET,
    SHORT_LOST_VWAP_OPEN_ET,
    SHORT_LV_MACD_NEGATIVE,
    SHORT_LV_RETEST_DOLLARS,
    SHORT_LV_RETEST_PCT,
    SHORT_STOP_OFFSET_DOLLARS,
    SHORT_WINDOW_START_ET,
)
from setup_scanner.bars import Bar
from setup_scanner.detector import EPS, et_time, hhmm, window_blocked
from setup_scanner.detector_short import ShortTriggerDetector, short_levels, short_risk_blocked, short_target


@dataclass(frozen=True)
class LostVwapParams:
    open_at: str = SHORT_LOST_VWAP_OPEN_ET
    retest_pct: float = SHORT_LV_RETEST_PCT
    retest_dollars: float = SHORT_LV_RETEST_DOLLARS
    ema_period: int = SETUPS_EMA_PERIOD
    macd_negative: bool = SHORT_LV_MACD_NEGATIVE
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
    entry_cutoff: str = SHORT_LOST_VWAP_CUTOFF_ET
    max_per_symbol_day: int = 1


@dataclass
class LostVwapDetector(ShortTriggerDetector):
    p: LostVwapParams = field(default_factory=LostVwapParams)
    done: str | None = None           # why today's one try is spent

    FIRST_KIND: ClassVar[str] = SETUP_KIND_LOST_VWAP
    SECOND_KIND: ClassVar[str | None] = None

    def restore(self, nth: int) -> None:
        super().restore(nth)
        if self.nth >= 1:
            self.done = "the day's try is spent"

    def on_bars(self, bars: list[Bar]) -> list[tuple[str, dict]]:
        self.series.update(bars)
        self.forming = None
        if self.state == SETUP_STATE_TRIGGERED or self.nth >= 1:
            return []
        if self.done is not None:
            return []
        s, p = self.series, self.p
        last = len(bars) - 1
        prev = self.armed if self.state in (SETUP_STATE_ARMED, SETUP_STATE_NEAR) else None
        o_i = next((i for i in range(len(bars)) if et_time(bars[i].t) >= hhmm(p.open_at)), None)
        if o_i is None:
            self._set(SETUP_STATE_WATCHING, f"waiting for the {p.open_at} open")
            return []
        loss = None
        for i in range(o_i, last + 1):
            vw = s.vw[i]
            if vw is None:
                continue
            if s.c[i] < vw - EPS:
                loss = i
                break
        if loss is None:
            self._set(SETUP_STATE_WATCHING, "over VWAP since the open")
            return []
        if loss == o_i:
            return self._end(prev, None, "the opening candle closed under VWAP: not over VWAP from the open")
        leg = {"t": bars[loss].t, "high": round(float(s.vw[loss] or 0), 4), "low": s.lo[loss],
               "pct": 0.0, "bars": last - loss}
        for i in range(loss + 1, last + 1):
            vw = s.vw[i]
            if vw is None:
                continue
            band = max(p.retest_pct * vw, p.retest_dollars)
            if s.c[i] >= vw - EPS:
                return self._end(prev, leg, "closed back over VWAP before the retest")
            if s.h[i] >= vw - band - EPS and et_time(bars[i].t) >= hhmm(p.session_start):
                return self._arm(bars, i, last, leg, prev)
        self.leg, self.armed = leg, None
        if self.state != SETUP_STATE_LEG:
            self._set(SETUP_STATE_LEG, f"lost VWAP at {et_time(bars[loss].t).strftime('%H:%M')} -- wait for the "
                                       "retest")
            return [("leg", self.view())]
        return []

    def _arm(self, bars: list[Bar], r_i: int, last: int, leg: dict, prev: dict | None) -> list[tuple[str, dict]]:
        s, p = self.series, self.p
        vw = float(s.vw[r_i] or 0)
        for i in range(r_i + 1, last + 1):
            if s.vw[i] is not None and s.c[i] >= float(s.vw[i]) - EPS:
                return self._end(prev, leg, "closed back over VWAP after the retest")
        trig = s.lo[r_i]
        entry = round(trig - p.entry_offset, 4)
        stop = round(max(vw, s.h[r_i]) + p.stop_offset, 4)
        risk = round(stop - entry, 4)
        target = short_target(entry, risk, p.target_r)
        self.leg = leg
        blocked = window_blocked(p, bars[r_i].t + p.bar_sec)
        if blocked is None and p.macd_negative and s.hist[r_i] >= 0:
            blocked = "MACD positive -- not on the back side"
        if blocked is None:
            blocked = short_risk_blocked(p, risk, entry=entry)
        if blocked:
            self.forming = short_levels(trig, entry, stop, target, bars=r_i - leg_index(bars, leg), blocked=blocked)
            return self._end(prev, leg, f"the retest {blocked} -- the day's one try is spent")
        self.armed = {
            "leg_t": leg["t"], "trigger": round(trig, 4), "entry": entry, "stop": stop, "risk": risk,
            "target1": target, "pullback_bars": r_i - leg_index(bars, leg), "leg_high": round(vw, 4),
            "leg_low": leg["low"], "leg_pct": 0.0, "armed_bar_t": bars[r_i].t,
            "armed_at": (prev or {}).get("armed_at") or bars[r_i].t + p.bar_sec, "kind": self.kind_now(),
            "detail": {"vwap": round(vw, 4), "loss_t": leg["t"], "retest_t": bars[r_i].t},
        }
        self._set(SETUP_STATE_ARMED, f"VWAP {vw:.2f} turned the retest back: short under {trig:.2f}, buy stop "
                                     f"{stop:.2f}, risk {risk:.2f}")
        return self.arm_events(prev)

    def _end(self, prev: dict | None, leg: dict | None, why: str) -> list[tuple[str, dict]]:
        """Today's one try is over: failed (with its leg) or watching."""
        self.done, self.armed = why, None
        self.leg = leg
        self._set(SETUP_STATE_FAILED if leg is not None else SETUP_STATE_WATCHING, why)
        if prev is not None:
            return [("failed" if leg is not None else "disarmed", self._key_view(prev, reason=why))]
        return []


def leg_index(bars: list[Bar], leg: dict) -> int:
    """The loss candle's index in ``bars``."""
    t = leg["t"]
    return next((i for i, b in enumerate(bars) if b.t == t), 0)
