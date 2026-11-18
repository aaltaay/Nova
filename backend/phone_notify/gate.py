"""Whether one event on the desk becomes a notification on the phone. Pure: the clock, the settings and how a
stock is listed are passed in; the memory is the trading day's and lives in the ``Gate`` the caller keeps.

The rules are the operator's settings and the desk's own toast rules (ADR 044), no more:

- Market alerts (HOD Momo, a setup, a new leader) come only on the chosen days, between the chosen hours,
  New York time. Fills and the loss limit come at any time.
- HOD Momo: off, your stars only, or every stock. Running Up never notifies. One per stock per quiet
  period; the alerts in between are held back, not queued.
- A setup: only a star's, only on the live scanner's playing lanes, only when it arms, comes near its
  trigger or triggers, and each of those once per setup.
- A new leader: once per stock per day.
- Fills and the loss limit: Live and Paper. A Sim replay is another day's market and never notifies.
  A fill that carries an id is said once, however often its producer hands it over.

Every "no" carries its reason, so a test (and the log) can say why a notification did not go.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from phone_notify.constants_phone_notify import (
    HOD_MODE_ALL,
    HOD_MODE_OFF,
    KIND_FILL,
    KIND_HOD,
    KIND_LEADER,
    KIND_LOSS_LIMIT,
    KIND_SETUP,
    KIND_TEST,
    PHONE_NOTIFY_ACCOUNT_VENUES,
    PHONE_NOTIFY_HOD_QUIET_SEC,
    PHONE_NOTIFY_SETUP_STAGES,
    PHONE_NOTIFY_TZ,
)
from phone_notify.store import minutes_of

_ET = ZoneInfo(PHONE_NOTIFY_TZ)
_RUNNING_UP_STRATEGY_ID = 12        # constants_hod_momo.HOD_MOMO_RUNNING_UP_STRATEGY_ID; the id, never the name
_STAR = "star"

SEND = "send"


def trading_day(now: float) -> str:
    """The desk's day at ``now``: it turns over at 04:00 New York time."""
    return (datetime.fromtimestamp(now, _ET) - timedelta(hours=4)).strftime("%Y-%m-%d")


def in_hours(settings: dict[str, Any], now: float) -> bool:
    """Whether ``now`` is on a chosen day, from the start up to (not including) the end."""
    at = datetime.fromtimestamp(now, _ET)
    start, end = minutes_of(settings.get("start")), minutes_of(settings.get("end"))
    if start is None or end is None or at.weekday() not in (settings.get("days") or []):
        return False
    return start <= at.hour * 60 + at.minute < end


@dataclass
class Gate:
    """One trading day's memory of what was sent."""

    day: str = ""
    hod_last: dict[str, float] = field(default_factory=dict)
    setups_said: set[tuple[str, str]] = field(default_factory=set)
    leaders_said: set[str] = field(default_factory=set)
    fills_said: set[tuple[str, str]] = field(default_factory=set)

    def _roll(self, now: float) -> None:
        day = trading_day(now)
        if day != self.day:
            self.day = day
            self.hod_last.clear()
            self.setups_said.clear()
            self.leaders_said.clear()
            self.fills_said.clear()

    def decide(
        self,
        kind: str,
        event: dict[str, Any],
        *,
        settings: dict[str, Any],
        now: float,
        how: Callable[[str], str | None] = lambda _symbol: None,
    ) -> str:
        """``SEND``, or the reason the event is held back. A ``SEND`` is remembered: asking twice sends once."""
        self._roll(now)
        symbol = str(event.get("symbol") or "").strip().upper()
        if kind == KIND_TEST:
            return SEND
        if kind == KIND_HOD:
            mode = settings.get("hod_momo")
            if mode == HOD_MODE_OFF:
                return "off"
            if event.get("strategy_id") == _RUNNING_UP_STRATEGY_ID:
                return "running_up"
            if not symbol:
                return "no_symbol"
            if mode != HOD_MODE_ALL and how(symbol) != _STAR:
                return "not_a_star"
            if not in_hours(settings, now):
                return "outside_hours"
            last = self.hod_last.get(symbol)
            if last is not None and now - last < PHONE_NOTIFY_HOD_QUIET_SEC:
                return "quiet"
            self.hod_last[symbol] = now
            return SEND
        if kind == KIND_SETUP:
            if not settings.get("setups"):
                return "off"
            stage = str(event.get("stage") or "")
            if stage not in PHONE_NOTIFY_SETUP_STAGES:
                return "not_a_stage"
            if event.get("source") != "live" or event.get("playing") is not True:
                return "not_live"
            if not symbol or how(symbol) != _STAR:
                return "not_a_star"
            if not in_hours(settings, now):
                return "outside_hours"
            key = (str(event.get("setup_id") or symbol), stage)
            if key in self.setups_said:
                return "said"
            self.setups_said.add(key)
            return SEND
        if kind == KIND_LEADER:
            if not settings.get("new_leader"):
                return "off"
            if not symbol:
                return "no_symbol"
            if not in_hours(settings, now):
                return "outside_hours"
            if symbol in self.leaders_said:
                return "said"
            self.leaders_said.add(symbol)
            return SEND
        if kind == KIND_FILL:
            if not settings.get("fills"):
                return "off"
            if event.get("venue") not in PHONE_NOTIFY_ACCOUNT_VENUES:
                return "not_this_venue"
            if not symbol:
                return "no_symbol"
            if event.get("id") is not None:
                key = (str(event.get("venue")), str(event.get("id")))
                if key in self.fills_said:
                    return "said"
                self.fills_said.add(key)
            return SEND
        if kind == KIND_LOSS_LIMIT:
            if not settings.get("loss_limit"):
                return "off"
            return SEND if event.get("venue") in PHONE_NOTIFY_ACCOUNT_VENUES else "not_this_venue"
        return "unknown_kind"
