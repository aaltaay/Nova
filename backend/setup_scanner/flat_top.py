"""The high-of-day / flat-top breakout as a live state machine on one-minute bars (ADR 031, amended 2026-10-06).

The flat top is the one the operator's material draws (``flat_top_shape``): a run-up into the high of day, then
candles that tap it again and again -- each high within the tolerance under it -- their closes just under it and
their lows on the 9 EMA. Read after every completed bar the way the first pullback is (ADR 022):

  leg        a new high of day on an impulse, or a flat top with fewer touches than the rule needs; from its
             second touch it is drawn forming ("2 of 3 touches")
  armed      at least ``min_touches`` touches and a base of ``min_consol``-``max_consol`` candles after the first:
             trigger = the high of day, the last base candle's MACD histogram above zero, the next minute inside
             the entry window
  hold       (the default, the taught way) after a live price over the high, the first of the next
             ``hold_bars`` completed candles that holds the flat top (its low in the zone or over it: a retest
             of the level holds) and closes green over the high triggers at its close: entry one cent over that
             close, stop that candle's low (or, with ``hold_stop`` "pullback", the lowest low since the break's
             candle) -- the risk check reads entry minus stop, the cent standing for the research's slippage; a
             close back under the zone first fails it, and ``hold_bars`` candles without a hold disarm it. The
             hold reads the pattern's own candles, or -- ``hold_bar_sec``, the 5-minute flat top's minutes
             (``flat_top_5m``) -- candles of its own the host feeds to ``on_hold_bars``
  break      (the variant) a live price over the high triggers: entry one cent over it (the bar's open when it
             gapped over), stop the base low

The research's pre-registered P2 rule is one setting away (``flat_top_shape.P2_RULE``: the base right after the
last candle at the high, no touch count, no tolerance). Target 1 is entry + R x risk (the research's), or a fixed
amount over the entry. At most ``max_per_symbol_day`` setups trigger on one symbol a day. A hold entry is scored
from the hold candle, which takes no half at target 1 (the research's ``half_on_entry_bar=False``). Pure: no I/O,
no clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from constants_setups import (
    SETUPS_BAR_SEC,
    SETUP_KIND_FLAT_TOP,
    SETUP_KIND_SECOND_FLAT_TOP,
    SETUP_STATE_ARMED,
    SETUP_STATE_FAILED,
    SETUP_STATE_LEG,
    SETUP_STATE_NEAR,
    SETUP_STATE_PULLBACK,
    SETUP_STATE_TRIGGERED,
    SETUP_STATE_WATCHING,
    SETUPS_EMA_PERIOD,
    SETUPS_EMA_TOLERANCE,
    SETUPS_ENTRY_CUTOFF_ET,
    SETUPS_ENTRY_OFFSET_DOLLARS,
    SETUPS_FT_BAND,
    SETUPS_FT_BASE_FIRST_TOUCH,
    SETUPS_FT_BASE_START,
    SETUPS_FT_ENTRY,
    SETUPS_FT_ENTRY_BREAK,
    SETUPS_FT_FORMING_TOUCHES,
    SETUPS_FT_HOLD_BARS,
    SETUPS_FT_HOLD_STOP_CANDLE,
    SETUPS_FT_HOLD_STOP_PULLBACK,
    SETUPS_FT_IMPULSE_PCT,
    SETUPS_FT_LEG_WINDOW_BARS,
    SETUPS_FT_MAX_CONSOL,
    SETUPS_FT_MAX_PER_SYMBOL_DAY,
    SETUPS_FT_MIN_CONSOL,
    SETUPS_FT_MIN_TOUCHES,
    SETUPS_FT_TOUCH_DOLLARS,
    SETUPS_FT_TOUCH_PCT,
    SETUPS_MACD_FAST,
    SETUPS_MACD_POSITIVE,
    SETUPS_MACD_SIGNAL,
    SETUPS_MACD_SLOW,
    SETUPS_MIN_STOP_DOLLARS,
    SETUPS_NEAR_DOLLARS,
    SETUPS_NEAR_PCT,
    SETUPS_RISK_SLIPPAGE_DOLLARS,
    SETUPS_SESSION_START_ET,
    SETUPS_STOP_CAP_DOLLARS,
    SETUPS_STOP_CAP_PCT,
    SETUPS_TARGET_FIXED_DOLLARS,
    SETUPS_TARGET_R,
)
from setup_scanner.bars import Bar
from setup_scanner.detector import (
    EPS,
    TriggerDetector,
    et_time,
    forming_levels,
    hhmm,
    risk_blocked,
    window_blocked,
)
from setup_scanner.flat_top_shape import Shape, find, leg, miss_leg, new_high, pct_words, stale_base, tolerance


@dataclass(frozen=True)
class FlatTopParams:
    impulse_pct: float = SETUPS_FT_IMPULSE_PCT
    leg_window: int = SETUPS_FT_LEG_WINDOW_BARS
    min_consol: int = SETUPS_FT_MIN_CONSOL
    max_consol: int = SETUPS_FT_MAX_CONSOL
    band: float = SETUPS_FT_BAND
    min_touches: int = SETUPS_FT_MIN_TOUCHES              # candles whose high reached the flat top
    touch_pct: float = SETUPS_FT_TOUCH_PCT                # a high this share of the level under it touched it ...
    touch_dollars: float = SETUPS_FT_TOUCH_DOLLARS        # ... or this many dollars under it, whichever is more
    base_start: str = SETUPS_FT_BASE_START                # "first_touch", or the research's "last_high" (P2)
    entry_mode: str = SETUPS_FT_ENTRY
    hold_bars: int = SETUPS_FT_HOLD_BARS
    hold_bar_sec: int | None = None                       # the hold's candle when not the pattern's (5m flat top: 60)
    hold_stop: str = SETUPS_FT_HOLD_STOP_CANDLE           # "candle": the hold candle's low; "pullback": since the break
    ema_period: int = SETUPS_EMA_PERIOD
    ema_tol: float = SETUPS_EMA_TOLERANCE
    macd_positive: bool = SETUPS_MACD_POSITIVE
    macd_fast: int = SETUPS_MACD_FAST
    macd_slow: int = SETUPS_MACD_SLOW
    macd_signal: int = SETUPS_MACD_SIGNAL
    stop_cap: float = SETUPS_STOP_CAP_DOLLARS
    stop_cap_pct: float | None = SETUPS_STOP_CAP_PCT     # a 5-minute lane's cap, as a share of the entry
    bar_sec: int = SETUPS_BAR_SEC                         # the candle's length (a 5-minute lane: 300)
    min_stop: float = SETUPS_MIN_STOP_DOLLARS
    entry_offset: float = SETUPS_ENTRY_OFFSET_DOLLARS
    risk_slippage: float = SETUPS_RISK_SLIPPAGE_DOLLARS
    target_mode: str = "r"
    target_r: float = SETUPS_TARGET_R
    target_fixed: float = SETUPS_TARGET_FIXED_DOLLARS
    near_dollars: float = SETUPS_NEAR_DOLLARS
    near_pct: float = SETUPS_NEAR_PCT
    session_start: str = SETUPS_SESSION_START_ET
    entry_cutoff: str = SETUPS_ENTRY_CUTOFF_ET
    max_per_symbol_day: int = SETUPS_FT_MAX_PER_SYMBOL_DAY

    @property
    def breaks(self) -> bool:
        return self.entry_mode == SETUPS_FT_ENTRY_BREAK

    @property
    def from_first_touch(self) -> bool:
        return self.base_start == SETUPS_FT_BASE_FIRST_TOUCH

    @property
    def hold_sec(self) -> int:
        """The hold candle's length: the pattern's own, or ``hold_bar_sec``."""
        return int(self.hold_bar_sec or self.bar_sec)

    @property
    def hold_apart(self) -> bool:
        """The hold reads candles of its own (``on_hold_bars``), not the pattern's."""
        return self.hold_sec != int(self.bar_sec)

    def hold_words(self, plural: bool = True) -> str:
        """The hold's candles in words: candles, or the 5-minute flat top's minutes."""
        minutes = self.hold_apart and self.hold_sec == 60
        if plural:
            return "minutes" if minutes else "candles"
        return "1-minute candle" if minutes else "candle"

    def target1(self, entry: float, risk: float) -> float:
        if self.target_mode == "fixed":
            return round(entry + self.target_fixed, 4)
        return round(entry + self.target_r * risk, 4)


