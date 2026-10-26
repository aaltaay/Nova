"""Money in and out of a market from IBKR's bars (ADR 060). Pure: bars in, sums out.

A bar is up when it closed above the bar before it in IBKR's answer, down when below, flat otherwise (the first bar,
with none before it, is flat). Its notional is volume x the bar's average price (its close when IBKR gives no
average) x the contract multiplier, in the instrument's currency; ``usd`` converts it at IBKR's exchange rate. Only
bars that start inside the market's own session count. Nothing here is estimated: every sum is of trades IBKR
reported.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence

Bar = dict
Classified = tuple[float, float, int]   # (bar start, notional in the instrument's currency, +1 / -1 / 0)
HOUR = 3600.0


def classify(bars: Sequence[Bar], multiplier: float) -> list[Classified]:
    out: list[Classified] = []
    prev: float | None = None
    for bar in bars:
        close = bar.get("close")
        volume = bar.get("volume") or 0.0
        price = bar.get("average") or close
        notional = float(volume) * float(price) * multiplier if price else 0.0
        sign = 0
        if prev is not None and close is not None:
            sign = 1 if close > prev else -1 if close < prev else 0
        out.append((float(bar["t"]), max(notional, 0.0), sign))
        if close is not None:
            prev = close
    return out


def _inside(t: float, segments: Iterable[tuple[float, float]]) -> bool:
    return any(a <= t < b for a, b in segments)


def sums(classified: Sequence[Classified], segments: Sequence[tuple[float, float]]) -> dict:
    """``{up, down, flat, traded, bars, first_bar_at, last_bar_at}`` of the bars inside ``segments``, in the
    instrument's currency."""
    up = down = flat = 0.0
    n = 0
    first = last = None
    for t, notional, sign in classified:
        if not _inside(t, segments):
            continue
        n += 1
        first = t if first is None else first
        last = t
        if sign > 0:
            up += notional
        elif sign < 0:
            down += notional
        else:
            flat += notional
    return {"up": up, "down": down, "flat": flat, "traded": up + down + flat, "bars": n,
            "first_bar_at": first, "last_bar_at": last}


def pressure_pct(up: float, down: float, traded: float) -> float | None:
    return round((up - down) / traded * 100.0, 2) if traded > 0 else None


def hours(classified: Sequence[Classified], segments: Sequence[tuple[float, float]]) -> list[list[float]]:
    """``[[hour start, net, traded]]`` of the bars inside ``segments``, by the hour they started in, oldest first."""
    buckets: dict[float, list[float]] = {}
    for t, notional, sign in classified:
        if not _inside(t, segments):
            continue
        hour = t - (t % HOUR)
        row = buckets.setdefault(hour, [0.0, 0.0])
        row[0] += notional * sign
        row[1] += notional
    return [[h, net, traded] for h, (net, traded) in sorted(buckets.items())]


def last_close_before(bars: Sequence[Bar], end: float, start: float | None = None) -> float | None:
    """The close of the last bar that starts before ``end`` (and at or after ``start``)."""
    found = None
    for bar in bars:
        t = float(bar["t"])
        if t >= end:
            break
        if (start is None or t >= start) and bar.get("close") is not None:
            found = float(bar["close"])
    return found


def move_from_bars(bars: Sequence[Bar], session: Sequence[tuple[float, float]],
                   previous: Sequence[tuple[float, float]] | None) -> dict | None:
    """The session's last close against the previous session's last close: ``{pct, last, prev_close}``."""
    if not session or not previous:
        return None
    last = last_close_before(bars, session[-1][1], session[0][0])
    prior = last_close_before(bars, previous[-1][1], previous[0][0])
    if last is None or not prior:
        return None
    return {"pct": round((last / prior - 1.0) * 100.0, 3), "last": last, "prev_close": prior}


def usd(amount: float | None, usd_per_unit: float | None) -> float | None:
    if amount is None or usd_per_unit is None:
        return None
    return round(amount * usd_per_unit, 2)


def daily_move(rows: Sequence[dict], sessions: int) -> dict | None:
    """The latest daily close against the one ``sessions`` bars earlier: ``{pct, last, prev_close, from, to}``."""
    closes = [r for r in rows if r.get("close")]
    if len(closes) <= sessions:
        return None
    last, base = closes[-1], closes[-1 - sessions]
    return {"pct": round((last["close"] / base["close"] - 1.0) * 100.0, 3), "last": last["close"],
            "prev_close": base["close"], "from": base["date"], "to": last["date"]}


def daily_sums(notional_rows: Sequence[dict], sign_rows: Sequence[dict], sessions: int, multiplier: float) -> dict:
    """The last ``sessions`` daily bars of ``notional_rows``, each up or down by ``sign_rows``' close against its
    close the session before (same date; a date it lacks is flat). In the instrument's currency."""
    sign_close = {r["date"]: r["close"] for r in sign_rows if r.get("close")}
    dates = sorted(sign_close)
    sign_of: dict[str, int] = {}
    for prev_day, day in zip(dates, dates[1:], strict=False):
        a, b = sign_close[prev_day], sign_close[day]
        sign_of[day] = 1 if b > a else -1 if b < a else 0
    rows = [r for r in notional_rows if r.get("close")][-sessions:]
    up = down = flat = 0.0
    for r in rows:
        price = r.get("average") or r.get("close") or 0.0
        notional = float(r.get("volume") or 0.0) * float(price) * multiplier
        sign = sign_of.get(r["date"], 0)
        if sign > 0:
            up += notional
        elif sign < 0:
            down += notional
        else:
            flat += notional
    return {"up": up, "down": down, "flat": flat, "traded": up + down + flat, "sessions": len(rows),
            "from": rows[0]["date"] if rows else None, "to": rows[-1]["date"] if rows else None}
