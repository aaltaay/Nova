"""Gap and Go as a live state machine on one-minute bars (ADR 031 amendment, 2026-10-02).

The research's pre-registered A2 rule (research/orb/backtest_gng.py, rules of 2026-09-22),
on the names the scanner follows:

  the level  the pre-market high: the highest high of the day's candles before
             ``session_start`` (09:30 ET)
  the open   the first price at or after 09:30 (the opening minute's open). An open at
             or over the pre-market high is a gap through it: the rule skips the day
  armed      from the open until ``entry_cutoff`` (10:00): trigger = the pre-market
             high, entry one cent over it, stop ``min(stop_cents, stop_pct x entry)``
             under the entry, target 1 = entry + R x risk
  triggered  a live price over the pre-market high (entry at the bar's open when it
             gapped over; the stop moves with the entry, as the research's did)

**One try a day.** A gap through the level at the open, the window closing, or a break
the scanner did not see live (a completed candle over the level with no trigger -- a
restart's seed) ends the day. Before the open the levels are drawn as forming. The
research has no MACD rule; ``macd_positive`` is off by default and, when a template turns
it on, arming waits for the last candle's histogram above zero. Pure: no I/O, no clock.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

from constants_setups import (
    SETUP_KIND_GAP_AND_GO,
    SETUP_STATE_ARMED,
    SETUP_STATE_NEAR,
    SETUP_STATE_PULLBACK,
    SETUP_STATE_TRIGGERED,
    SETUP_STATE_WATCHING,
    SETUPS_EMA_PERIOD,
    SETUPS_ENTRY_OFFSET_DOLLARS,
    SETUPS_GNG_CUTOFF_ET,
    SETUPS_GNG_MACD_POSITIVE,
    SETUPS_GNG_OPEN_ET,
    SETUPS_GNG_STOP_CENTS,
    SETUPS_GNG_STOP_PCT,
    SETUPS_MACD_FAST,
    SETUPS_MACD_SIGNAL,
    SETUPS_MACD_SLOW,
    SETUPS_MIN_STOP_DOLLARS,
    SETUPS_NEAR_DOLLARS,
    SETUPS_NEAR_PCT,
    SETUPS_RISK_SLIPPAGE_DOLLARS,
    SETUPS_TARGET_R,
)
from setup_scanner.bars import Bar
from setup_scanner.detector import ET, EPS, TriggerDetector, et_time, forming_levels, hhmm


@dataclass(frozen=True)
class GapAndGoParams:
    session_start: str = SETUPS_GNG_OPEN_ET
    entry_cutoff: str = SETUPS_GNG_CUTOFF_ET
    stop_cents: float = SETUPS_GNG_STOP_CENTS
    stop_pct: float = SETUPS_GNG_STOP_PCT
    ema_period: int = SETUPS_EMA_PERIOD
    macd_positive: bool = SETUPS_GNG_MACD_POSITIVE
    macd_fast: int = SETUPS_MACD_FAST
    macd_slow: int = SETUPS_MACD_SLOW
    macd_signal: int = SETUPS_MACD_SIGNAL
    min_stop: float = SETUPS_MIN_STOP_DOLLARS
    entry_offset: float = SETUPS_ENTRY_OFFSET_DOLLARS
    risk_slippage: float = SETUPS_RISK_SLIPPAGE_DOLLARS
    target_r: float = SETUPS_TARGET_R
    near_dollars: float = SETUPS_NEAR_DOLLARS
    near_pct: float = SETUPS_NEAR_PCT
    max_per_symbol_day: int = 1

    @property
    def stop_cap(self) -> float:
        """The largest risk a share the rule can give (a plan names it)."""
        return self.stop_cents

    def stop_distance(self, entry: float) -> float:
        return round(min(self.stop_cents, self.stop_pct * entry), 4)

    def target1(self, entry: float, risk: float) -> float:
        return round(entry + self.target_r * risk, 4)


def _open_ts(times: list[float], at: str) -> float | None:
    """Epoch seconds of ``at`` (ET) on the bars' own day."""
    if not times:
        return None
    day = datetime.fromtimestamp(times[0], ET).date()
    t = hhmm(at)
    return datetime(day.year, day.month, day.day, t.hour, t.minute, tzinfo=ET).timestamp()


