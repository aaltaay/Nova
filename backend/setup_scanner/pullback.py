"""The first (and second) pullback as a live state machine on one-minute bars.

Arming is the pre-registered P1 rule of the research screen
(research/momentum/backtest_setups.py ``find_pullback``), evaluated the same
stateless way after every completed bar (ADR 022, Bot-Trading-Plan section 2g):
for m = 1, 2, 3 the bar m bars back is tried as the leg high and the bars after
it as the pullback; the first m that qualifies is the setup.

  leg        a bar whose high is the highest of the prior 30 bars and the day's
             high so far, at least 5% above the lowest low of the 10 bars ending
             at it
  pullback   the 1-3 bars after it: no new high, less than half the leg given
             back, every close at or above the 9 EMA
  armed      trigger = the last pullback bar's high, entry one cent over it, stop
             = the pullback low, risk 3c-20c counting one cent of slippage, the
             last bar's MACD histogram > 0, the next bar inside the entry window
  near       price within max(3c, 0.3%) of the trigger
  triggered  a live price above the trigger (entry at the bar's open when it
             gapped over, and skipped if that gap pushes the risk over the cap)

The board's other states are for the eye, not for arming: ``leg`` (a fresh
high -- wait for the pullback), ``pullback`` (a setup exists but MACD, risk or
the window blocks it), ``failed`` (the pullback broke a rule), ``watching``.

Every number above is a ``PullbackParams`` field, which a template sets (ADR
029); the defaults are the pre-registered rules. At most ``max_per_symbol_day``
setups trigger on one symbol a day (the research's cap, ADR 022). Target 1 is
max(leg high, entry + R x risk), or entry plus a fixed amount when the template
asks for one.

The trigger on a live price, the near band and the view are the shared
``setup_scanner/detector.TriggerDetector`` (ADR 031), moved there unchanged.

Pure: no I/O, no clock. The engine feeds bars and prices.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar
from zoneinfo import ZoneInfo

from constants_setups import (
    SETUP_KIND_FIRST_PULLBACK,
    SETUP_KIND_SECOND_PULLBACK,
    SETUP_STATE_ARMED,
    SETUP_STATE_FAILED,
    SETUP_STATE_LEG,
    SETUP_STATE_NEAR,
    SETUP_STATE_PULLBACK,
    SETUP_STATE_TRIGGERED,
    SETUP_STATE_WATCHING,
    SETUPS_EMA_PERIOD,
    SETUPS_EMA_TOLERANCE,
    SETUPS_ENTRY_CUTOFF_ET,
    SETUPS_ENTRY_OFFSET_DOLLARS,
    SETUPS_LEG_LOOKBACK_BARS,
    SETUPS_LEG_PCT,
    SETUPS_LEG_WINDOW_BARS,
    SETUPS_MACD_FAST,
    SETUPS_MACD_POSITIVE,
    SETUPS_MACD_SIGNAL,
    SETUPS_MACD_SLOW,
    SETUPS_MAX_PER_SYMBOL_DAY,
    SETUPS_MAX_PULLBACK_BARS,
    SETUPS_MAX_RETRACE,
    SETUPS_MIN_PULLBACK_BARS,
    SETUPS_MIN_STOP_DOLLARS,
    SETUPS_NEAR_DOLLARS,
    SETUPS_NEAR_PCT,
    SETUPS_REQUIRE_HOD,
    SETUPS_RISK_SLIPPAGE_DOLLARS,
    SETUPS_SESSION_START_ET,
    SETUPS_STOP_CAP_DOLLARS,
    SETUPS_TARGET_FIXED_DOLLARS,
    SETUPS_TARGET_MODE,
    SETUPS_TARGET_R,
)
from setup_scanner.bars import Bar
from setup_scanner.detector import TriggerDetector, et_time, forming_levels, hhmm, risk_blocked
from setup_scanner.series import Series, ema, macd_hist  # noqa: F401 -- callers import them from here

ET = ZoneInfo("America/New_York")
STALE_LEG_BARS = 10       # how far back a leg can still explain a "failed" row
_hhmm = hhmm              # the name this module's callers used before ADR 031


@dataclass(frozen=True)
class PullbackParams:
    leg_pct: float = SETUPS_LEG_PCT
    leg_window: int = SETUPS_LEG_WINDOW_BARS
    leg_lookback: int = SETUPS_LEG_LOOKBACK_BARS
    require_hod: bool = SETUPS_REQUIRE_HOD
    min_pullback_bars: int = SETUPS_MIN_PULLBACK_BARS
    max_pullback_bars: int = SETUPS_MAX_PULLBACK_BARS
    max_retrace: float = SETUPS_MAX_RETRACE
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
    max_per_symbol_day: int = SETUPS_MAX_PER_SYMBOL_DAY

    def target1(self, leg_high: float, entry: float, risk: float) -> float:
        if self.target_mode == "fixed":
            return round(entry + self.target_fixed, 4)
        return round(max(leg_high, entry + self.target_r * risk), 4)


@dataclass
class PullbackDetector(TriggerDetector):
    """One symbol's setup state. Call ``on_bars`` after each completed bar and
    ``on_price`` on every live price in between (``TriggerDetector``)."""

    p: PullbackParams = field(default_factory=PullbackParams)

    FIRST_KIND: ClassVar[str] = SETUP_KIND_FIRST_PULLBACK
    SECOND_KIND: ClassVar[str | None] = SETUP_KIND_SECOND_PULLBACK

    # -- bar close ---------------------------------------------------------
    def on_bars(self, bars: list[Bar]) -> list[tuple[str, dict]]:
        """Re-evaluate after a bar completes. ``bars`` is the whole day so far, oldest first."""
        n = len(bars)
        self.series.update(bars)
        self.forming = None
        if n < self.p.leg_lookback + 2:
            if self.state == SETUP_STATE_WATCHING:
                self.reason = f"warming up ({n}/{self.p.leg_lookback + 2} bars)"
            return []
        if self.state == SETUP_STATE_TRIGGERED and self.nth >= self.p.max_per_symbol_day:
            return []                     # the day's setups on this symbol are used
        h, lows, c = self.series.h, self.series.lo, self.series.c
        e9, hist = self.series.e, self.series.hist
        last = n - 1
        prev = self.armed if self.state in (SETUP_STATE_ARMED, SETUP_STATE_NEAR) else None

        cand, first_fail = None, None
        for m in range(self.p.min_pullback_bars, self.p.max_pullback_bars + 1):
            H = last - m
            leg = self._qualify_leg(bars, h, lows, H)
            if leg is None:
                continue
            pb = range(H + 1, last + 1)
            pb_low = min(lows[i] for i in pb)
            why = None
            if max(h[i] for i in pb) > leg["high"]:
                why = "made a new high without a fresh 5% leg"
            elif (leg["high"] - pb_low) / max(leg["high"] - leg["low"], 1e-9) >= self.p.max_retrace:
                why = "gave back half the leg"
            elif any(c[i] < e9[i] * (1 - self.p.ema_tol) for i in pb):
                why = "a pullback candle closed under the 9 EMA"
            if why:
                first_fail = first_fail or (leg, why)
                continue
            cand = (m, leg, pb_low)
            break

        if self.state == SETUP_STATE_TRIGGERED:
            fresh = self._qualify_leg(bars, h, lows, last)
            new_leg = (cand and cand[1]["t"] != self.triggered.get("leg_t")) or (
                fresh and fresh["t"] != self.triggered.get("leg_t"))
            if not new_leg:
                return []                 # the trade is on; a new setup needs a new leg

        if cand is not None:
            return self._arm(bars, h, hist, last, cand, prev)

        events: list[tuple[str, dict]] = []
        fresh = self._qualify_leg(bars, h, lows, last)
        if fresh is not None:
            self.leg, self.armed = fresh, None
            was = self.state
            self._set(SETUP_STATE_LEG, f"new high {fresh['high']:.2f} on a {100 * fresh['pct']:.1f}% leg -- wait for the pullback")
            if prev is not None:
                events.append(("disarmed", self._key_view(prev)))
            if was != SETUP_STATE_LEG:
                events.append(("leg", self.view()))
            return events
        fail = first_fail or self._stale_leg(bars, h, lows, last)
        self.armed = None
        if fail is not None:
            self.leg = fail[0]
            if self.state != SETUP_STATE_FAILED or self.reason != fail[1]:
                self._set(SETUP_STATE_FAILED, fail[1])
                if prev is not None:
                    events.append(("failed", self._key_view(prev, reason=fail[1])))
            return events
        self.leg = None
        self._set(SETUP_STATE_WATCHING, "no fresh leg")
        if prev is not None:
            events.append(("disarmed", self._key_view(prev, reason="no fresh leg")))
        return events

    def _arm(self, bars, h, hist, last, cand, prev) -> list[tuple[str, dict]]:
        m, leg, pb_low = cand
        events: list[tuple[str, dict]] = []
        self.leg = leg
        trig = h[last]
        entry = round(trig + self.p.entry_offset, 4)
        risk = round(entry - pb_low, 4)
        next_t = et_time(bars[last].t + 60)
        blocked = None
        if not (_hhmm(self.p.session_start) <= next_t < _hhmm(self.p.entry_cutoff)):
            blocked = f"outside the entry window {self.p.session_start}-{self.p.entry_cutoff} ET"
        elif self.p.macd_positive and hist[last] <= 0:
            blocked = "MACD negative -- not on the front side"
        else:
            blocked = risk_blocked(self.p, risk)
        if blocked:
            self.armed = None
            self.forming = forming_levels(trig, entry, pb_low, self.p.target1(leg["high"], entry, risk), bars=m,
                                          blocked=blocked)
            self._set(SETUP_STATE_PULLBACK, blocked)
            if prev is not None:
                events.append(("disarmed", self._key_view(prev, reason=blocked)))
            return events
        if prev is not None and prev["leg_t"] != leg["t"]:
            events.append(("disarmed", self._key_view(prev, reason="a newer leg took over")))
            prev = None
        self.armed = {
            "leg_t": leg["t"], "trigger": round(trig, 4), "entry": entry, "stop": round(pb_low, 4),
            "risk": risk, "target1": self.p.target1(leg["high"], entry, risk),
            "pullback_bars": m, "leg_high": leg["high"], "leg_low": leg["low"], "leg_pct": leg["pct"],
            "armed_bar_t": bars[last].t, "armed_at": (prev or {}).get("armed_at") or bars[last].t + 60,
            "kind": self.kind_now(), "detail": None,
        }
        self._set(SETUP_STATE_ARMED, f"trigger {trig:.2f}, stop {pb_low:.2f}, risk {risk:.2f}")
        return events + self.arm_events(prev)

    # -- helpers ------------------------------------------------------------
    def _qualify_leg(self, bars: list[Bar], h: list[float], lows: list[float], H: int) -> dict | None:
        p = self.p
        if H < p.leg_lookback:
            return None
        leg_high = h[H]
        if leg_high < max(h[H - p.leg_lookback:H]):
            return None
        if p.require_hod and H > 0 and leg_high < self.series.prior_high(H):
            return None
        leg_low = min(lows[max(0, H - p.leg_window + 1):H + 1])
        if leg_low <= 0 or leg_high / leg_low - 1 < p.leg_pct:
            return None
        return {"t": bars[H].t, "high": leg_high, "low": leg_low, "pct": round(leg_high / leg_low - 1, 4)}

    def _stale_leg(self, bars, h, lows, last) -> tuple[dict, str] | None:
        """A leg 4-10 bars back with no higher high since: the pullback ran too long."""
        for H in range(last - self.p.max_pullback_bars - 1, max(last - STALE_LEG_BARS, -1), -1):
            leg = self._qualify_leg(bars, h, lows, H)
            if leg is not None:
                if max(h[H + 1:last + 1]) <= leg["high"]:
                    return leg, f"pullback ran past {self.p.max_pullback_bars} candles"
                return None
        return None
