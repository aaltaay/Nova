"""Red to green as a live state machine on one-minute bars (ADR 031).

The pre-registered P3 rule of the research screen (research/momentum/
backtest_setups.py ``find_red_to_green``, Bot-Trading-Plan section 2f):

  the open   the open of the first candle at or after ``session_start``
             (09:30 ET) is the level
  red        closes under the open, counted from the opening candle
  armed      the last candle closed under the open, at least ``min_red_bars``
             have, its MACD histogram is above zero and the next minute starts
             before ``r2g_cutoff`` (10:30): trigger = the open, entry one cent
             over, stop = the lowest low since the open, target 1 = entry + R x
             risk or the high of day, whichever is higher
  triggered  a live price over the open (entry at the bar's open when it gapped
             over)

**One try a day**, as the research: the first price through the open after a
red close with the MACD above zero either triggers or, when its risk (with the
gap entry, counting one cent of slippage) is outside the band, ends the day. A
reclaim with the MACD under zero is not a try. After ``r2g_cutoff`` nothing
arms. Pure: no I/O, no clock.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

from constants_setups import (
    SETUP_KIND_RED_TO_GREEN,
    SETUP_STATE_ARMED,
    SETUP_STATE_LEG,
    SETUP_STATE_NEAR,
    SETUP_STATE_PULLBACK,
    SETUP_STATE_TRIGGERED,
    SETUP_STATE_WATCHING,
    SETUPS_EMA_PERIOD,
    SETUPS_EMA_TOLERANCE,
    SETUPS_ENTRY_OFFSET_DOLLARS,
    SETUPS_MACD_FAST,
    SETUPS_MACD_POSITIVE,
    SETUPS_MACD_SIGNAL,
    SETUPS_MACD_SLOW,
    SETUPS_MIN_STOP_DOLLARS,
    SETUPS_NEAR_DOLLARS,
    SETUPS_NEAR_PCT,
    SETUPS_R2G_CUTOFF_ET,
    SETUPS_R2G_MIN_RED_BARS,
    SETUPS_R2G_OPEN_ET,
    SETUPS_R2G_TARGET_HOD,
    SETUPS_RISK_SLIPPAGE_DOLLARS,
    SETUPS_STOP_CAP_DOLLARS,
    SETUPS_TARGET_R,
)
from setup_scanner.bars import Bar
from setup_scanner.detector import ET, EPS, TriggerDetector, et_time, forming_levels, hhmm, risk_blocked


@dataclass(frozen=True)
class RedToGreenParams:
    session_start: str = SETUPS_R2G_OPEN_ET
    r2g_cutoff: str = SETUPS_R2G_CUTOFF_ET
    min_red_bars: int = SETUPS_R2G_MIN_RED_BARS
    target_hod: bool = SETUPS_R2G_TARGET_HOD
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
    target_r: float = SETUPS_TARGET_R
    near_dollars: float = SETUPS_NEAR_DOLLARS
    near_pct: float = SETUPS_NEAR_PCT
    max_per_symbol_day: int = 1

    @property
    def entry_cutoff(self) -> str:
        """The reclaim window's end: the base class's cutoff for a trigger."""
        return self.r2g_cutoff

    def target1(self, entry: float, risk: float, hod: float) -> float:
        t1 = entry + self.target_r * risk
        return round(max(hod, t1) if self.target_hod else t1, 4)


def _under(close: float, level: float) -> str:
    """How far under the open a close sits, in percent: "4.1"."""
    return f"{100 * (1 - close / level):.1f}".rstrip("0").rstrip(".")


def _open_index(times: list[float], at: str) -> int | None:
    """The first candle at or after ``at`` (ET) on the bars' own day (``times``: their starts, sorted)."""
    if not times:
        return None
    day = datetime.fromtimestamp(times[0], ET).date()
    h, m = hhmm(at).hour, hhmm(at).minute
    start = datetime(day.year, day.month, day.day, h, m, tzinfo=ET).timestamp()
    i = bisect_left(times, start)
    return i if i < len(times) else None