def _hm(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M")


@dataclass
class GapAndGoDetector(TriggerDetector):
    p: GapAndGoParams = field(default_factory=GapAndGoParams)
    spent: bool = False                  # the day's one try is used (or skipped)
    pm_high: float | None = None
    pm_high_t: float | None = None
    open_px: float | None = None
    open_t: float | None = None

    FIRST_KIND: ClassVar[str] = SETUP_KIND_GAP_AND_GO
    SECOND_KIND: ClassVar[str | None] = None

    # -- levels -------------------------------------------------------------
    def _levels(self, pmh: float) -> dict[str, float]:
        entry = round(pmh + self.p.entry_offset, 4)
        risk = self.p.stop_distance(entry)
        return {"trigger": round(pmh, 4), "entry": entry, "stop": round(entry - risk, 4), "risk": risk,
                "target1": self.p.target1(entry, risk)}

    def _leg(self) -> dict[str, Any] | None:
        if self.pm_high is None:
            return None
        lv = self._levels(self.pm_high)
        gap = round(self.open_px / self.pm_high - 1, 4) if self.open_px else 0.0
        return {"t": self.pm_high_t, "high": self.pm_high, "low": lv["stop"], "pct": gap, "bars": 0}

    def _setup(self, at: float) -> dict[str, Any]:
        lv = self._levels(float(self.pm_high))
        return {
            "leg_t": self.pm_high_t, **lv, "pullback_bars": 0, "leg_high": self.pm_high, "leg_low": lv["stop"],
            "leg_pct": (self.leg or {}).get("pct", 0.0), "armed_bar_t": at - 60, "armed_at": at,
            "kind": self.kind_now(),
            "detail": {"pm_high": self.pm_high, "pm_high_t": self.pm_high_t, "open": self.open_px,
                       "open_t": self.open_t, "stop_rule": f"min({self.p.stop_cents:.2f}, "
                                                           f"{100 * self.p.stop_pct:g}% of the entry)"},
        }

    # -- bar close ---------------------------------------------------------
    def on_bars(self, bars: list[Bar]) -> list[tuple[str, dict]]:
        s, p = self.series, self.p
        s.update(bars)
        self.forming = None
        if self.state == SETUP_STATE_TRIGGERED or self.spent or not bars:
            return []
        open_at = _open_ts(s.t, p.session_start)
        k0 = bisect_left(s.t, open_at) if open_at is not None else len(s.t)
        if k0 == 0:
            self._set(SETUP_STATE_WATCHING, "no pre-market trade on record -- no pre-market high to break")
            return []
        if self.open_px is None:          # the open is not decided yet: the pre-market high may still grow
            hi = max(range(k0), key=lambda i: (s.h[i], i))
            self.pm_high, self.pm_high_t = s.h[hi], bars[hi].t
        self.leg = self._leg()
        last = len(bars) - 1
        if k0 > last:                     # before the open: draw the levels it would arm with
            lv = self._levels(float(self.pm_high))
            self.forming = forming_levels(lv["trigger"], lv["entry"], lv["stop"], lv["target1"], bars=0,
                                          waiting=f"waits for the {p.session_start} open")
            self._set(SETUP_STATE_WATCHING, f"pre-market high {self.pm_high:.2f} -- from the {p.session_start} "
                                            f"open, a price over it until {p.entry_cutoff}")
            return []
        if self.open_px is None:          # no live price saw the open (a seed or a replay): its candle did
            events = self._decide_open(s.o[k0], bars[k0].t)
            if self.spent or self.state == SETUP_STATE_TRIGGERED:
                return events
        else:
            events = []
        broke = next((i for i in range(k0, last + 1) if s.h[i] > float(self.pm_high) + EPS), None)
        if broke is not None:             # a break no live price triggered: the try is gone
            return events + self._spend(f"the {self.pm_high:.2f} pre-market high broke at {_hm(bars[broke].t)} "
                                        "before the setup could trigger on it")
        if et_time(bars[last].t + 60) >= hhmm(p.entry_cutoff):
            return events + self._spend(f"no break of the {self.pm_high:.2f} pre-market high by {p.entry_cutoff}")
        if self.armed is None:
            events += self._try_arm(bars[last].t + 60)
        return events

    def _decide_open(self, open_px: float, ts: float) -> list[tuple[str, dict]]:
        self.open_px, self.open_t = round(float(open_px), 4), ts
        self.leg = self._leg()
        if self.open_px >= float(self.pm_high) - EPS:
            return self._spend(f"opened at {self.open_px:.2f}, at or over the {self.pm_high:.2f} pre-market "
                               "high -- the rule skips a gap through it")
        return self._try_arm(ts)

    def _try_arm(self, at: float) -> list[tuple[str, dict]]:
        p, s = self.p, self.series
        if et_time(at) >= hhmm(p.entry_cutoff):
            return self._spend(f"the window closed at {p.entry_cutoff} before the open")
        setup = self._setup(at)
        if setup["risk"] + p.risk_slippage < p.min_stop - EPS:
            return self._spend(f"risk {setup['risk']:.2f} is under {p.min_stop:.2f}")
        if p.macd_positive and s.hist and s.hist[-1] <= 0:
            self.forming = forming_levels(setup["trigger"], setup["entry"], setup["stop"], setup["target1"], bars=0,
                                          blocked="MACD below zero -- waits for it to turn up")
            self._set(SETUP_STATE_PULLBACK, f"opened {self.open_px:.2f} under the {self.pm_high:.2f} pre-market "
                                            "high; MACD below zero -- waits for it to turn up")
            return []
        self.armed = setup
        self._set(SETUP_STATE_ARMED, f"opened {self.open_px:.2f} under the {self.pm_high:.2f} pre-market high: "
                                     f"trigger {setup['trigger']:.2f}, stop {setup['stop']:.2f}, "
                                     f"risk {setup['risk']:.2f}")
        return self.arm_events(None)

    def _spend(self, why: str) -> list[tuple[str, dict]]:
        prev = self.armed if self.state in (SETUP_STATE_ARMED, SETUP_STATE_NEAR) else None
        self.spent, self.armed = True, None
        self._set(SETUP_STATE_WATCHING, why)
        return [("disarmed", self._key_view(prev, reason=why))] if prev is not None else []

    # -- live price -------------------------------------------------------
    def on_price(self, price: float, ts: float, *, bar_open: float | None = None) -> list[tuple[str, dict]]:
        self.last_price = price
        if self.spent or self.state == SETUP_STATE_TRIGGERED or self.pm_high is None:
            return []
        if et_time(ts) < hhmm(self.p.session_start):
            return []
        events: list[tuple[str, dict]] = []
        if self.open_px is None:
            events = self._decide_open(bar_open if bar_open is not None else price, ts)
        if self.armed is None or self.state not in (SETUP_STATE_ARMED, SETUP_STATE_NEAR):
            return events
        trig = float(self.armed["trigger"])
        if price <= trig + EPS:
            return events + self._near_check(price)
        if et_time(ts) >= hhmm(self.cutoff()):
            return events + self._spend(f"the window closed at {self.p.entry_cutoff} before the break")
        entry = round(max(self.armed["entry"], bar_open if bar_open is not None else price), 4)
        risk = self.p.stop_distance(entry)
        self.nth += 1
        self.triggered = {**self.armed, "entry": entry, "stop": round(entry - risk, 4), "risk": risk,
                          "target1": self.p.target1(entry, risk), "triggered_at": ts, "nth": self.nth,
                          "trigger_price": price}
        self._set(SETUP_STATE_TRIGGERED, f"traded {price:.2f} over the {trig:.2f} pre-market high")
        return events + [("triggered", self.view())]
