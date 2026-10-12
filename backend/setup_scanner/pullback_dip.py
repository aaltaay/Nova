"""The pullback dip (#847): the first pullback's run and pullback, bought at the candle that bottoms it. WATCH ONLY.

The operator's material lists three entries for a pullback: the first candle to make a new high (the first pullback,
``pullback.py``, buys that break), the first candle to close green, and the bottoming wick -- buying the dip -- and
pairs a dip entry with the high of the pullback as the first target. This detector reads the last two
(``dip_candle.py``; a template's ``entry_mode``), after every completed one-minute candle:

  leg        a fresh run made a new high -- the first pullback's leg rules and numbers (``PullbackDetector``: the
             highest high of the prior 30 candles, the high of day, 5%+ over the leg window's low): wait for the
             pullback
  pullback   the candles after the leg high pull back by the first pullback's rules -- no new high, less than half
             the leg given back, every close on the 9 EMA -- and the entry candle has not come (``forming`` waits
             for it), or it came and one rule blocks it (MACD, the window, the risk: the reason says which)
  triggered  the pullback's newest candle is the entry: the pullback ``min_pullback_bars``-``max_pullback_bars``
             candles long, the entry candle included; its MACD histogram above zero; its close inside the entry
             window. The setup arms and triggers at that candle's close: entry ``entry_offset`` over the close (a
             limit over the close, never a chase of the ask), the stop ``stop_offset`` under the pullback's low, the
             risk inside the template's caps -- the entry's cent stands for the slippage, as a flat-top hold's does.
             Targets are the menu's (``targets.py``): by default the first half at the high the pullback came off
             (the leg high), the second the menu's default. It is scored from the entry candle, which takes no half
             at target 1.
  failed     the pullback broke a rule, ran past ``max_pullback_bars`` candles without an entry, or -- the green
             entry -- its first green close came and was not the entry

No live price triggers it -- the entry is a candle's close -- so ``on_price`` only follows the price. At most
``max_per_symbol_day`` dips trigger on one symbol a day; after one, the next needs a new leg.

Watch only (``constants_bot.BOT_WATCH_ONLY_SETUPS``): its lane never proposes it or tells the bot, and
``setup_scanner.trade_verdict`` reads NOT A TRADE on it. Pure: no I/O, no clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from constants_setups import (
    SETUP_KIND_PULLBACK_DIP,
    SETUP_KIND_SECOND_PULLBACK_DIP,
    SETUP_STATE_ARMED,
    SETUP_STATE_FAILED,
    SETUP_STATE_LEG,
    SETUP_STATE_PULLBACK,
    SETUP_STATE_TRIGGERED,
    SETUP_STATE_WATCHING,
    SETUPS_DIP_CLOSE_MIN,
    SETUPS_DIP_ENTRY,
    SETUPS_DIP_MAX_PULLBACK_BARS,
    SETUPS_DIP_MIN_PULLBACK_BARS,
    SETUPS_DIP_MIN_RED_BARS,
    SETUPS_DIP_STOP_OFFSET_DOLLARS,
    SETUPS_DIP_WICK_MIN,
    SETUPS_DIP_WICK_MIN_DOLLARS,
    SETUPS_TARGET_PULLBACK_HIGH,
)
from setup_scanner import dip_candle
from setup_scanner.bars import Bar
from setup_scanner.detector import forming_levels, risk_blocked, window_blocked
from setup_scanner.pullback import PullbackDetector, PullbackParams
from setup_scanner.targets import TargetSpec

# The menu's choice a dip starts from: the first half at the high the pullback came off, the second the default.
DIP_TARGETS = TargetSpec(first=SETUPS_TARGET_PULLBACK_HIGH)


@dataclass(frozen=True)
class DipParams(PullbackParams):
    """The first pullback's numbers (the run and the pullback), the dip's own entry, and its stop."""

    min_pullback_bars: int = SETUPS_DIP_MIN_PULLBACK_BARS     # the entry candle included
    max_pullback_bars: int = SETUPS_DIP_MAX_PULLBACK_BARS
    risk_slippage: float = 0.0          # the entry's cent over the close stands for it, as a flat-top hold's does
    targets: TargetSpec = DIP_TARGETS
    entry_mode: str = SETUPS_DIP_ENTRY
    wick_min: float = SETUPS_DIP_WICK_MIN
    close_min: float = SETUPS_DIP_CLOSE_MIN
    wick_min_dollars: float = SETUPS_DIP_WICK_MIN_DOLLARS
    min_red: int = SETUPS_DIP_MIN_RED_BARS
    stop_offset: float = SETUPS_DIP_STOP_OFFSET_DOLLARS


def _n(m: int) -> str:
    return f"{m} candle{'' if m == 1 else 's'}"


@dataclass
class PullbackDipDetector(PullbackDetector):
    """One symbol's dip. ``on_bars`` after each completed candle; ``on_price`` follows the price only."""

    p: DipParams = field(default_factory=DipParams)
    said_leg_t: float | None = None     # the leg a ``leg`` event last named (the lane reads the pillars on it)

    FIRST_KIND: ClassVar[str] = SETUP_KIND_PULLBACK_DIP
    SECOND_KIND: ClassVar[str | None] = SETUP_KIND_SECOND_PULLBACK_DIP
    TAPE_WHILE_FORMING: ClassVar[bool] = True   # its trigger reads the tape that printed into its entry candle

    def on_bars(self, bars: list[Bar]) -> list[tuple[str, dict]]:
        n = len(bars)
        self.series.update(bars)
        self.forming = None
        if n < self.p.leg_lookback + 2:
            if self.state == SETUP_STATE_WATCHING:
                self.reason = f"warming up ({n}/{self.p.leg_lookback + 2} bars)"
            return []
        if self.nth >= self.p.max_per_symbol_day:
            return []                     # the day's dips on this symbol are used (or were, before a restart)
        h, lows = self.series.h, self.series.lo
        last = n - 1
        cand, first_fail = self.find_pullback(bars, last, 1, self.p.max_pullback_bars)
        fresh = self._qualify_leg(bars, h, lows, last)
        if self.state == SETUP_STATE_TRIGGERED:
            done = self.triggered.get("leg_t") if self.triggered else None
            if not ((cand and cand[1]["t"] != done) or (fresh and fresh["t"] != done)):
                return []                 # the trade is on; the next dip needs a new leg
        if cand is not None:
            return self._read(bars, last, cand)
        if fresh is not None:
            self.leg = fresh
            was = self.state
            self.said_leg_t = fresh["t"]
            self._set(SETUP_STATE_LEG, f"new high {fresh['high']:.2f} on a {100 * fresh['pct']:.1f}% leg -- wait for "
                                       "the pullback, then the candle that bottoms it")
            return [("leg", self.view())] if was != SETUP_STATE_LEG else []
        fail = first_fail or self._stale_leg(bars, h, lows, last)
        if fail is not None:
            self._fail(fail[0], fail[1])
            return []
        self.leg = None
        self._set(SETUP_STATE_WATCHING, "no fresh leg")
        return []

    def _read(self, bars: list[Bar], last: int, cand: tuple) -> list[tuple[str, dict]]:
        """The pullback ``m`` candles long off ``leg``: its newest candle the entry, a wait, a block or a failure.

        A pullback whose leg no ``leg`` event named (a symbol first read mid-pullback) names it first: the lane
        reads the forming row's pillars on it, as on a new high."""
        m, leg, pb_low = cand
        p, b = self.p, bars[last]
        unnamed = self.said_leg_t != leg["t"]
        self.said_leg_t = leg["t"]
        self.leg = leg
        got = dip_candle.read(p.entry_mode, bars[last - m + 1:last + 1], p)
        entry = round(b.c + p.entry_offset, 4)
        stop, stop_why = self.stop_at(entry, round(pb_low - p.stop_offset, 4), slippage=False)
        risk = round(entry - stop, 4)
        aim = self.aim(entry, pullback_high=leg["high"], stop=stop_why)
        waiting = dip_candle.WAITING.get(p.entry_mode, dip_candle.WAITING[SETUPS_DIP_ENTRY])
        head = f"pulling back {_n(m)} off the {leg['high']:.2f} high"
        blocked = None
        if got.final or (not got.ok and m >= p.max_pullback_bars):
            self._fail(leg, got.why if got.final else f"no {waiting} in {_n(p.max_pullback_bars)} of pullback")
        elif not got.ok or m < p.min_pullback_bars:
            why = got.why if not got.ok else f"the entry needs a pullback of {_n(p.min_pullback_bars)}"
            self.forming = forming_levels(b.c, entry, stop, aim, bars=m, waiting=waiting)
            self._set(SETUP_STATE_PULLBACK, f"{head} -- waiting for {waiting}: {why}")
        else:
            blocked = window_blocked(p, b.t + p.bar_sec)
            if blocked is None and p.macd_positive and self.series.hist[last] <= 0:
                blocked = "MACD negative -- not on the front side"
            if blocked is None:
                blocked = risk_blocked(p, risk, entry=entry, slippage=False)
            if blocked is None:
                named = [("leg", self.view())] if unnamed else []
                return named + self._trigger(b, m, leg, pb_low, entry, round(stop, 4), risk, aim, got.detail, got.why)
            self.forming = forming_levels(b.c, entry, stop, aim, bars=m, blocked=blocked)
            self._set(SETUP_STATE_PULLBACK, f"{head}: {got.why}, but {blocked}")
        return [("leg", self.view())] if unnamed else []

    def _fail(self, leg: dict[str, Any], why: str) -> None:
        """The dip off ``leg`` is dead; the first reason stays while the same leg is the one read."""
        same = self.state == SETUP_STATE_FAILED and self.leg is not None and self.leg.get("t") == leg["t"]
        self.leg = leg
        if not same:
            self._set(SETUP_STATE_FAILED, why)

    def _trigger(self, b: Bar, m: int, leg: dict[str, Any], pb_low: float, entry: float, stop: float, risk: float,
                 aim: dict[str, Any], detail: dict[str, Any], why: str) -> list[tuple[str, dict]]:
        """Arm and trigger at the entry candle's close: the row is made (``armed``), then the trade (``triggered``)."""
        p = self.p
        closed = b.t + p.bar_sec
        self.armed = {
            "leg_t": leg["t"], "trigger": round(b.c, 4), "entry": entry, "stop": stop, "risk": risk, **aim,
            "pullback_bars": m, "leg_high": leg["high"], "leg_low": leg["low"], "leg_pct": leg["pct"],
            "armed_bar_t": b.t, "armed_at": closed, "kind": self.kind_now(),
            "detail": {**detail, "pullback_low": round(pb_low, 4), "pullback_high": leg["high"],
                       "stop_offset": p.stop_offset},
        }
        self._set(SETUP_STATE_ARMED, f"{why} -- entry {entry:.2f}, stop {stop:.2f}, risk {risk:.2f}")
        events = [("armed", self.view())]
        self.nth += 1
        self.triggered = {**self.armed, "triggered_at": closed, "nth": self.nth, "trigger_price": b.c,
                          "score_bar_t": b.t, "half_on_entry_bar": False}
        self.armed = None
        self._set(SETUP_STATE_TRIGGERED, f"bought the dip at the {b.c:.2f} close: {why} -- entry {entry:.2f}, "
                                         f"stop {stop:.2f}")
        events.append(("triggered", self.view()))
        return events
