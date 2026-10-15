"""A watched stock's day as live HOD Momo would have received it: IBKR L1 ticks made from Massive's trades.

IBKR's L1 line conflates a stock's prints: at most one last-price tick per ``HOD_MOMO_REBUILD_L1_TICK_SEC``, carrying
the latest price, the day's volume and the day's high so far. So each interval that held a price-setting print
(``sim/massive_files.sets_price``) gives one tick at the interval's end -- the moment the line would have
delivered it -- with that interval's last price; volume counts every trade, the high every price-setting print.
Ticks exist only while the stock held an L1 line (its active minutes); volume and high run all day regardless,
as IBKR's day counters do.

Minute bars for priming come from the same prints (price-setting prints set open / high / low / close, every
trade adds volume): one source for the whole day.
"""
from __future__ import annotations

import math
from array import array
from collections.abc import Iterable
from dataclasses import dataclass, field

from constants_hod_momo import HOD_MOMO_REBUILD_L1_TICK_SEC

# (minute start, open, high, low, close, volume)
Bar = tuple[int, float, float, float, float, float]


@dataclass
class SymbolDay:
    symbol: str
    ts: array = field(default_factory=lambda: array("d"))
    price: array = field(default_factory=lambda: array("d"))
    volume: array = field(default_factory=lambda: array("d"))
    high: array = field(default_factory=lambda: array("d"))
    bars: list[Bar] = field(default_factory=list)
    prints: int = 0

    def __len__(self) -> int:
        return len(self.ts)


def build(symbol: str, prints: Iterable[tuple[int, int, float, float, bool]], active_minutes: Iterable[int]) -> SymbolDay:
    """``prints`` are ``(ns, sequence, price, size, sets_price)`` in SIP time order (``inputs.TradeRead``)."""
    step = float(HOD_MOMO_REBUILD_L1_TICK_SEC)
    active = set(int(m) for m in active_minutes)
    out = SymbolDay(symbol)
    cum = 0.0
    high = 0.0
    bucket: int | None = None
    last: float | None = None
    bar: list[float] | None = None          # [minute, open, high, low, close, volume]

    def flush_tick() -> None:
        if bucket is None or last is None:
            return
        at = (bucket + 1) * step
        if int(at - step) // 60 * 60 in active:
            out.ts.append(at)
            out.price.append(last)
            out.volume.append(cum)
            out.high.append(high)

    for ns, _seq, price, size, sets in prints:
        out.prints += 1
        sec = ns / 1e9
        minute = int(sec) // 60 * 60
        if bar is None or bar[0] != minute:
            if bar is not None and bar[1] is not None:
                out.bars.append(tuple(bar))       # type: ignore[arg-type]
            bar = [minute, None, None, None, None, 0.0]
        bar[5] += size
        here = math.floor(sec / step)
        if here != bucket:
            flush_tick()
            bucket, last = here, None
        cum += size
        if sets and price > 0:
            last = price
            high = max(high, price)
            if bar[1] is None:
                bar[1] = bar[2] = bar[3] = price
            bar[2] = max(bar[2], price)
            bar[3] = min(bar[3], price)
            bar[4] = price
    flush_tick()
    if bar is not None and bar[1] is not None:
        out.bars.append(tuple(bar))               # type: ignore[arg-type]
    return out
