"""Score a triggered setup the two ways the scoreboard reports (ADR 022).

``first touch`` -- which the live price reached first after the trigger: the
target (``target_first``) or the stop (``stop_first``); ``open`` until one of
them prints, and it stays ``open`` if neither did by the scoring close.

``bar R`` -- the bot's exit (#845, operator decisions 2026-10-09 and 2026-10-12) replayed on the
completed one-minute bars after the trigger: ``target1_fraction`` of the shares sell at target 1 and
the rest at target 2 -- everything at target 1 when there is no target 2 -- and the stop stays where
it is after the first half (it no longer moves to the entry, and the 9 EMA no longer exits the rest);
the stop before target 1; five bars without a close above entry -> out (the bailout, before the first
half only); flat by 15:55. On a bar that reached a target and the stop, the stop is taken: the order
inside a minute is unknown. The entry bar's stop counts only on a close at or below it, as in the
backtest. R is gross -- no fees, no slippage -- R stays the unit (1R = the risk); the summary also
reports it net of one cent of slippage per fill. Exits: ``stop``, ``stop_entry_bar``, ``bailout``,
``target`` (everything at target 1), ``close`` before the first half; ``target2``, ``stop_runner``,
``close_runner`` after it (rows scored before #845 say ``ema`` / ``breakeven``).

A template's flush exit (ADR 034) joins the bar rules: fed each flow reading
after the trigger, a ``flush`` moves the stop up (``tighten``) or gets out at the
bid (``exit``), by ``tape_flow.flush_action`` -- the rule Nova's bot follows too.
Its exits are named: ``flush`` (and ``flush_runner`` after the half), and a
tightened stop that is hit ``flush_stop`` / ``flush_stop_runner``.

A 5-minute lane (``five_minute_lane.py``) feeds its own 5-minute candles: the bailout and the 9 EMA exit
count 5-minute candles (``bar_sec``), and its first touch, MFE and MAE are read over ``window_min``.

A short setup (ADR 049, ``side="short"``) reads every rule mirrored: R is (entry - exit) / risk; the first touch
is target 1 at or under, or the stop at or over; the entry bar's stop counts on a close at or over it; the
first part covers at target 1 and the rest at target 2, the stop staying put; the bailout is five candles
without a close under the entry; a ``burst`` of buying is its flush, covered at the ask. Every comparison is the long one on the sign ``s`` (+1 long, -1 short), so the long path is unchanged.

Pure: the engine feeds prices, completed bars and flow readings.
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
    SETUPS_BAR_SEC,
    SETUPS_SCORE_FLAT_BY_ET,
    SETUPS_SCORE_WINDOW_MIN,
)
from setup_scanner.bars import Bar
from setup_scanner.tape_flow import FlushPolicy, flush_action

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
    target2: float | None = None       # the rest's target (#845); None: everything sells at target 1
    target1_fraction: float = 1.0      # the share of the position that sells at target 1
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
    flush: FlushPolicy = field(default_factory=FlushPolicy)   # the template's flush exit (ADR 034)
    flush_tightened: bool = False
    flush_action: str | None = None    # the last thing a flush did: "tighten" | "exit"
    flush_at: float | None = None
    window_min: int = SETUPS_SCORE_WINDOW_MIN   # MFE / MAE and the flow are read this long after the trigger
    bar_sec: int = SETUPS_BAR_SEC              # the candles fed: a minute, or a 5-minute lane's five
    side: str = "long"                         # ADR 049: a short reads every rule mirrored
    _entry_bar_done: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        self.bar_stop = self.stop
        if self.target2 is None or not 0 < self.target1_fraction < 1:
            self.target2, self.target1_fraction = None, 1.0

    @property
    def _s(self) -> int:
        return -1 if self.side == "short" else 1

    @property
    def done(self) -> bool:
        return self.exit_px is not None and self.outcome != SETUP_OUTCOME_OPEN

    # -- live prices: first touch, MFE / MAE ------------------------------
    def on_price(self, price: float, ts: float) -> bool:
        """Returns True when the first-touch outcome changed."""
        if ts < self.triggered_at:
            return False
        s = self._s
        if ts <= self.triggered_at + self.window_min * 60:
            self.mfe = max(self.mfe, s * (price - self.entry))
            self.mae = min(self.mae, s * (price - self.entry))
        if self.outcome != SETUP_OUTCOME_OPEN or _flat_by(ts):
            return False
        if s * price >= s * self.target1 - 1e-9:
            self.outcome, self.outcome_at = SETUP_OUTCOME_TARGET_FIRST, ts
            return True
        if s * price <= s * self.stop + 1e-9:
            self.outcome, self.outcome_at = SETUP_OUTCOME_STOP_FIRST, ts
            return True
        return False

    # -- completed bars: the bot's exit (#845) --------------------------------
    def on_bar(self, bar: Bar, ema9: float | None = None) -> bool:
        """Apply one completed bar at or after the entry bar. Returns True when the trade closed. ``ema9`` is
        not read since #845 (the 9 EMA exits nothing); callers that hand it in still work."""
        if self.exit_px is not None or bar.t < self.entry_bar_t:
            return False
        s = self._s
        fav, adv = (bar.h, bar.lo) if s > 0 else (bar.lo, bar.h)    # the bar's extreme the trade's way, and against
        if not self._entry_bar_done:
            self._entry_bar_done = True
            if s * bar.c <= s * self.bar_stop:
                return self._exit(self.bar_stop, bar, self._stop_reason("stop_entry_bar"))
            if self.half_on_entry_bar and s * fav >= s * self.target1 > s * self.entry:
                return self._take(self.target1, fav, bar, at_open=None)
            return False
        self.bars_seen += 1
        if _flat_by(bar.t):
            return self._exit(bar.c, bar, "close_runner" if self.half_done else "close")
        if s * adv <= s * self.bar_stop:
            return self._exit(s * min(s * bar.o, s * self.bar_stop), bar,
                              self._stop_reason("stop_runner" if self.half_done else "stop"))
        if not self.half_done and s * fav >= s * self.target1:
            return self._take(s * max(s * bar.o, s * self.target1), fav, bar, at_open=bar.o)
        if self.half_done and self.target2 is not None and s * fav >= s * self.target2:
            return self._exit(s * max(s * bar.o, s * self.target2), bar, "target2")
        if not self.half_done and self.bars_seen >= self.bailout_bars and s * bar.c <= s * self.entry:
            return self._exit(bar.c, bar, "bailout")
        return False

    def _take(self, px: float, fav: float, bar: Bar, *, at_open: float | None) -> bool:
        """Target 1 filled at ``px``: everything when there is no target 2, else the first part -- and the
        rest at target 2 when the same bar reached it too. The stop stays where it is."""
        s = self._s
        if self.target2 is None:
            return self._exit(px, bar, "target")
        self.half_done, self.half_px = True, px
        if s * fav >= s * self.target2:
            t2 = self.target2 if at_open is None else s * max(s * at_open, s * self.target2)
            return self._exit(t2, bar, "target2")
        return False

    def _exit(self, px: float, bar: Bar, reason: str) -> bool:
        self.exit_px, self.exit_reason, self.closed_at = px, reason, bar.t + self.bar_sec
        return True

    def _stop_reason(self, plain: str) -> str:
        """A stop the flush tightened is named for it; any other keeps its own name."""
        if not self.flush_tightened:
            return plain
        return "flush_stop_runner" if self.half_done else "flush_stop"

    # -- flow readings: the template's flush exit (ADR 034) -----------------------
    def on_flow(self, *, label: str | None, price: float | None, bid: float | None, ts: float,
                ask: float | None = None) -> str | None:
        """Apply one flow reading; returns ``"tighten"`` / ``"exit"`` when the flush did something. A long's
        flush sells into the ``bid``; a short's (a burst of buying) covers at the ``ask``."""
        if self.exit_px is not None or ts < self.triggered_at or _flat_by(ts):
            return None
        act = flush_action(self.flush, label=label, price=price, ts=ts, entry=self.entry, risk=self.risk,
                           stop=self.bar_stop, since=self.triggered_at, side=self.side)
        if act is None:
            return None
        self.flush_action, self.flush_at = act["action"], ts
        if act["action"] == "exit":
            px = float(price)
            if self.side == "short":
                if ask is not None and ask >= px > 0:
                    px = float(ask)              # a short's flush covers at the ask
            elif bid is not None and 0 < bid <= px:
                px = float(bid)                  # a flush sells into the bid
            self.exit_px, self.closed_at = px, ts
            self.exit_reason = "flush_runner" if self.half_done else "flush"
            return "exit"
        self.bar_stop, self.flush_tightened = float(act["stop"]), True
        return "tighten"

    def bar_r(self) -> float | None:
        if self.exit_px is None or self.risk <= 0:
            return None
        s = self._s
        if self.half_done and self.half_px is not None:
            f = self.target1_fraction
            pnl = f * s * (self.half_px - self.entry) + (1 - f) * s * (self.exit_px - self.entry)
        else:
            pnl = s * (self.exit_px - self.entry)
        return round(pnl / self.risk, 3)

    def as_dict(self) -> dict:
        return {
            "outcome": self.outcome, "outcome_at": self.outcome_at,
            "mfe": round(self.mfe, 4), "mae": round(self.mae, 4),
            "bar_r": self.bar_r(), "bar_exit_reason": self.exit_reason, "closed_at": self.closed_at,
            "half_px": self.half_px, "flush_action": self.flush_action, "flush_at": self.flush_at,
            "stop_now": self.bar_stop,
        }