def touch_words(n: int) -> str:
    return f"{n} touch{'' if n == 1 else 'es'}"


@dataclass
class FlatTopDetector(TriggerDetector):
    p: FlatTopParams = field(default_factory=FlatTopParams)
    broke: dict[str, Any] | None = None     # hold entry: the break of the high, waiting for the hold

    FIRST_KIND: ClassVar[str] = SETUP_KIND_FLAT_TOP
    SECOND_KIND: ClassVar[str | None] = SETUP_KIND_SECOND_FLAT_TOP

    # -- bar close ---------------------------------------------------------
    def on_bars(self, bars: list[Bar]) -> list[tuple[str, dict]]:
        n = len(bars)
        self.series.update(bars)
        self.forming = None
        need = self.p.leg_window + self.p.min_consol + 1
        if n < need:
            if self.state == SETUP_STATE_WATCHING:
                self.reason = f"warming up ({n}/{need} bars)"
            return []
        if self.nth >= self.p.max_per_symbol_day:
            return []                     # the day's setups on this symbol are used (or were, before a restart)
        last = n - 1
        if self.broke is not None and self.armed is not None:
            # Broken and waiting for a hold: the hold's own candles decide when it reads them apart.
            return [] if self.p.hold_apart else self._hold_check(bars, last)
        prev = self.armed if self.state in (SETUP_STATE_ARMED, SETUP_STATE_NEAR) else None
        shape, miss = find(self.series, last, self.p)
        if shape is not None and self.p.min_touches > 1 and len(shape.touches) > 1 and not shape.retested:
            shape = None                  # rising highs a cent apart: a move, not a flat top
        ready = shape is not None and len(shape.touches) >= self.p.min_touches and shape.bars >= self.p.min_consol

        if self.state == SETUP_STATE_TRIGGERED:
            fresh = new_high(self.series, last, self.p)
            new = (ready and self.series.t[shape.first] != self.triggered.get("leg_t")) or (
                fresh is not None and fresh["t"] != self.triggered.get("leg_t"))
            if not new:
                return []                 # the trade is on; a new setup needs a new flat top

        if ready:
            return self._arm(bars, last, shape, prev)
        if shape is not None and len(shape.touches) >= SETUPS_FT_FORMING_TOUCHES:
            return self._forming(shape, prev)

        events: list[tuple[str, dict]] = []
        fresh = new_high(self.series, last, self.p)
        if fresh is not None:
            self.leg, self.armed = fresh, None
            was = self.state
            self._set(SETUP_STATE_LEG, f"new high of day {fresh['high']:.2f} on a {pct_words(fresh['pct'])}% move -- "
                                       "wait for candles to tap it")
            if prev is not None:
                events.append(("disarmed", self._key_view(prev, reason="a new high of day")))
            if was != SETUP_STATE_LEG:
                events.append(("leg", self.view()))
            return events
        if shape is not None:
            return self._forming(shape, prev)       # one touch: the high of day, not tapped again yet
        fail = miss_leg(self.series, miss) if miss is not None else None
        if fail is None and not self.p.from_first_touch:
            fail = stale_base(self.series, last, self.p)
        self.armed = None
        if fail is not None:
            self.leg = fail[0]
            if self.state != SETUP_STATE_FAILED or self.reason != fail[1]:
                self._set(SETUP_STATE_FAILED, fail[1])
                if prev is not None:
                    events.append(("failed", self._key_view(prev, reason=fail[1])))
            return events
        self.leg = None
        self._set(SETUP_STATE_WATCHING, "no base under the high of day")
        if prev is not None:
            events.append(("disarmed", self._key_view(prev, reason="no base under the high of day")))
        return events

    def _forming(self, shape: Shape, prev: dict | None) -> list[tuple[str, dict]]:
        """Fewer touches than the rule needs: forming (drawn from the second touch), never armed."""
        p = self.p
        n, level = len(shape.touches), shape.level
        self.leg, self.armed, self.broke = leg(self.series, shape), None, None
        if n >= SETUPS_FT_FORMING_TOUCHES:
            entry = round(level + p.entry_offset, 4)
            risk = round(entry - shape.base_low, 4)
            more = p.min_touches - n
            if more > 0:
                have, waiting = n, f"{more} more touch{'' if more == 1 else 'es'}"
                why = (f"flat top {level:.2f}: {n} of {p.min_touches} touches -- {more} more tap"
                       f"{'' if more == 1 else 's'} of it arms it")
            else:                          # touches enough, the base too short yet (a template's fewer touches)
                more = p.min_consol - shape.bars
                have, waiting = shape.bars, f"{more} more candle{'' if more == 1 else 's'}"
                why = f"flat top {level:.2f}: {touch_words(n)} -- the base needs {p.min_consol} candles"
            self.forming = forming_levels(level, entry, shape.base_low, p.target1(entry, risk), bars=have,
                                          waiting=waiting)
        else:
            why = f"the {level:.2f} high of day, touched once -- a flat top needs {touch_words(p.min_touches)}"
        events: list[tuple[str, dict]] = []
        if prev is not None:
            events.append(("disarmed", self._key_view(prev, reason=f"the flat top has {touch_words(n)} now")))
        was = self.state
        self._set(SETUP_STATE_LEG, why)
        if was != SETUP_STATE_LEG:
            events.append(("leg", self.view()))
        return events

    def _arm(self, bars: list[Bar], last: int, shape: Shape, prev: dict | None) -> list[tuple[str, dict]]:
        s, p = self.series, self.p
        events: list[tuple[str, dict]] = []
        level, base_low, m, n = shape.level, shape.base_low, shape.bars, len(shape.touches)
        self.leg = leg(s, shape)
        key = self.leg["t"]
        entry = round(level + p.entry_offset, 4)
        risk = round(entry - base_low, 4)
        blocked = window_blocked(p, bars[last].t + p.bar_sec)
        if blocked is None and p.macd_positive and s.hist[last] <= 0:
            blocked = "MACD negative -- not on the front side"
        if blocked is None and p.breaks:
            blocked = risk_blocked(p, risk, entry=entry)
        if blocked:
            self.armed, self.broke = None, None
            self.forming = forming_levels(level, entry, base_low, p.target1(entry, risk), bars=m, blocked=blocked)
            self._set(SETUP_STATE_PULLBACK, f"flat top {level:.2f}: {touch_words(n)}, a base of {m} candles, "
                                            f"but {blocked}")
            if prev is not None:
                events.append(("disarmed", self._key_view(prev, reason=blocked)))
            return events
        if prev is not None and prev["leg_t"] != key:
            events.append(("disarmed", self._key_view(prev, reason="a newer flat top took over")))
            prev = None
        self.broke = None
        self.armed = {
            "leg_t": key, "trigger": round(level, 4), "entry": entry, "stop": round(base_low, 4),
            "risk": risk, "target1": p.target1(entry, risk), "pullback_bars": m, "leg_high": level,
            "leg_low": shape.impulse_low, "leg_pct": shape.pct, "armed_bar_t": bars[last].t,
            "armed_at": (prev or {}).get("armed_at") or bars[last].t + p.bar_sec, "kind": self.kind_now(),
            "detail": {"entry_mode": p.entry_mode, "base_low": round(base_low, 4), "broke_at": None,
                       "broke_bar_t": None, "hold_bars": p.hold_bars, "touches": self.leg["touches"],
                       "zone": shape.zone, "min_touches": p.min_touches},
        }
        how = (f"stop {base_low:.2f}, risk {risk:.2f}" if p.breaks
               else f"then a green {p.hold_words(plural=False)} holding over it (up to {p.hold_bars})")
        self._set(SETUP_STATE_ARMED, f"flat top {level:.2f}: {touch_words(n)}, a base of {m} candles -- "
                                     f"trigger {level:.2f}, {how}")
        return events + self.arm_events(prev)

    # -- live price -------------------------------------------------------
    def on_price(self, price: float, ts: float, *, bar_open: float | None = None) -> list[tuple[str, dict]]:
        if self.p.breaks:
            return super().on_price(price, ts, bar_open=bar_open)
        self.last_price = price
        if self.armed is None or self.state not in (SETUP_STATE_ARMED, SETUP_STATE_NEAR) or self.broke is not None:
            return []
        trig = self.armed["trigger"]
        if price <= trig + EPS:
            return self._near_check(price)
        if et_time(ts) >= hhmm(self.cutoff()):
            return self._disarm(self.armed, "the entry window closed before the break")
        hold = self.p.hold_sec
        self.broke = {"at": ts, "bar_t": float(int(ts // hold) * hold)}
        self.armed = {**self.armed, "detail": {**(self.armed.get("detail") or {}), "broke_at": ts,
                                               "broke_bar_t": self.broke["bar_t"]}}
        was = self.state
        self._set(SETUP_STATE_NEAR, f"broke the {trig:.2f} high -- the first of the next {self.p.hold_bars} "
                                    f"{self.p.hold_words()} that holds over it and closes green is the entry")
        return [("near", self.view())] if was != SETUP_STATE_NEAR else []

    def _hold_check(self, bars: list[Bar], last: int) -> list[tuple[str, dict]]:
        """Hold entry, after the break: a completed candle holds the flat top, closes back under it, or none comes.

        The zone under the level counts as the level: a candle that dips into it and closes green over the
        high holds (a retest), and only a close under the zone fails."""
        b = bars[last]
        broke_bar = float(self.broke["bar_t"])
        if b.t <= broke_bar:
            return []                     # the break's own candle: the hold starts after it
        level = float(self.armed["trigger"])
        floor = level - tolerance(self.p, level)
        waited = sum(1 for x in bars if x.t > broke_bar)
        prev = self.armed
        if b.c < floor - EPS:
            why = f"closed back under the {level:.2f} high before a candle held it"
            self.armed, self.broke = None, None
            self._set(SETUP_STATE_FAILED, why)
            return [("failed", self._key_view(prev, reason=why))]
        if b.lo >= floor - EPS and b.c > b.o + EPS and b.c > level + EPS:
            entry = round(b.c + self.p.entry_offset, 4)
            stop = round(b.lo, 4)
            if self.p.hold_stop == SETUPS_FT_HOLD_STOP_PULLBACK:   # the pullback's low: every candle since the break's
                stop = round(min(x.lo for x in bars if broke_bar < x.t <= b.t), 4)
            risk = round(entry - stop, 4)
            why = risk_blocked(self.p, risk, entry=entry, slippage=False)
            if why:
                return self._disarm(prev, f"the hold candle's {why}")
            self.nth += 1
            self.triggered = {
                **prev, "entry": entry, "stop": stop, "risk": risk, "target1": self.p.target1(entry, risk),
                "triggered_at": b.t + self.p.hold_sec, "nth": self.nth, "trigger_price": b.c, "score_bar_t": b.t,
                "half_on_entry_bar": False,
                "detail": {**(prev.get("detail") or {}), "hold_bar_t": b.t, "hold_high": b.h},
            }
            self.broke = None
            self._set(SETUP_STATE_TRIGGERED, f"held over {level:.2f}: a green {self.p.hold_words(plural=False)} "
                                             f"closed at {b.c:.2f} -- entry {entry:.2f}, stop {stop:.2f}")
            return [("triggered", self.view())]
        if waited >= self.p.hold_bars:
            return self._disarm(prev, f"no {self.p.hold_words(plural=False)} held over {level:.2f} and closed green "
                                      f"within {self.p.hold_bars}")
        self.reason = (f"broke {level:.2f}: {waited} of {self.p.hold_bars} {self.p.hold_words()}, none held over "
                       "it and closed green yet")
        return []

    def on_hold_bars(self, bars: list[Bar]) -> list[tuple[str, dict]]:
        """A completed hold candle when the hold reads its own (``hold_apart``): the hold check, else nothing."""
        if not self.p.hold_apart or self.broke is None or self.armed is None or not bars:
            return []
        return self._hold_check(bars, len(bars) - 1)

    def _disarm(self, prev: dict, why: str) -> list[tuple[str, dict]]:
        self.broke = None
        return super()._disarm(prev, why)
