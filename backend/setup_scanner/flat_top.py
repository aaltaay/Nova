"""The high-of-day / flat-top breakout as a live state machine on one-minute bars (ADR 031).

Arming is the pre-registered P2 rule of the research screen
(research/momentum/backtest_setups.py ``find_flat_top``, Bot-Trading-Plan
section 2f), evaluated after every completed bar the way the first pullback is
(ADR 022): for m = 2 .. 6 the bar m bars back is tried as the candle that set
the high of day and the bars after it as the base; the first m that qualifies is
the setup.

  impulse    the candle that set the high of day, at least 3% over the lowest
             low of the 10 candles ending at it
  base       the 2-6 candles right after it: no new high, every close within 2%
             under the high, every low at or above the 9 EMA
  armed      trigger = the high of day, the last base candle's MACD histogram
             above zero, the next minute inside the entry window
  hold       (the default, the taught way) after a live price over the high, the
             first of the next ``hold_bars`` completed candles that holds the
             level (its low at or above it) and closes green triggers at its
             close: entry one cent over that close, stop that candle's low -- the
             risk check reads entry minus stop, the cent standing for the
             research's slippage; a close back under the high first fails it, and
             ``hold_bars`` candles without a hold disarm it
  break      (the variant) a live price over the high triggers: entry one cent
             over it (the bar's open when it gapped over), stop the base low

Target 1 is entry + R x risk (the research's), or a fixed amount over the entry.
At most ``max_per_symbol_day`` setups trigger on one symbol a day. A hold
entry is scored from the hold candle, which takes no half at target 1 (the
research's ``half_on_entry_bar=False``). Pure: no I/O, no clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from constants_setups import (
    SETUP_KIND_FLAT_TOP,
    SETUP_KIND_SECOND_FLAT_TOP,
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
    SETUPS_FT_BAND,
    SETUPS_FT_ENTRY,
    SETUPS_FT_ENTRY_BREAK,
    SETUPS_FT_HOLD_BARS,
    SETUPS_FT_IMPULSE_PCT,
    SETUPS_FT_LEG_WINDOW_BARS,
    SETUPS_FT_MAX_CONSOL,
    SETUPS_FT_MAX_PER_SYMBOL_DAY,
    SETUPS_FT_MIN_CONSOL,
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
    SETUPS_TARGET_R,
)
from setup_scanner.bars import Bar, minute_start
from setup_scanner.detector import EPS, TriggerDetector, et_time, forming_levels, hhmm, risk_blocked, window_blocked


@dataclass(frozen=True)
class FlatTopParams:
    impulse_pct: float = SETUPS_FT_IMPULSE_PCT
    leg_window: int = SETUPS_FT_LEG_WINDOW_BARS
    min_consol: int = SETUPS_FT_MIN_CONSOL
    max_consol: int = SETUPS_FT_MAX_CONSOL
    band: float = SETUPS_FT_BAND
    entry_mode: str = SETUPS_FT_ENTRY
    hold_bars: int = SETUPS_FT_HOLD_BARS
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
    target_mode: str = "r"
    target_r: float = SETUPS_TARGET_R
    target_fixed: float = SETUPS_TARGET_FIXED_DOLLARS
    near_dollars: float = SETUPS_NEAR_DOLLARS
    near_pct: float = SETUPS_NEAR_PCT
    session_start: str = SETUPS_SESSION_START_ET
    entry_cutoff: str = SETUPS_ENTRY_CUTOFF_ET
    max_per_symbol_day: int = SETUPS_FT_MAX_PER_SYMBOL_DAY

    @property
    def breaks(self) -> bool:
        return self.entry_mode == SETUPS_FT_ENTRY_BREAK

    def target1(self, entry: float, risk: float) -> float:
        if self.target_mode == "fixed":
            return round(entry + self.target_fixed, 4)
        return round(entry + self.target_r * risk, 4)


def _pct(x: float) -> str:
    return f"{100 * x:.1f}".rstrip("0").rstrip(".")


@dataclass
class FlatTopDetector(TriggerDetector):
    p: FlatTopParams = field(default_factory=FlatTopParams)
    broke: dict[str, Any] | None = None     # hold entry: the break of the high, waiting for the hold

    FIRST_KIND: ClassVar[str] = SETUP_KIND_FLAT_TOP
    SECOND_KIND: ClassVar[str | None] = SETUP_KIND_SECOND_FLAT_TOP

    # -- bar close ---------------------------------------------------------
    def on_bars(self, bars: list[Bar]) -> list[tuple[str, dict]]:
        n = len(bars)
        self.series.update(bars)
        self.forming = None
        need = self.p.leg_window + self.p.min_consol + 1
        if n < need:
            if self.state == SETUP_STATE_WATCHING:
                self.reason = f"warming up ({n}/{need} bars)"
            return []
        if self.state == SETUP_STATE_TRIGGERED and self.nth >= self.p.max_per_symbol_day:
            return []                     # the day's setups on this symbol are used
        last = n - 1
        if self.broke is not None and self.armed is not None:
            return self._hold_check(bars, last)
        prev = self.armed if self.state in (SETUP_STATE_ARMED, SETUP_STATE_NEAR) else None
        cand, first_fail = self._find(bars, last)

        if self.state == SETUP_STATE_TRIGGERED:
            fresh = self._impulse_high(bars, last)
            new = (cand is not None and cand["t"] != self.triggered.get("leg_t")) or (
                fresh is not None and fresh["t"] != self.triggered.get("leg_t"))
            if not new:
                return []                 # the trade is on; a new setup needs a new high of day

        if cand is not None:
            return self._arm(bars, last, cand, prev)

        events: list[tuple[str, dict]] = []
        fresh = self._impulse_high(bars, last)
        if fresh is not None:
            self.leg, self.armed = fresh, None
            was = self.state
            self._set(SETUP_STATE_LEG, f"new high of day {fresh['high']:.2f} on a {_pct(fresh['pct'])}% move -- "
                                       "wait for a base under it")
            if prev is not None:
                events.append(("disarmed", self._key_view(prev, reason="a new high of day")))
            if was != SETUP_STATE_LEG:
                events.append(("leg", self.view()))
            return events
        fail = first_fail or self._stale_base(bars, last)
        self.armed = None
        if fail is not None:
            self.leg = fail[0]
            if self.state != SETUP_STATE_FAILED or self.reason != fail[1]:
                self._set(SETUP_STATE_FAILED, fail[1])
                if prev is not None:
                    events.append(("failed", self._key_view(prev, reason=fail[1])))
            return events
        self.leg = None
        self._set(SETUP_STATE_WATCHING, "no base under the high of day")
        if prev is not None:
            events.append(("disarmed", self._key_view(prev, reason="no base under the high of day")))
        return events

    def _arm(self, bars: list[Bar], last: int, cand: dict, prev: dict | None) -> list[tuple[str, dict]]:
        s, p = self.series, self.p
        events: list[tuple[str, dict]] = []
        level, base_low, m = cand["high"], cand["base_low"], cand["bars"]
        self.leg = {k: cand[k] for k in ("t", "high", "low", "pct", "bars")}
        entry = round(level + p.entry_offset, 4)
        risk = round(entry - base_low, 4)
        blocked = window_blocked(p, bars[last].t + 60)
        if blocked is None and p.macd_positive and s.hist[last] <= 0:
            blocked = "MACD negative -- not on the front side"
        if blocked is None and p.breaks:
            blocked = risk_blocked(p, risk)
        if blocked:
            self.armed, self.broke = None, None
            self.forming = forming_levels(level, entry, base_low, p.target1(entry, risk), bars=m, blocked=blocked)
            self._set(SETUP_STATE_PULLBACK, f"base of {m} candles under {level:.2f}, but {blocked}")
            if prev is not None:
                events.append(("disarmed", self._key_view(prev, reason=blocked)))
            return events
        if prev is not None and prev["leg_t"] != cand["t"]:
            events.append(("disarmed", self._key_view(prev, reason="a newer high of day took over")))
            prev = None
        self.broke = None
        self.armed = {
            "leg_t": cand["t"], "trigger": round(level, 4), "entry": entry, "stop": round(base_low, 4),
            "risk": risk, "target1": p.target1(entry, risk), "pullback_bars": m, "leg_high": level,
            "leg_low": cand["low"], "leg_pct": cand["pct"], "armed_bar_t": bars[last].t,
            "armed_at": (prev or {}).get("armed_at") or bars[last].t + 60, "kind": self.kind_now(),
            "detail": {"entry_mode": p.entry_mode, "base_low": round(base_low, 4), "broke_at": None,
                       "hold_bars": p.hold_bars},
        }
        how = (f"stop {base_low:.2f}, risk {risk:.2f}" if p.breaks
               else f"then a green candle holding over it (up to {p.hold_bars})")
        self._set(SETUP_STATE_ARMED, f"base of {m} candles under the {level:.2f} high: trigger {level:.2f}, {how}")
        return events + self.arm_events(prev)

    # -- live price -------------------------------------------------------
    def on_price(self, price: float, ts: float, *, bar_open: float | None = None) -> list[tuple[str, dict]]:
        if self.p.breaks:
            return super().on_price(price, ts, bar_open=bar_open)
        self.last_price = price
        if self.armed is None or self.state not in (SETUP_STATE_ARMED, SETUP_STATE_NEAR) or self.broke is not None:
            return []
        trig = self.armed["trigger"]
        if price <= trig + EPS:
            return self._near_check(price)
        if et_time(ts) >= hhmm(self.cutoff()):
            return self._disarm(self.armed, "the entry window closed before the break")
        self.broke = {"at": ts, "bar_t": minute_start(ts)}
        self.armed = {**self.armed, "detail": {**(self.armed.get("detail") or {}), "broke_at": ts}}
        was = self.state
        self._set(SETUP_STATE_NEAR, f"broke the {trig:.2f} high -- the first of the next {self.p.hold_bars} candles "
                                    "that holds over it and closes green is the entry")
        return [("near", self.view())] if was != SETUP_STATE_NEAR else []

    def _hold_check(self, bars: list[Bar], last: int) -> list[tuple[str, dict]]:
        """Hold entry, after the break: a completed candle holds the level, closes back under it, or none comes."""
        b = bars[last]
        broke_bar = float(self.broke["bar_t"])
        if b.t <= broke_bar:
            return []                     # the break's own candle: the hold starts after it
        level = float(self.armed["trigger"])
        waited = sum(1 for x in bars if x.t > broke_bar)
        prev = self.armed
        if b.c < level - EPS:
            why = f"closed back under the {level:.2f} high before a candle held it"
            self.armed, self.broke = None, None
            self._set(SETUP_STATE_FAILED, why)
            return [("failed", self._key_view(prev, reason=why))]
        if b.lo >= level - EPS and b.c > b.o + EPS:
            entry = round(b.c + self.p.entry_offset, 4)
            stop = round(b.lo, 4)
            risk = round(entry - stop, 4)
            why = risk_blocked(self.p, risk, slippage=False)
            if why:
                return self._disarm(prev, f"the hold candle's {why}")
            self.nth += 1
            self.triggered = {
                **prev, "entry": entry, "stop": stop, "risk": risk, "target1": self.p.target1(entry, risk),
                "triggered_at": b.t + 60, "nth": self.nth, "trigger_price": b.c, "score_bar_t": b.t,
                "half_on_entry_bar": False, "detail": {**(prev.get("detail") or {}), "hold_bar_t": b.t},
            }
            self.broke = None
            self._set(SETUP_STATE_TRIGGERED, f"held over {level:.2f}: a green candle closed at {b.c:.2f} -- "
                                             f"entry {entry:.2f}, stop {stop:.2f}")
            return [("triggered", self.view())]
        if waited >= self.p.hold_bars:
            return self._disarm(prev, f"no candle held over {level:.2f} and closed green within {self.p.hold_bars}")
        self.reason = (f"broke {level:.2f}: {waited} of {self.p.hold_bars} candles, none held over it and "
                       "closed green yet")
        return []

    def _disarm(self, prev: dict, why: str) -> list[tuple[str, dict]]:
        self.broke = None
        return super()._disarm(prev, why)

    # -- the pattern ----------------------------------------------------------
    def _find(self, bars: list[Bar], last: int) -> tuple[dict | None, tuple[dict, str] | None]:
        s, p = self.series, self.p
        level = s.hod[last]
        first_fail: tuple[dict, str] | None = None
        for m in range(p.min_consol, p.max_consol + 1):
            top = last - m
            if top < p.leg_window or s.h[top] != level:
                continue
            ctx = self._impulse(bars, top, level)
            if ctx is None:
                continue                  # no impulse into the high: not a flat top at all
            base = range(top + 1, last + 1)
            why = None
            if any(s.c[i] < level * (1 - p.band) for i in base):
                why = f"a base candle closed more than {_pct(p.band)}% under the {level:.2f} high"
            elif any(s.lo[i] < s.e[i] * (1 - p.ema_tol) for i in base):
                why = "a base candle's low broke the 9 EMA"
            if why:
                first_fail = first_fail or (ctx, why)
                continue
            return {**ctx, "bars": m, "base_low": min(s.lo[i] for i in base)}, first_fail
        return None, first_fail

    def _impulse(self, bars: list[Bar], top: int, level: float) -> dict | None:
        s, p = self.series, self.p
        low = min(s.lo[max(0, top - p.leg_window + 1):top + 1])
        if low <= 0 or level / low - 1 < p.impulse_pct:
            return None
        return {"t": bars[top].t, "high": level, "low": low, "pct": round(level / low - 1, 4), "bars": 0}

    def _impulse_high(self, bars: list[Bar], last: int) -> dict | None:
        """The last candle set a new high of day on an impulse: wait for the base."""
        s = self.series
        if last < self.p.leg_window or s.h[last] < s.hod[last] or (last > 0 and s.h[last] <= s.hod[last - 1]):
            return None
        return self._impulse(bars, last, s.h[last])

    def _stale_base(self, bars: list[Bar], last: int) -> tuple[dict, str] | None:
        """A high-of-day candle more than ``max_consol`` candles back with no higher high since."""
        s, p = self.series, self.p
        level = s.hod[last]
        top = s.hod_i[last]                   # the latest candle at the high of day
        if last - top <= p.max_consol or top < p.leg_window:
            return None
        ctx = self._impulse(bars, top, level)
        if ctx is None:
            return None
        return ctx, f"the base ran past {p.max_consol} candles without a break"
