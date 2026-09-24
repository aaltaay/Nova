"""What every setup detector shares (ADR 022, ADR 031): the armed setup, the near
band, the trigger on a live price, and the view the lane reads.

A detector is one symbol's state on one-minute bars for one setup. The engine
calls ``on_bars`` after each completed bar (the whole day so far, oldest first)
and ``on_price`` on every live price in between; both return events --
``(name, view)`` pairs the lane turns into scoreboard rows:

  leg        a pattern is forming (the leg, the pole, a new high of day)
  armed      the trigger, entry, stop and target are known
  rearmed    the same setup at new levels
  near       price within the near band of the trigger: read the tape
  triggered  a live price over the trigger (a flat-top hold: a candle's close)
  failed     the forming setup broke a rule
  disarmed   an armed setup stopped being one

The states are one ladder for every setup: ``watching``, ``leg`` (forming),
``pullback`` (formed, but one rule blocks it -- the reason says which),
``armed``, ``near``, ``triggered``, ``failed``. The trigger on a live price is
the first pullback's (ADR 022): entry at the bar's open when it gapped over,
and the setup skipped when that gap pushes the risk over the cap.

A setup's params carry ``entry_cutoff``, ``stop_cap``, ``risk_slippage``,
``near_dollars``, ``near_pct``, ``ema_period`` and the MACD periods. Pure: no
I/O, no clock.

ADR 035: while a setup forms, a detector keeps ``forming`` -- the levels it would
arm with now, computed by the rule that arms it, with what blocks it or what it
still waits for -- and ``symbol_view()`` shows them with the lane's own
indicators. Shown to the desk only: ``forming`` never arms, triggers or scores,
and ``view()`` (the board, the rows, the journal) does not carry it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

from constants_setups import (
    SETUP_STATE_ARMED,
    SETUP_STATE_NEAR,
    SETUP_STATE_PULLBACK,
    SETUP_STATE_TRIGGERED,
    SETUP_STATE_WATCHING,
)
from setup_scanner.series import Series

ET = ZoneInfo("America/New_York")
EPS = 1e-9


def hhmm(text: str) -> dtime:
    h, m = text.split(":")
    return dtime(int(h), int(m))


def et_time(ts: float) -> dtime:
    return datetime.fromtimestamp(ts, ET).time()


@dataclass
class TriggerDetector:
    """One symbol's setup state. Subclasses read the bars in ``on_bars``."""

    symbol: str
    p: Any = None
    state: str = SETUP_STATE_WATCHING
    reason: str = "warming up"
    leg: dict[str, Any] | None = None
    armed: dict[str, Any] | None = None
    triggered: dict[str, Any] | None = None
    nth: int = 0                      # setups triggered today on this symbol
    last_price: float | None = None
    forming: dict[str, Any] | None = None   # the levels it would arm with now (ADR 035); never armed
    series: Series = field(init=False, repr=False)

    FIRST_KIND: ClassVar[str] = ""
    SECOND_KIND: ClassVar[str | None] = None

    def __post_init__(self) -> None:
        self.series = Series(ema_period=self.p.ema_period, macd_fast=self.p.macd_fast,
                             macd_slow=self.p.macd_slow, macd_signal=self.p.macd_signal)

    @property
    def ema_now(self) -> float | None:
        """The EMA at the last completed bar: the scoring exit reads the lane's own."""
        return self.series.e[-1] if self.series.e else None

    def kind_now(self) -> str:
        """The kind a setup armed now would have: the first of the day, then the second."""
        return self.FIRST_KIND if self.nth == 0 or not self.SECOND_KIND else self.SECOND_KIND

    def cutoff(self) -> str:
        """No setup arms, and none triggers, at or after this time (ET)."""
        return str(self.p.entry_cutoff)

    def on_bars(self, bars: list[Any]) -> list[tuple[str, dict]]:   # pragma: no cover - abstract
        raise NotImplementedError

    # -- live price -------------------------------------------------------
    def on_price(self, price: float, ts: float, *, bar_open: float | None = None) -> list[tuple[str, dict]]:
        self.last_price = price
        if self.armed is None or self.state not in (SETUP_STATE_ARMED, SETUP_STATE_NEAR):
            return []
        trig = self.armed["trigger"]
        if price <= trig + EPS:
            return self._near_check(price)
        prev = self.armed
        if et_time(ts) >= hhmm(self.cutoff()):
            return self._disarm(prev, "the entry window closed before the trigger")
        entry = round(max(prev["entry"], bar_open if bar_open is not None else price), 4)
        if entry + self.p.risk_slippage - prev["stop"] > self.p.stop_cap + EPS:
            return self._disarm(prev, f"gapped over the trigger to {entry:.2f}: risk over {self.p.stop_cap:.2f}")
        self.nth += 1
        self.triggered = {**prev, "entry": entry, "triggered_at": ts, "nth": self.nth, "trigger_price": price}
        self._set(SETUP_STATE_TRIGGERED, f"traded {price:.2f} over the {trig:.2f} trigger")
        return [("triggered", self.view())]

    def _disarm(self, prev: dict, why: str) -> list[tuple[str, dict]]:
        self.armed = None
        self._set(SETUP_STATE_PULLBACK, why)
        return [("disarmed", self._key_view(prev, reason=why))]

    def _near_check(self, price: float) -> list[tuple[str, dict]]:
        if self.armed is None:
            return []
        trig = self.armed["trigger"]
        band = max(self.p.near_dollars, self.p.near_pct * price)
        if trig - price <= band:
            if self.state != SETUP_STATE_NEAR:
                self._set(SETUP_STATE_NEAR, f"{trig - price:.2f} under the {trig:.2f} trigger -- read the tape")
                return [("near", self.view())]
        elif self.state == SETUP_STATE_NEAR:
            self._set(SETUP_STATE_ARMED, self.armed_reason())
        return []

    def armed_reason(self) -> str:
        a = self.armed or {}
        return f"trigger {a.get('trigger', 0):.2f}, stop {a.get('stop', 0):.2f}, risk {a.get('risk', 0):.2f}"

    def arm_events(self, prev: dict | None) -> list[tuple[str, dict]]:
        """``armed`` for a new setup, ``rearmed`` when the same one moved, then the near check."""
        events: list[tuple[str, dict]] = []
        if prev is None:
            events.append(("armed", self.view()))
        elif prev["trigger"] != self.armed["trigger"] or prev["stop"] != self.armed["stop"]:
            events.append(("rearmed", self.view()))
        if self.last_price is not None:
            events += self._near_check(self.last_price)
        return events

    # -- helpers ------------------------------------------------------------
    def _set(self, state: str, reason: str) -> None:
        self.state = state
        self.reason = reason

    def _key_view(self, setup: dict, reason: str | None = None) -> dict[str, Any]:
        """A view for an event about ``setup`` (which may no longer be the current one)."""
        v = self.view()
        v["setup"] = dict(setup)
        v["setup_key"] = int(setup["leg_t"])
        if reason:
            v["reason"] = reason
        return v

    def view(self) -> dict[str, Any]:
        setup = self.triggered if self.state == SETUP_STATE_TRIGGERED else self.armed
        key = int(setup["leg_t"]) if setup else (int(self.leg["t"]) if self.leg else 0)
        return {
            "symbol": self.symbol,
            "state": self.state,
            "reason": self.reason,
            "kind": (setup or {}).get("kind") or self.kind_now(),
            "nth": self.nth,
            "setup_key": key,
            "leg": dict(self.leg) if self.leg else None,
            "setup": dict(setup) if setup else None,
            "last_price": self.last_price,
        }

    def symbol_view(self) -> dict[str, Any]:
        """``view()`` plus the forming levels and the lane's own indicators (ADR 035)."""
        return {**self.view(), "forming": dict(self.forming) if self.forming else None,
                "series": self.series.last_values()}


