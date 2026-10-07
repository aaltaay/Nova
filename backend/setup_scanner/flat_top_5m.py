"""The 5-minute flat top (ADR 031 amendment 2026-10-06; operator: "Make the 5-minute flat top a Paper buy with a
1-minute hold entry, as the material trades it").

The operator's material reads the flat top on the 5-minute chart and executes on the 1-minute chart: after the
break it lets the 1-minute candles spike and pull back, and buys once that pullback holds the level -- the
1-minute pullback inside the 5-minute breakout candle, not the break itself. So this detector is fed the
scanner's minutes like every other -- its lane's tape reads, liquidity, scoring and the bot are the minutes' --
and reads the pattern on 5-minute candles it makes of them (``five_minute.candles``: on the clock from 04:00 ET,
one over once its last minute, or a later one, is in) by ``FlatTopDetector``'s rules with ``bar_sec`` 300: the
touches, the base, the 9 EMA and the MACD are the 5-minute chart's, and the pattern is read only when a 5-minute
candle is over.

After a live price over the flat top, the hold is read on the minutes (``hold_bar_sec`` 60): the first of the
next ``hold_bars`` minutes after the break's own that holds the touch zone and closes green over the high
triggers at its close, entry one cent over it, the stop at the pullback's low -- the lowest low of those minutes
(``hold_stop``); a minute closing under the zone first fails it. The scoring exit's 9 EMA is the minutes' too:
the trade is a 1-minute trade. Pure: no I/O, no clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from constants_setups import SETUP_KIND_FLAT_TOP_5M, SETUP_KIND_SECOND_FLAT_TOP_5M, SETUPS_BAR_SEC
from setup_scanner.bars import Bar
from setup_scanner.five_minute import candles
from setup_scanner.flat_top import FlatTopDetector
from setup_scanner.series import Series


def five_minute_candles(bars: list[Bar]) -> list[Bar]:
    """The 5-minute candles of ``bars`` that are over: a candle is once its last minute, or a later one, is in."""
    if not bars:
        return []
    return [Bar(c["t"], c["o"], c["h"], c["l"], c["c"], c["v"])
            for c in candles(bars, bars[-1].t + SETUPS_BAR_SEC)]


@dataclass
class FlatTop5mDetector(FlatTopDetector):
    minutes: Series = field(init=False, repr=False)
    fed: int = 0                      # the 5-minute candles the pattern has read

    FIRST_KIND: ClassVar[str] = SETUP_KIND_FLAT_TOP_5M
    SECOND_KIND: ClassVar[str | None] = SETUP_KIND_SECOND_FLAT_TOP_5M

    def __post_init__(self) -> None:
        super().__post_init__()
        self.minutes = Series(ema_period=self.p.ema_period, macd_fast=self.p.macd_fast,
                              macd_slow=self.p.macd_slow, macd_signal=self.p.macd_signal)

    @property
    def ema_now(self) -> float | None:
        """The scoring exit's EMA: the minutes', the trade being a 1-minute one."""
        return self.minutes.e[-1] if self.minutes.e else None

    def on_bars(self, bars: list[Bar]) -> list[tuple[str, dict]]:
        """The scanner's minutes: the pattern reads a 5-minute candle once it is over, the hold every minute."""
        self.minutes.update(bars)
        events: list[tuple[str, dict]] = []
        done = five_minute_candles(bars)
        if len(done) != self.fed:
            self.fed = len(done)
            events += super().on_bars(done)
        return events + self.on_hold_bars(bars)
