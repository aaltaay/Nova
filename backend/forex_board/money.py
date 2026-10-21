"""A CME currency future's money in and out (ADR 061, by ADR 060's rule). Pure: bars in, sums out.

A one-minute bar is up when it closed above the bar before it in IBKR's answer, down when below, flat otherwise (the
first bar, with none before it, is flat). Its notional is volume x average price (its close when IBKR gives no
average) x multiplier for a contract priced in dollars per unit of the currency (6E: dollars per euro, 125,000 euros),
already in dollars. An ``inverted`` contract is worth ``multiplier`` dollars and priced in the currency per dollar
(USD/CNH): its notional is volume x multiplier, and an up bar is the dollar bought -- the currency sold. Sums are
always from the currency's side. Nothing here is estimated: every sum is of trades IBKR reported.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

HOUR = 3600.0
Classified = tuple[float, float, int, float]    # (bar start, notional $, +1 / -1 / 0 for the currency, contracts)


def classify(bars: Sequence[Mapping], multiplier: float, inverted: bool = False) -> list[Classified]:
    out: list[Classified] = []
    prev: float | None = None
    for bar in bars:
        close = bar.get("close")
        volume = float(bar.get("volume") or 0.0)
        price = bar.get("average") or close
        notional = volume * multiplier if inverted else (volume * float(price) * multiplier if price else 0.0)
        sign = 0
        if prev is not None and close is not None:
            sign = 1 if close > prev else -1 if close < prev else 0
        out.append((float(bar["t"]), max(notional, 0.0), -sign if inverted else sign, volume))
        if close is not None:
            prev = close
    return out


def sums(classified: Sequence[Classified], start: float, end: float) -> dict:
    """``{up, down, flat, traded, contracts, bars, last_bar_at}`` of the bars starting in ``[start, end)``, in dollars."""
    up = down = flat = contracts = 0.0
    n = 0
    last = None
    for t, notional, sign, volume in classified:
        if not start <= t < end:
            continue
        n += 1
        last = t
        contracts += volume
        if sign > 0:
            up += notional
        elif sign < 0:
            down += notional
        else:
            flat += notional
    return {"up": up, "down": down, "flat": flat, "traded": up + down + flat, "contracts": contracts, "bars": n,
            "last_bar_at": last}


def pressure_pct(up: float, down: float, traded: float) -> float | None:
    return round((up - down) / traded * 100.0, 2) if traded > 0 else None


def hours(classified: Sequence[Classified], start: float) -> dict[int, list[float]]:
    """``{hour of the day: [net $, traded $]}`` of the bars from ``start`` on, by the hour each started in."""
    out: dict[int, list[float]] = {}
    for t, notional, sign, _volume in classified:
        h = int((t - start) // HOUR)
        if not 0 <= h < 24:
            continue
        row = out.setdefault(h, [0.0, 0.0])
        row[0] += notional * sign
        row[1] += notional
    return out


def levels(bars: Sequence[Mapping], start: float, end: float) -> dict:
    """The future's own price over ``[start, end)``: ``{open, last, last_t, high, low, closes}`` -- ``open`` the last
    close before ``start``, ``closes[h]`` the last close in hour ``h`` (a future moves the currency when IBKR has no
    spot quote, ADR 061 decision 3)."""
    open_level = last = last_t = high = low = None
    closes: list[float | None] = [None] * 24
    for bar in bars:
        t = float(bar["t"])
        close = bar.get("close")
        if close is None:
            continue
        if t < start:
            open_level = float(close)
        elif t < end:
            last, last_t = float(close), t
            closes[int((t - start) // HOUR)] = last
            hi, lo = bar.get("high") or close, bar.get("low") or close
            high = hi if high is None else max(high, hi)
            low = lo if low is None else min(low, lo)
    return {"open": open_level, "last": last, "last_t": last_t, "high": high, "low": low, "closes": closes}


def daily_sums(rows: Sequence[Mapping], sign_of: Mapping[str, int], multiplier: float, inverted: bool) -> dict:
    """The daily rows' money, each day up or down by ``sign_of[date]`` -- the currency's own move that day (a date
    it lacks is flat). Dollars, from the currency's side."""
    up = down = flat = contracts = 0.0
    for r in rows:
        volume = float(r.get("volume") or 0.0)
        price = r.get("average") or r.get("close") or 0.0
        notional = volume * multiplier if inverted else volume * float(price) * multiplier
        contracts += volume
        sign = sign_of.get(r.get("date") or "", 0)
        if sign > 0:
            up += notional
        elif sign < 0:
            down += notional
        else:
            flat += notional
    return {"up": up, "down": down, "flat": flat, "traded": up + down + flat, "contracts": contracts,
            "days": len(rows), "from": rows[0]["date"] if rows else None, "to": rows[-1]["date"] if rows else None}


def day_signs(rows: Sequence[Mapping], per_usd: bool) -> dict[str, int]:
    """``{date: +1 / -1 / 0}`` -- the currency's move each day from consecutive daily closes of its pair (a pair quoted
    per dollar moves the other way)."""
    closes = [r for r in rows if r.get("close")]
    out: dict[str, int] = {}
    for prev, row in zip(closes, closes[1:], strict=False):
        sign = 1 if row["close"] > prev["close"] else -1 if row["close"] < prev["close"] else 0
        out[row["date"]] = -sign if per_usd else sign
    return out


def normal_volume(rows: Sequence[Mapping], days: int) -> float | None:
    """The average contracts of the last ``days`` daily rows; None with fewer than half of them."""
    got = [float(r["volume"]) for r in list(rows)[-days:] if r.get("volume")]
    return sum(got) / len(got) if len(got) >= days / 2 else None