@dataclass
class RedToGreenDetector(TriggerDetector):
    p: RedToGreenParams = field(default_factory=RedToGreenParams)
    spent: bool = False                     # the day's one try is used (or the window closed)
    shadow: dict[str, Any] | None = None     # red and MACD above zero, but the risk is out of the band

    FIRST_KIND: ClassVar[str] = SETUP_KIND_RED_TO_GREEN
    SECOND_KIND: ClassVar[str | None] = None

    # -- bar close ---------------------------------------------------------
    def on_bars(self, bars: list[Bar]) -> list[tuple[str, dict]]:
        s, p = self.series, self.p
        s.update(bars)
        self.forming = None
        if self.state == SETUP_STATE_TRIGGERED or self.spent:
            return []
        prev = self.armed if self.state in (SETUP_STATE_ARMED, SETUP_STATE_NEAR) else None
        last = len(bars) - 1
        k0 = _open_index(s.t, p.session_start)
        if k0 is None or k0 > last:
            self.leg = None
            self._set(SETUP_STATE_WATCHING, f"waits for the {p.session_start} open")
            return []
        level = s.o[k0]
        low = min(s.lo[k0:last + 1])
        red = sum(1 for i in range(k0, last + 1) if s.c[i] < level - EPS)
        self.leg = {"t": bars[k0].t, "high": level, "low": low, "pct": round(s.c[last] / level - 1, 4) if level else 0.0,
                    "bars": red}
        events: list[tuple[str, dict]] = []
        if et_time(bars[last].t + 60) >= hhmm(p.r2g_cutoff):
            self.spent, self.shadow = True, None
            why = f"the reclaim window closed at {p.r2g_cutoff} -- no try left today"
            self.armed = None
            self._set(SETUP_STATE_WATCHING, why)
            if prev is not None:
                events.append(("disarmed", self._key_view(prev, reason=why)))
            return events
        if s.c[last] >= level - EPS:
            return self._watch(prev, f"at or over the {level:.2f} open -- waits for a close under it")
        if red < p.min_red_bars:
            self.armed, self.shadow = None, None
            self.forming = self._provisional(level, low, red, last)
            self._set(SETUP_STATE_LEG, f"{red} close under the {level:.2f} open -- the rule asks {p.min_red_bars}")
            if prev is not None:
                events.append(("disarmed", self._key_view(prev, reason="not enough red closes")))
            return events
        entry = round(level + p.entry_offset, 4)
        risk = round(entry - low, 4)
        setup = {
            "leg_t": bars[k0].t, "trigger": round(level, 4), "entry": entry, "stop": round(low, 4), "risk": risk,
            "target1": p.target1(entry, risk, s.hod[last]), "pullback_bars": red, "leg_high": level,
            "leg_low": low, "leg_pct": self.leg["pct"], "armed_bar_t": bars[last].t,
            "armed_at": (prev or {}).get("armed_at") or bars[last].t + 60, "kind": self.kind_now(),
            "detail": {"open": round(level, 4), "open_t": bars[k0].t, "red_bars": red, "hod": s.hod[last]},
        }
        under = _under(s.c[last], level)
        if p.macd_positive and s.hist[last] <= 0:
            self.shadow = None
            self.forming = forming_levels(level, entry, low, setup["target1"], bars=red,
                                          blocked="MACD below zero -- a reclaim now is not a try")
            return self._block(prev, f"red, {under}% under the {level:.2f} open; MACD below zero -- "
                                     "a reclaim now is not a try")
        why = risk_blocked(p, risk)
        if why:
            self.shadow = setup
            self.forming = forming_levels(level, entry, low, setup["target1"], bars=red, blocked=why)
            return self._block(prev, f"red, {under}% under the {level:.2f} open; {why} -- a reclaim now "
                                     "spends the day's one try")
        self.shadow = None
        self.armed = setup
        self._set(SETUP_STATE_ARMED, f"red, {under}% under the {level:.2f} open: trigger {level:.2f}, "
                                     f"stop {low:.2f}, risk {risk:.2f}")
        return events + self.arm_events(prev)

    def _provisional(self, level: float, low: float, red: int, last: int) -> dict[str, Any]:
        """Fewer red closes than the rule asks: the reclaim's levels if it counted now (ADR 035)."""
        s, p = self.series, self.p
        entry = round(level + p.entry_offset, 4)
        risk = round(entry - low, 4)
        need = p.min_red_bars - red
        blocked = ("MACD below zero -- a reclaim now is not a try" if p.macd_positive and s.hist[last] <= 0
                   else risk_blocked(p, risk))
        return forming_levels(level, entry, low, p.target1(entry, risk, s.hod[last]), bars=red, blocked=blocked,
                              waiting=f"{need} more close{'' if need == 1 else 's'} under the open")

    def _watch(self, prev: dict | None, why: str) -> list[tuple[str, dict]]:
        self.armed, self.shadow = None, None
        self._set(SETUP_STATE_WATCHING, why)
        return [("disarmed", self._key_view(prev, reason=why))] if prev is not None else []

    def _block(self, prev: dict | None, why: str) -> list[tuple[str, dict]]:
        self.armed = None
        self._set(SETUP_STATE_PULLBACK, why)
        return [("disarmed", self._key_view(prev, reason=why))] if prev is not None else []

    # -- live price -------------------------------------------------------
    def on_price(self, price: float, ts: float, *, bar_open: float | None = None) -> list[tuple[str, dict]]:
        if self.spent or self.state == SETUP_STATE_TRIGGERED:
            self.last_price = price
            return []
        if self.armed is None and self.shadow is not None:
            return self._shadow_try(price, ts, bar_open)
        events = super().on_price(price, ts, bar_open=bar_open)
        for name, view in events:
            if name == "disarmed":        # a gap over the band, or the window closed: the try is spent
                self.spent = True
                self._set(SETUP_STATE_WATCHING, f"{view.get('reason')} -- the day's one try is spent")
        return events

    def _shadow_try(self, price: float, ts: float, bar_open: float | None) -> list[tuple[str, dict]]:
        """The risk was out of the band at the close; a gap can still bring it in (the research's entry)."""
        self.last_price = price
        setup = self.shadow
        if price <= setup["trigger"] + EPS:
            return []
        self.shadow = None
        self.spent = True
        if et_time(ts) >= hhmm(self.p.r2g_cutoff):
            self._set(SETUP_STATE_WATCHING, f"the reclaim window closed at {self.p.r2g_cutoff}")
            return []
        entry = round(max(setup["entry"], bar_open if bar_open is not None else price), 4)
        risk = round(entry - setup["stop"], 4)
        why = risk_blocked(self.p, risk)
        if why:
            self._set(SETUP_STATE_WATCHING, f"reclaimed the {setup['trigger']:.2f} open with {why} -- "
                                            "the day's one try is spent")
            return []
        hod = float((setup.get("detail") or {}).get("hod") or 0)
        self.armed = {**setup, "entry": entry, "risk": risk, "target1": self.p.target1(entry, risk, hod)}
        self._set(SETUP_STATE_ARMED, self.armed_reason())
        armed = [("armed", self.view())]
        self.nth += 1
        self.triggered = {**self.armed, "triggered_at": ts, "nth": self.nth, "trigger_price": price}
        self._set(SETUP_STATE_TRIGGERED, f"traded {price:.2f} over the {setup['trigger']:.2f} open")
        return armed + [("triggered", self.view())]
