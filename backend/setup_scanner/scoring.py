"""Score a triggered setup the two ways the scoreboard reports (ADR 022).

``first touch`` -- which the live price reached first after the trigger: the
target (``target_first``) or the stop (``stop_first``); ``open`` until one of
them prints, and it stays ``open`` if neither did by the scoring close.

``bar R`` -- the research screen's own exit rules replayed on the completed
one-minute bars after the trigger (research/momentum/backtest_setups.py
``Day.simulate``): half off at target 1 with the stop moved to break-even, the
rest on the first close under the 9 EMA; the stop before target 1; five bars
without a close above entry -> out; flat by 15:55. The entry bar's stop counts
only on a close at or below it, as in the backtest. R is gross -- no fees, no
slippage -- so live numbers sit beside the research table; the summary also
reports it net of one cent of slippage per fill.

Pure: the engine feeds prices and completed bars.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from constants_setups import (
    SETUP_OUTCOME_OPEN,
    SETUP_OUTCOME_STOP_FIRST,
    SETUP_OUTCOME_TARGET_FIRST,
    SETUPS_BAILOUT_BARS,
    SETUPS_SCORE_FLAT_BY_ET,
    SETUPS_SCORE_WINDOW_MIN,
)
from setup_scanner.bars import Bar

ET = ZoneInfo("America/New_York")


def _flat_by(ts: float) -> bool:
    h, m = SETUPS_SCORE_FLAT_BY_ET.split(":")
    return datetime.fromtimestamp(ts, ET).time() >= dtime(int(h), int(m))


@dataclass
class ScoreTracker:
    entry: float
    stop: float
    target1: float
    risk: float
    triggered_at: float
    entry_bar_t: float                 # start of the minute the trigger printed in
    outcome: str = SETUP_OUTCOME_OPEN
    outcome_at: float | None = None
    mfe: float = 0.0                   # best move after the trigger, $/share
    mae: float = 0.0                   # worst move after the trigger, $/share (<= 0)
    half_done: bool = False
    half_px: float | None = None
    bar_stop: float = 0.0
    exit_px: float | None = None
    exit_reason: str | None = None
    closed_at: float | None = None
    bars_seen: int = 0
    bailout_bars: int = SETUPS_BAILOUT_BARS   # a template sets its own (ADR 029)
    half_on_entry_bar: bool = True     # a flat-top hold enters at the close: no half on its own bar (ADR 031)
    _entry_bar_done: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        self.bar_stop = self.stop

    @property
    def done(self) -> bool:
        return self.exit_px is not None and self.outcome != SETUP_OUTCOME_OPEN

    # -- live prices: first touch, MFE / MAE ------------------------------
    def on_price(self, price: float, ts: float) -> bool:
        """Returns True when the first-touch outcome changed."""
        if ts < self.triggered_at:
            return False
        if ts <= self.triggered_at + SETUPS_SCORE_WINDOW_MIN * 60:
            self.mfe = max(self.mfe, price - self.entry)
            self.mae = min(self.mae, price - self.entry)
        if self.outcome != SETUP_OUTCOME_OPEN or _flat_by(ts):
            return False
        if price >= self.target1 - 1e-9:
            self.outcome, self.outcome_at = SETUP_OUTCOME_TARGET_FIRST, ts
            return True
        if price <= self.stop + 1e-9:
            self.outcome, self.outcome_at = SETUP_OUTCOME_STOP_FIRST, ts
            return True
        return False

    # -- completed bars: the backtest's exit rules --------------------------
    def on_bar(self, bar: Bar, ema9: float | None) -> bool:
        """Apply one completed bar at or after the entry bar. Returns True when the trade closed."""
        if self.exit_px is not None or bar.t < self.entry_bar_t:
            return False
        if ema9 is None:
            ema9 = bar.c                     # no EMA yet (never after a seeded day): no EMA exit this bar
        if not self._entry_bar_done:
            self._entry_bar_done = True
            if bar.c <= self.bar_stop:
                return self._exit(self.bar_stop, bar, "stop_entry_bar")
            if self.half_on_entry_bar and bar.h >= self.target1 > self.entry:
                self.half_done, self.half_px, self.bar_stop = True, self.target1, self.entry
            return False
        self.bars_seen += 1
        if _flat_by(bar.t):
            return self._exit(bar.c, bar, "close")
        if bar.lo <= self.bar_stop:
            return self._exit(min(bar.o, self.bar_stop), bar, "breakeven" if self.half_done else "stop")
        if not self.half_done and bar.h >= self.target1:
            self.half_done, self.half_px, self.bar_stop = True, max(bar.o, self.target1), self.entry
        elif self.half_done and bar.c < ema9:
            return self._exit(bar.c, bar, "ema")
        elif not self.half_done and self.bars_seen >= self.bailout_bars and bar.c <= self.entry:
            return self._exit(bar.c, bar, "bailout")
        return False

    def _exit(self, px: float, bar: Bar, reason: str) -> bool:
        self.exit_px, self.exit_reason, self.closed_at = px, reason, bar.t + 60
        return True

    def bar_r(self) -> float | None:
        if self.exit_px is None or self.risk <= 0:
            return None
        if self.half_done and self.half_px is not None:
            pnl = 0.5 * (self.half_px - self.entry) + 0.5 * (self.exit_px - self.entry)
        else:
            pnl = self.exit_px - self.entry
        return round(pnl / self.risk, 3)

    def as_dict(self) -> dict:
        return {
            "outcome": self.outcome, "outcome_at": self.outcome_at,
            "mfe": round(self.mfe, 4), "mae": round(self.mae, 4),
            "bar_r": self.bar_r(), "bar_exit_reason": self.exit_reason, "closed_at": self.closed_at,
            "half_px": self.half_px,
        }
