"""The SSR bounce short (ADR 049 section 9, pre-registered; its step 4 section names the CHOSEN readings).

Under SSR a short may sell only above the bid, so this setup sells into a bounce instead of on a break. After
every completed bar:

  ssr        the stock is under SSR today -- a bar's low reached 90% of the prior close, or yesterday's SSR
             carries (``detector_short.ssr_today``) -- and known on: an unknown SSR is not an SSR stock
  drop       the candle that made the low of day: a new low, at least ``drop_pct`` under the highest high of
             the ``drop_lookback`` candles before it
  bounce     the ``bounce_greens`` candles right after it are green; no candle since went under the low
  level      the nearest of these over the price: the SSR trigger (90% of the prior close), the next half or
             whole dollar, the last lower high (the highest high from the previous low of day's candle to this
             low), VWAP
  armed      the price (the last close) under VWAP and within ``arm_pct`` under the level: the short rests one
             cent under the level -- trigger and entry both -- with its buy stop ``stop_pct`` over the entry,
             at least ``stop_min``; the next minute inside the window (09:35-15:50); risk inside the band
  triggered  a live price over the entry fills it, at the entry (a resting limit, never re-priced)
  cancelled  a bar's low under the drop's low, a bar's close over the level, or ``cancel_min`` minutes after
             it armed -- it fails, and a new drop and bounce may arm again (two a day)

The armed levels never move: a resting order is cancelled, never re-priced. Every number is an
``SsrBounceParams`` field a template sets (ADR 029). Pure: no I/O, no clock.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, ClassVar

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
    SETUP_KIND_SECOND_SSR_BOUNCE,
    SETUP_KIND_SSR_BOUNCE,
    SETUPS_SSR_ON,
    SHORT_ENTRY_OFFSET_DOLLARS,
    SHORT_MAX_PER_SYMBOL_DAY,
    SHORT_SSR_ARM_PCT,
    SHORT_SSR_BOUNCE_CUTOFF_ET,
    SHORT_SSR_BOUNCE_GREENS,
    SHORT_SSR_CANCEL_MIN,
    SHORT_SSR_DROP_LOOKBACK,
    SHORT_SSR_DROP_PCT,
    SHORT_SSR_ROUND_STEP,
    SHORT_SSR_STOP_MIN_DOLLARS,
    SHORT_SSR_STOP_PCT,
    SHORT_WINDOW_START_ET,
)
from constants_shorts import SSR_TRIGGER_FRACTION
from setup_scanner.bars import Bar
from setup_scanner.detector import EPS, TriggerDetector, et_time, hhmm, window_blocked
from setup_scanner.detector_short import ShortTriggerDetector, short_levels, short_risk_blocked, short_target


@dataclass(frozen=True)
class SsrBounceParams:
    drop_pct: float = SHORT_SSR_DROP_PCT
    drop_lookback: int = SHORT_SSR_DROP_LOOKBACK
    bounce_greens: int = SHORT_SSR_BOUNCE_GREENS
    arm_pct: float = SHORT_SSR_ARM_PCT
    cancel_min: int = SHORT_SSR_CANCEL_MIN
    stop_pct: float = SHORT_SSR_STOP_PCT
    stop_min: float = SHORT_SSR_STOP_MIN_DOLLARS
    round_step: float = SHORT_SSR_ROUND_STEP
    ema_period: int = SETUPS_EMA_PERIOD
    macd_fast: int = SETUPS_MACD_FAST
    macd_slow: int = SETUPS_MACD_SLOW
    macd_signal: int = SETUPS_MACD_SIGNAL
    stop_cap: float = SETUPS_STOP_CAP_DOLLARS
    bar_sec: int = SETUPS_BAR_SEC
    min_stop: float = SETUPS_MIN_STOP_DOLLARS
    entry_offset: float = SHORT_ENTRY_OFFSET_DOLLARS
    risk_slippage: float = SETUPS_RISK_SLIPPAGE_DOLLARS
    target_r: float = SETUPS_TARGET_R
    near_dollars: float = SETUPS_NEAR_DOLLARS
    near_pct: float = SETUPS_NEAR_PCT
    session_start: str = SHORT_WINDOW_START_ET
    entry_cutoff: str = SHORT_SSR_BOUNCE_CUTOFF_ET
    max_per_symbol_day: int = SHORT_MAX_PER_SYMBOL_DAY


def next_round(price: float, step: float) -> float:
    """The next half or whole dollar strictly over ``price``."""
    n = math.floor(price / step + 1e-9) + 1
    return round(n * step, 4)


@dataclass
class SsrBounceDetector(ShortTriggerDetector):
    p: SsrBounceParams = field(default_factory=SsrBounceParams)

    FIRST_KIND: ClassVar[str] = SETUP_KIND_SSR_BOUNCE
    SECOND_KIND: ClassVar[str | None] = SETUP_KIND_SECOND_SSR_BOUNCE
    TRIGGER_UP: ClassVar[bool] = True       # its entry rests over the price: a buyer lifting into it fills it

    # -- bar close ---------------------------------------------------------
    def on_bars(self, bars: list[Bar]) -> list[tuple[str, dict]]:
        n = len(bars)
        self.series.update(bars)
        self.forming = None
        need = self.p.drop_lookback + self.p.bounce_greens + 1
        if n < need:
            if self.state == SETUP_STATE_WATCHING:
                self.reason = f"warming up ({n}/{need} bars)"
            return []
        if self.nth >= self.p.max_per_symbol_day:
            return []
        s, p = self.series, self.p
        last = n - 1
        prev = self.armed if self.state in (SETUP_STATE_ARMED, SETUP_STATE_NEAR) else None
        d_i = s.lod_i[last]
        if self.state == SETUP_STATE_TRIGGERED and s.t[d_i] == self.triggered.get("leg_t"):
            return []                     # the trade is on; a new setup needs a new drop
        if prev is not None:
            cancel = self._cancel_on_bar(prev, bars, last)
            if cancel is None:
                return []                 # resting: the levels never move
            return self._fail(prev, cancel)
        ssr = self.ssr()
        if ssr != SETUPS_SSR_ON:
            self.leg = None
            why = ("SSR is off: the SSR bounce shorts SSR stocks only" if ssr == "off" else
                   "SSR is not known (no prior close): the SSR bounce shorts SSR stocks only")
            self._set(SETUP_STATE_WATCHING, why)
            return []
        drop = self._drop(bars, d_i)
        if drop is None:
            self.leg = None
            self._set(SETUP_STATE_WATCHING, f"no {100 * p.drop_pct:.0f}% drop to a new low of day")
            return []
        if last - d_i < p.bounce_greens:
            return self._leg(drop, f"new low {drop['low']:.2f} after a {100 * drop['pct']:.1f}% drop -- wait for "
                                   f"{p.bounce_greens} green candles")
        greens = range(d_i + 1, d_i + 1 + p.bounce_greens)
        if not all(s.c[i] > s.o[i] + EPS for i in greens):
            self.leg = drop
            self._set(SETUP_STATE_WATCHING, f"the bounce off {drop['low']:.2f} was not {p.bounce_greens} green "
                                            "candles")
            return []
        price = s.c[last]
        vw = s.vw[last]
        if vw is None or price >= vw - EPS:
            return self._leg(drop, "bouncing over VWAP -- the SSR bounce shorts under it")
        level, kind = self._level(price, d_i, last)
        if level is None:
            return self._leg(drop, "no level over the price")
        if (level - price) / level > p.arm_pct + EPS:
            return self._leg(drop, f"bouncing at {price:.2f}, {100 * (level - price) / level:.1f}% under the "
                                   f"{level:.2f} level -- the short rests within {100 * p.arm_pct:.0f}%")
        return self._arm(bars, last, drop, level, kind)

    def _cancel_on_bar(self, prev: dict, bars: list[Bar], last: int) -> str | None:
        s = self.series
        detail = prev.get("detail") or {}
        if s.lo[last] < float(detail.get("drop_low", prev["leg_low"])) - EPS:
            return "the bounce made a new low"
        if s.c[last] > float(detail.get("level", prev["trigger"])) + EPS:
            return "a candle closed over the level"
        if bars[last].t + self.p.bar_sec >= float(detail.get("cancel_at") or 9e18) - EPS:
            return f"{self.p.cancel_min} minutes passed without a fill"
        return None

    def _drop(self, bars: list[Bar], d_i: int) -> dict[str, Any] | None:
        s, p = self.series, self.p
        if d_i < p.drop_lookback or d_i < 1:
            return None
        low = s.lo[d_i]
        if low >= s.lod[d_i - 1] - EPS:
            return None                   # not a new low of day
        high = max(s.h[d_i - p.drop_lookback:d_i])
        if high <= 0 or (high - low) / high < p.drop_pct - EPS:
            return None
        return {"t": bars[d_i].t, "high": high, "low": low, "pct": round((high - low) / high, 4), "bars": 0}

    def _level(self, price: float, d_i: int, last: int) -> tuple[float | None, str | None]:
        s, p = self.series, self.p
        prior = (self.context or {}).get("prior_close")
        cands: list[tuple[float, str]] = []
        if prior:
            cands.append((round(float(prior) * (1.0 - SSR_TRIGGER_FRACTION), 4), "ssr_trigger"))
        cands.append((next_round(price, p.round_step), "round"))
        prev_low_i = s.lod_i[d_i - 1]
        cands.append((max(s.h[prev_low_i:d_i]), "lower_high"))
        vw = s.vw[last]
        if vw is not None:
            cands.append((round(float(vw), 4), "vwap"))
        over = [(lvl, kind) for lvl, kind in cands if lvl > price + EPS]
        if not over:
            return None, None
        return min(over)

    def _arm(self, bars: list[Bar], last: int, drop: dict, level: float, kind: str) -> list[tuple[str, dict]]:
        p = self.p
        entry = round(level - p.entry_offset, 4)
        stop = round(entry + max(p.stop_pct * entry, p.stop_min), 4)
        risk = round(stop - entry, 4)
        target = short_target(entry, risk, p.target_r)
        self.leg = drop
        blocked = window_blocked(p, bars[last].t + p.bar_sec) or short_risk_blocked(p, risk, entry=entry)
        if blocked:
            self.armed = None
            self.forming = short_levels(entry, entry, stop, target, bars=last - (self.series.lod_i[last]),
                                        blocked=blocked)
            self._set(SETUP_STATE_LEG, f"a short at {entry:.2f} under the {level:.2f} level, but {blocked}")
            return []
        armed_at = bars[last].t + p.bar_sec
        self.armed = {
            "leg_t": drop["t"], "trigger": entry, "entry": entry, "stop": stop, "risk": risk, "target1": target,
            "pullback_bars": last - self.series.lod_i[last], "leg_high": drop["high"], "leg_low": drop["low"],
            "leg_pct": drop["pct"], "armed_bar_t": bars[last].t, "armed_at": armed_at, "kind": self.kind_now(),
            "detail": {"level": level, "level_kind": kind, "drop_low": drop["low"], "ssr": self.ssr(),
                       "cancel_at": armed_at + p.cancel_min * 60},
        }
        self._set(SETUP_STATE_ARMED, self.armed_reason())
        return self.arm_events(None)

    def _leg(self, drop: dict, why: str) -> list[tuple[str, dict]]:
        self.leg = drop
        was = self.state
        self._set(SETUP_STATE_LEG, why)
        return [("leg", self.view())] if was != SETUP_STATE_LEG else []

    def _fail(self, prev: dict, why: str) -> list[tuple[str, dict]]:
        self.armed = None
        self._set(SETUP_STATE_FAILED, why)
        return [("failed", self._key_view(prev, reason=why))]

    # -- live price: the long trigger, the entry fixed ------------------------------
    def on_price(self, price: float, ts: float, *, bar_open: float | None = None) -> list[tuple[str, dict]]:
        self.last_price = price
        if self.armed is None or self.state not in (SETUP_STATE_ARMED, SETUP_STATE_NEAR):
            return []
        prev = self.armed
        detail = prev.get("detail") or {}
        if ts >= float(detail.get("cancel_at") or 9e18) - EPS:
            return self._fail(prev, f"{self.p.cancel_min} minutes passed without a fill")
        if price < float(detail.get("drop_low", prev["leg_low"])) - EPS:
            return self._fail(prev, "the bounce made a new low")
        trig = prev["trigger"]
        if price <= trig + EPS:
            return TriggerDetector._near_check(self, price)
        if et_time(ts) >= hhmm(self.cutoff()):
            return self._disarm(prev, "the entry window closed before a buyer lifted it")
        self.nth += 1
        self.triggered = {**prev, "triggered_at": ts, "nth": self.nth, "trigger_price": price}
        self._set(SETUP_STATE_TRIGGERED, f"a buyer lifted it at {price:.2f}: shorted at {prev['entry']:.2f}")
        return [("triggered", self.view())]

    def armed_reason(self) -> str:
        a = self.armed or {}
        level = (a.get("detail") or {}).get("level", 0)
        return f"short rests at {a.get('entry', 0):.2f} under the {level:.2f} level, buy stop {a.get('stop', 0):.2f}"