def forming_levels(trigger: float, entry: float, stop: float, target1: float, *, bars: int,
                   blocked: str | None = None, waiting: str | None = None) -> dict[str, Any]:
    """The levels a forming setup would arm with (ADR 035): drawn and planned, never armed."""
    return {"trigger": round(trigger, 4), "entry": round(entry, 4), "stop": round(stop, 4),
            "risk": round(entry - stop, 4), "target1": round(target1, 4), "bars": int(bars),
            "blocked": blocked, "waiting": waiting}


def window_blocked(p: Any, next_bar_t: float, *, start: str | None = None, cutoff: str | None = None) -> str | None:
    """Why the next minute is outside the arming window, or None."""
    lo, hi = start or str(p.session_start), cutoff or str(p.entry_cutoff)
    if hhmm(lo) <= et_time(next_bar_t) < hhmm(hi):
        return None
    return f"outside the entry window {lo}-{hi} ET"


def risk_blocked(p: Any, risk: float, *, slippage: bool = True) -> str | None:
    """Why ``risk`` (entry minus stop) is outside the band, or None. ``slippage`` adds the
    cent the research counted; a flat-top hold's entry already carries it."""
    extra = p.risk_slippage if slippage else 0.0
    shown = f" (+{extra:.2f} slippage)" if extra else ""
    if risk + extra > p.stop_cap + EPS:
        return f"risk {risk:.2f}{shown} is over {p.stop_cap:.2f}"
    if risk + extra < p.min_stop - EPS:
        return f"risk {risk:.2f}{shown} is under {p.min_stop:.2f}"
    return None
