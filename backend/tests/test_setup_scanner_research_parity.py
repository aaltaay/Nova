"""The live flat-top and red-to-green detectors take the research harness's trades (ADR 031).

The research screens (``research/momentum/backtest_setups.py`` ``find_flat_top``,
``find_red_to_green``, Bot-Trading-Plan section 2f) are the pre-registered rules.
Random days, some shaped like each setup, go through both: the first trade of
each day -- its entry candle, entry and stop -- must be the same. The research
adds one cent of slippage to every entry; the live entry is the price the bot's
limit goes at (the flat-top hold's cent over the close stands for that slippage).

Skipped where the research harness's own dependencies (numpy, pandas, duckdb)
are not installed.
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")
pytest.importorskip("duckdb")

from setup_scanner.bars import Bar  # noqa: E402
from setup_scanner.flat_top import FlatTopDetector, FlatTopParams  # noqa: E402
from setup_scanner.red_to_green import RedToGreenDetector, RedToGreenParams  # noqa: E402

ET = ZoneInfo("America/New_York")
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "research" / "momentum"))
bs = pytest.importorskip("backtest_setups")
SLIP = 0.01
DAY = (2026, 9, 21)
# The research compares its risk to the $0.03 / $0.20 band with no tolerance, so a risk of
# exactly 3 cents can read 2.99999... cents there and be skipped; the live detectors compare
# with a tolerance, as the first pullback's does. Nudging the research's band by half a
# hundredth of a cent makes both read the same cents.
BAND = {"min_stop": 0.03 - 5e-5, "stop_cap": 0.20 + 5e-5}


def _ts(minute: int) -> float:
    return datetime(*DAY, 8, 0, tzinfo=ET).timestamp() + 60 * minute


def _bars(ohlc: list[tuple[float, float, float, float]]) -> list[Bar]:
    return [Bar(_ts(i), round(o, 2), round(h, 2), round(lo, 2), round(c, 2), 10_000) for i, (o, h, lo, c) in
            enumerate(ohlc)]


def _frame(bars: list[Bar]):
    t = [datetime.fromtimestamp(b.t, ET).time() for b in bars]
    return pd.DataFrame({"t": t, "open": [b.o for b in bars], "high": [b.h for b in bars],
                         "low": [b.lo for b in bars], "close": [b.c for b in bars]})


def _candle(rng: random.Random, o: float, drift: float, vol: float) -> tuple[float, float, float, float]:
    c = max(0.5, o + drift + rng.gauss(0, vol))
    h = max(o, c) + abs(rng.gauss(0, vol / 2))
    lo = min(o, c) - abs(rng.gauss(0, vol / 2))
    return o, h, lo, c


def flat_top_day(seed: int) -> list[Bar]:
    """08:00-12:00: a drift, an impulse into a high, a tight base under it, then a coin flip."""
    rng = random.Random(seed)
    px, out = 4.0, []
    for _ in range(rng.randint(60, 110)):
        out.append(_candle(rng, px, 0.0003, 0.012))
        px = out[-1][3]
    for _ in range(rng.randint(3, 6)):                       # the impulse
        out.append(_candle(rng, px, px * rng.uniform(0.006, 0.014), 0.006))
        px = out[-1][3]
    top = max(c[1] for c in out)
    for _ in range(rng.randint(2, 6)):                       # the base: tight, just under the high
        o = px
        c = min(top - 0.005, max(top * (1 - rng.uniform(0.001, 0.02)), o + rng.gauss(0, 0.01)))
        h = min(top - 0.001, max(o, c) + abs(rng.gauss(0, 0.005)))
        lo = min(o, c) - abs(rng.gauss(0, 0.01))
        out.append((o, h, lo, c))
        px = c
    drift = px * rng.choice((0.006, -0.004, 0.0))
    while len(out) < 240:
        out.append(_candle(rng, px, drift if len(out) % 7 else 0.0, 0.012))
        px = out[-1][3]
    return _bars(out)


def red_to_green_day(seed: int) -> list[Bar]:
    """08:00-12:00: a pre-market, the 09:30 open, a dip under it, and a try at the reclaim."""
    rng = random.Random(10_000 + seed)
    px, out = 4.0, []
    for _ in range(90):                                     # 08:00-09:29
        out.append(_candle(rng, px, rng.uniform(-0.001, 0.004), 0.01))
        px = out[-1][3]
    for _ in range(rng.randint(1, 8)):                      # a dip under the open
        out.append(_candle(rng, px, -rng.uniform(0.0, 0.03), 0.012))
        px = out[-1][3]
    while len(out) < 240:
        out.append(_candle(rng, px, rng.uniform(-0.01, 0.02), 0.014))
        px = out[-1][3]
    return _bars(out)


def live_first(det, bars: list[Bar]) -> tuple[int, float, float] | None:
    """The live detector's first trade: (entry candle, entry, stop), fed as a lane feeds it."""
    for k, bar in enumerate(bars):
        if k:
            for px in (bar.o, bar.h):
                for name, view in det.on_price(px, bar.t + 1, bar_open=bar.o):
                    if name == "triggered":
                        s = view["setup"]
                        return k, s["entry"], s["stop"]
        for name, view in det.on_bars(bars[:k + 1]):
            if name == "triggered":
                s = view["setup"]
                return k, s["entry"], s["stop"]
    return None


