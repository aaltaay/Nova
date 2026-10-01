"""The 5-minute chart's read on a 1-minute setup (operator ask 2026-09-30: "it's really powerful to have a
1-minute chart align well with the 5-minute chart"; trial T8, ``knowledge/signal-trials-3.json``). Pure.

``context(bars, now)`` makes 5-minute candles from the session's closed one-minute bars -- on the clock
from 04:00 ET (:00, :05 ...), each complete once its five minutes are over, five minutes without a bar
making no candle -- and says whether the 5-minute chart agrees with a long: the last complete candle's
close over the 9-period EMA of the 5-minute closes, and the 5-minute MACD (12, 26, 9) histogram over 0.
The EMAs seed with the first close (``series.ema``), as the in-sample study did
(``F:/Nova/eyes/studies/mtf-alignment-2026-09-30``). ``None`` when no 5-minute candle is complete.

Nothing gates on it: the setup rows and the plan show it, the scanner records it when a setup arms and
when it triggers (``setups.db`` ``tf5_armed`` / ``tf5_trigger``), and trial T8 decides whether "against"
ever becomes a warning.
"""
from __future__ import annotations

from datetime import datetime, time as dtime
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from setup_scanner.bars import Bar
from setup_scanner.series import ema, macd_hist

ET = ZoneInfo("America/New_York")
FIVE_MIN_SEC = 300
SESSION_START = dtime(4, 0)
EMA_PERIOD = 9
EPS = 1e-6


def candles(bars: Sequence[Bar], now: float) -> list[dict[str, float]]:
    """The complete 5-minute candles of the newest bar's session (``{t, o, h, l, c, v}``, oldest first)."""
    if not bars:
        return []
    day = datetime.fromtimestamp(bars[-1].t, ET).date()
    start = datetime.combine(day, SESSION_START, ET).timestamp()
    out: list[dict[str, float]] = []
    for b in bars:
        if b.t < start:
            continue
        t0 = float(int(b.t // FIVE_MIN_SEC) * FIVE_MIN_SEC)
        if out and out[-1]["t"] == t0:
            c = out[-1]
            c["h"] = max(c["h"], b.h)
            c["l"] = min(c["l"], b.lo)
            c["c"] = b.c
            c["v"] += b.v
        else:
            out.append({"t": t0, "o": b.o, "h": b.h, "l": b.lo, "c": b.c, "v": b.v})
    return [c for c in out if c["t"] + FIVE_MIN_SEC <= now + EPS]


def context(bars: Sequence[Bar], now: float) -> dict[str, Any] | None:
    """``{agrees, above_ema9, macd_up, close, ema9, macd_hist, candles, as_of}`` -- ``as_of`` the last
    complete candle's start (epoch seconds) -- or None before the first 5-minute candle is complete."""
    done = candles(bars, now)
    if not done:
        return None
    closes = [c["c"] for c in done]
    e9 = ema(closes, EMA_PERIOD)[-1]
    hist = macd_hist(closes)[-1]
    above, up = closes[-1] > e9, hist > 0
    return {"agrees": above and up, "above_ema9": above, "macd_up": up, "close": round(closes[-1], 4),
            "ema9": round(e9, 4), "macd_hist": round(hist, 6), "candles": len(done), "as_of": done[-1]["t"]}


def words(tf5: dict[str, Any]) -> str:
    """The read in a line: "5m agrees: over its 9 EMA 16.95, MACD up" / "5m against: under its 9 EMA 17.40,
    MACD down"."""
    side = "over" if tf5.get("above_ema9") else "under"
    macd = "up" if tf5.get("macd_up") else "down"
    head = "5m agrees" if tf5.get("agrees") else "5m against"
    return f"{head}: {side} its 9 EMA {float(tf5.get('ema9') or 0):.2f}, MACD {macd}"


def verdict(tf5: Any) -> str:
    """``agrees`` / ``against`` / ``unknown``: how a row's 5-minute read sorts (the scoreboard, trial T8)."""
    if not isinstance(tf5, dict) or not isinstance(tf5.get("agrees"), bool):
        return "unknown"
    return "agrees" if tf5["agrees"] else "against"
