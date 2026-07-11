"""
Gap and Go setup detection — signal-only.

Detects the mechanical parts of the Gap and Go setup:
  - Five Pillars pass (see five_pillars.py)
  - Inside the 9:30-10:00 AM ET entry window
  - Price has broken above the pre-market high

This module NEVER places an order. `evaluate_gap_and_go()` only returns a
GapAndGoSignal describing what a rules-following trader COULD do next,
with `would_execute` hard-coded to False so nothing downstream can mistake
a signal for an executed trade. Level 2 / time-and-sales exit judgment is
explicitly out of scope here (see backbone doc, section 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from constants import (
    GAP_AND_GO_MAX_STOP_DOLLARS,
    GAP_AND_GO_MIN_PROFIT_LOSS_RATIO,
    GAP_AND_GO_WINDOW_END_ET,
    GAP_AND_GO_WINDOW_START_ET,
)
from strategy.five_pillars import FivePillarsResult, evaluate_five_pillars

_ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class GapAndGoSignal:
    symbol: str
    five_pillars: FivePillarsResult
    in_time_window: bool
    premarket_high: float | None
    current_price: float | None
    triggered: bool          # price has broken above premarket_high
    entry_price: float | None
    stop_price: float | None
    target_price: float | None
    would_execute: bool = False  # always False — this module never trades
    notes: tuple[str, ...] = ()

    @property
    def eligible(self) -> bool:
        """All conditions met to consider this a valid Gap and Go signal."""
        return self.five_pillars.all_pass and self.in_time_window and self.triggered

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "eligible": self.eligible,
            "would_execute": self.would_execute,
            "in_time_window": self.in_time_window,
            "premarket_high": self.premarket_high,
            "current_price": self.current_price,
            "triggered": self.triggered,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "five_pillars": self.five_pillars.to_dict(),
            "notes": list(self.notes),
        }


def _in_window(now_et: datetime) -> bool:
    start = dtime(*GAP_AND_GO_WINDOW_START_ET)
    end = dtime(*GAP_AND_GO_WINDOW_END_ET)
    return start <= now_et.timetz().replace(tzinfo=None) < end


def _premarket_high(bars: list[dict]) -> float | None:
    """Highest high among bars timestamped before 9:30 AM ET.

    Each bar dict must have 't' (ISO timestamp) and 'h' (high) keys, matching
    the shape returned by backend/bars.py.
    """
    session_open = dtime(*GAP_AND_GO_WINDOW_START_ET)
    highs: list[float] = []
    for bar in bars:
        ts_raw = bar.get("t")
        high = bar.get("h")
        if ts_raw is None or high is None:
            continue
        try:
            ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")).astimezone(_ET)
        except ValueError:
            continue
        if ts.timetz().replace(tzinfo=None) < session_open:
            highs.append(float(high))
    return max(highs) if highs else None


def evaluate_gap_and_go(
    candidate: dict,
    bars: list[dict],
    now_et: datetime | None = None,
) -> GapAndGoSignal:
    """Evaluate the Gap and Go setup for one candidate using its intraday bars.

    `candidate` uses the same field names as five_pillars.evaluate_five_pillars.
    `bars` is a list of OHLCV dicts (see backend/bars.py) covering pre-market
    through the current bar for today.
    """
    now_et = now_et or datetime.now(_ET)
    symbol = candidate.get("symbol", "?")
    pillars = evaluate_five_pillars(candidate)

    in_window = _in_window(now_et)
    premarket_high = _premarket_high(bars)
    current_price = candidate.get("price", candidate.get("current_price"))

    triggered = bool(
        premarket_high is not None and current_price is not None and current_price > premarket_high
    )

    entry_price = stop_price = target_price = None
    notes: list[str] = []

    if not pillars.all_pass:
        notes.append(f"Five Pillars not all met ({pillars.pass_count}/5) — no signal.")
    if not in_window:
        notes.append("Outside the 9:30-10:00 AM ET Gap and Go entry window.")
    if premarket_high is None:
        notes.append("No pre-market bars available — cannot locate pre-market high.")
    elif not triggered:
        notes.append(f"Price has not yet broken pre-market high (${premarket_high:.2f}).")

    if pillars.all_pass and in_window and triggered and current_price is not None:
        entry_price = round(current_price, 2)
        stop_price = round(entry_price - GAP_AND_GO_MAX_STOP_DOLLARS, 2)
        risk = entry_price - stop_price
        target_price = round(entry_price + risk * GAP_AND_GO_MIN_PROFIT_LOSS_RATIO, 2)
        notes.append(
            f"Signal only — entry ${entry_price:.2f}, stop ${stop_price:.2f}, "
            f"target ${target_price:.2f} ({GAP_AND_GO_MIN_PROFIT_LOSS_RATIO:.0f}:1). "
            "No order has been placed."
        )

    return GapAndGoSignal(
        symbol=symbol,
        five_pillars=pillars,
        in_time_window=in_window,
        premarket_high=premarket_high,
        current_price=current_price,
        triggered=triggered,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        would_execute=False,
        notes=tuple(notes),
    )
