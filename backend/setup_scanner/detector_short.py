"""What the five short setups share (ADR 049): the trigger read downward.

A long setup's trigger is a high: a live price over it buys at the entry one cent over (``detector.py``). A
short's is a low, and its entry is one cent under it: a live price at or under the entry sells -- at the
minute's open when it gapped under, and the setup is disarmed when that gap pushes the risk over the cap (the
long rule mirrored). A print under the trigger but over the entry (a sub-penny trade) is still near: the sell
entry never traded (PR #789 review). Its stop is over the entry, its target 1 under it (entry - target R x risk), and its near
band over the trigger. The SSR bounce short reads the long way up -- its entry rests at the level and a price
over it fills it -- so it keeps the long trigger (``ssr_bounce.py``).

A short detector also reads the host's ``context`` (``{prior_close, ssr_yesterday}``, set by the lane before
each bar) for its SSR; the lane stamps every row with its setup's side. Pure: no I/O, no clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from constants_bot import SIDE_SHORT
from constants_setups import SETUP_STATE_ARMED, SETUP_STATE_NEAR, SETUP_STATE_TRIGGERED
from constants_short_setups import SETUPS_SSR_OFF, SETUPS_SSR_ON, SETUPS_SSR_UNKNOWN
from constants_shorts import SSR_TRIGGER_FRACTION
from setup_scanner.detector import EPS, TriggerDetector, et_time, hhmm, stop_cap


def short_levels(trigger: float, entry: float, stop: float, target1: float, *, bars: int,
                 blocked: str | None = None, waiting: str | None = None) -> dict[str, Any]:
    """The levels a forming short would arm with (ADR 036): its risk is the stop over the entry."""
    return {"trigger": round(trigger, 4), "entry": round(entry, 4), "stop": round(stop, 4),
            "risk": round(stop - entry, 4), "target1": round(target1, 4), "bars": int(bars),
            "blocked": blocked, "waiting": waiting}


def short_risk_blocked(p: Any, risk: float, *, entry: float | None = None) -> str | None:
    """Why a short's ``risk`` (stop minus entry) is outside the band, counting ``risk_slippage``; or None."""
    extra = p.risk_slippage
    shown = f" (+{extra:.2f} slippage)" if extra else ""
    cap = stop_cap(p, entry)
    if risk + extra > cap + EPS:
        return f"risk {risk:.2f}{shown} is over {cap:.2f}"
    if risk + extra < p.min_stop - EPS:
        return f"risk {risk:.2f}{shown} is under {p.min_stop:.2f}"
    return None


def short_target(entry: float, risk: float, target_r: float) -> float:
    """Cover at target R: entry - R x risk (ADR 049: no leg-or-R variant)."""
    return round(entry - target_r * risk, 4)


def ssr_today(lows: list[float], context: dict[str, Any] | None) -> str:
    """SSR from the lane's own bars and the host's facts (ADR 049 step 4): ``on`` when a bar's low today
    reached 90% of the prior close or yesterday's SSR carries, ``off`` when the prior close and yesterday are
    known and neither holds, else ``unknown`` (which the door prices as on)."""
    ctx = context or {}
    prior = ctx.get("prior_close")
    yesterday = ctx.get("ssr_yesterday")
    try:
        prior = float(prior) if prior is not None else None
    except (TypeError, ValueError):
        prior = None
    if yesterday is True:
        return SETUPS_SSR_ON
    if prior is not None and prior > 0 and lows and min(lows) <= prior * (1.0 - SSR_TRIGGER_FRACTION) + EPS:
        return SETUPS_SSR_ON
    if prior is not None and prior > 0 and yesterday is False:
        return SETUPS_SSR_OFF
    return SETUPS_SSR_UNKNOWN


@dataclass
class ShortTriggerDetector(TriggerDetector):
    """A short setup's state: the long ladder, the trigger read downward."""

    context: dict[str, Any] | None = field(default=None, repr=False)

    SIDE: ClassVar[str] = SIDE_SHORT
    TRIGGER_UP: ClassVar[bool] = False

    # -- live price ---------------------------------------------------------
    def on_price(self, price: float, ts: float, *, bar_open: float | None = None) -> list[tuple[str, dict]]:
        self.last_price = price
        if self.armed is None or self.state not in (SETUP_STATE_ARMED, SETUP_STATE_NEAR):
            return []
        trig = self.armed["trigger"]
        if price > self.armed["entry"] + EPS:
            return self._near_check(price)
        prev = self.armed
        if et_time(ts) >= hhmm(self.cutoff()):
            return self._disarm(prev, "the entry window closed before the trigger")
        entry = round(min(prev["entry"], bar_open if bar_open is not None else price), 4)
        cap = stop_cap(self.p, entry)
        if prev["stop"] - entry + self.p.risk_slippage > cap + EPS:
            return self._disarm(prev, f"gapped under the trigger to {entry:.2f}: risk over {cap:.2f}")
        self.nth += 1
        self.triggered = {**prev, "entry": entry, "triggered_at": ts, "nth": self.nth, "trigger_price": price}
        self._set(SETUP_STATE_TRIGGERED, f"traded {price:.2f} under the {trig:.2f} trigger")
        return [("triggered", self.view())]

    def _near_check(self, price: float) -> list[tuple[str, dict]]:
        if self.armed is None:
            return []
        trig = self.armed["trigger"]
        band = max(self.p.near_dollars, self.p.near_pct * price)
        over = max(0.0, price - trig)          # under the trigger but over the entry reads as at it
        if over <= band:
            if self.state != SETUP_STATE_NEAR:
                self._set(SETUP_STATE_NEAR, f"{over:.2f} over the {trig:.2f} trigger -- read the tape")
                return [("near", self.view())]
        elif self.state == SETUP_STATE_NEAR:
            self._set(SETUP_STATE_ARMED, self.armed_reason())
        return []

    def armed_reason(self) -> str:
        a = self.armed or {}
        return f"short under {a.get('trigger', 0):.2f}, buy stop {a.get('stop', 0):.2f}, risk {a.get('risk', 0):.2f}"

    def ssr(self) -> str:
        """SSR now, from this symbol's bars today, the live price it was last fed (the trade that triggers it may be
        the first at 90% of the prior close: PR #789 review) and the host's context."""
        lows = [*self.series.lo, self.last_price] if self.last_price is not None else self.series.lo
        return ssr_today(lows, self.context)