def research_first(finder, params, bars: list[Bar]) -> tuple[int, float, float] | None:
    trades = finder(bs.Day(_frame(bars), params), params)
    if not trades:
        return None
    t = trades[0]
    return int(t["_k"]), round(t["entry"] - SLIP, 4), round(t["stop0"], 4)


def _agree(a, b) -> bool:
    if a is None or b is None:
        return a is b
    return a[0] == b[0] and abs(a[1] - b[1]) < 1e-6 and abs(a[2] - b[2]) < 1e-6


@pytest.mark.parametrize("entry", ["hold", "break"])
def test_the_flat_top_detector_takes_the_research_trades(entry):
    params = bs.Params(setup="flat_top", ft_entry=entry, slippage=SLIP, **BAND)
    live_params = FlatTopParams(entry_mode=entry, session_start="09:30", entry_cutoff="11:30")
    agree, trades, misses = 0, 0, []
    for seed in range(160):
        bars = flat_top_day(seed)
        want = research_first(bs.find_flat_top, params, bars)
        # The research's "hold" entry is its close plus its cent of slippage, the live one the close plus
        # the entry offset: the same number; the research's "break" entry carries the cent on top.
        got = live_first(FlatTopDetector("SYM", p=live_params), bars)
        if entry == "hold" and want is not None:
            want = (want[0], round(want[1] + SLIP, 4), want[2])
        trades += want is not None
        if _agree(want, got):
            agree += 1
        else:
            misses.append((seed, want, got))
    assert trades >= 25, f"too few flat tops in the sample ({trades})"
    assert agree == 160, misses[:5]


def test_the_red_to_green_detector_takes_the_research_trades():
    params = bs.Params(setup="red_to_green", slippage=SLIP, **BAND)
    agree, trades, misses = 0, 0, []
    for seed in range(160):
        bars = red_to_green_day(seed)
        want = research_first(bs.find_red_to_green, params, bars)
        got = live_first(RedToGreenDetector("SYM", p=RedToGreenParams()), bars)
        trades += want is not None
        if _agree(want, got):
            agree += 1
        else:
            misses.append((seed, want, got))
    assert trades >= 25, f"too few reclaims in the sample ({trades})"
    assert agree == 160, misses[:5]


def test_the_frames_times_are_eastern_minutes():
    bars = flat_top_day(0)
    assert _frame(bars)["t"].iloc[0] == dtime(8, 0)
