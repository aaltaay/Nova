"""The day's support and resistance for one symbol (ADR 036 amendment 2026-09-30). Pure.

Three maps, each read from the candles of the chart it belongs on (operator report 2026-09-30: a
"double top" two 1-minute candles made inside one 5-minute candle was drawn on the 5-minute chart,
which shows one top):

- **intraday** (today's map from the session's one-minute candles): the high and low of day, the
  premarket high, the 09:30 open, VWAP, tops and bottoms tested twice or more, the round numbers
  (``rounds``: the half and whole dollars up to $25, coarser over it), and yesterday's high, low and
  close. The plan reads it (Room, the levels between stop and
  target; trial T7 is registered on it), and the 1-minute pane draws its nearest tops and bottoms.
- **five_minute** (the 5-minute pane): the same day read from 5-minute candles made of those minutes --
  the high and low of day, the premarket high, the open, and tops and bottoms two separate 5-minute
  candles tested; a round number only where it falls in one of those zones. No VWAP (the chart
  draws its own line) and nothing from yesterday (the Full Day pane's).
- **daily** (the Full Day pane): daily highs and lows touched twice or more in the last sessions, the
  older daily highs above the price ("look left and up"), unfilled gaps, the 200-day average, and
  yesterday's levels.

Levels close together merge into one **zone** that lists every reason it holds. Nothing here decides a
trade: ``level_notes`` says what stands between the plan's entry, stop and target. A bar is ``{t, o, h, l, c, v}`` (``t`` epoch seconds),
oldest first, closed bars only; a daily bar is ``{d, o, h, l, c, v}``.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_stock_read import (
    STOCK_READ_DAILY_LEVEL_SESSIONS,
    STOCK_READ_DAILY_LEVEL_TOUCH_PCT,
    STOCK_READ_DAILY_MERGE_PCT,
    STOCK_READ_DAILY_STAIR_MAX,
    STOCK_READ_LEVEL_AT_MIN,
    STOCK_READ_LEVEL_AT_PCT,
    STOCK_READ_LEVEL_MERGE_MIN,
    STOCK_READ_LEVEL_MERGE_PCT,
    STOCK_READ_LEVEL_MIN_TOUCHES,
    STOCK_READ_LEVEL_ROUND_SPAN_PCT,
    STOCK_READ_LEVEL_STUDY,
    STOCK_READ_LEVEL_SWING_BARS,
    STOCK_READ_LEVEL_TOUCH_MIN,
    STOCK_READ_LEVEL_TOUCH_PCT,
    STOCK_READ_LEVELS_SCHEMA_VERSION,
)
from stock_read import rounds

ET = ZoneInfo("America/New_York")
EPS = 1e-9
REGULAR_OPEN_MIN = 9 * 60 + 30
CENT = 0.01                     # a print 1c past a level is through it
# How much a member holds, for ordering and for which zones a chart draws first.
WEIGHT = {"whole": 3, "hod": 3, "half": 2, "lod": 2, "pmh": 2, "open": 2, "vwap": 2, "yday_high": 2,
          "yday_low": 2, "prior_close": 2, "top": 2, "bottom": 2, "daily_highs": 1, "daily_lows": 1,
          "daily_high": 1, "gap": 1, "sma200": 1}
COUNTED = {"top", "bottom", "daily_highs", "daily_lows"}      # these weigh their touches (up to four)
ROUND_KINDS = {"whole", "half"}
WORDS = {"hod": "HOD", "lod": "LOD", "pmh": "PMH", "open": "open", "vwap": "VWAP", "yday_high": "yday high",
         "yday_low": "yday low", "prior_close": "prior close", "daily_high": "daily high", "gap": "gap",
         "sma200": "200-day avg"}


def px(p: float) -> str:
    return f"{p:.2f}" if p >= 1 else f"{p:.4f}"


def hhmm(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), ET).strftime("%H:%M")


def _mmdd(d: str) -> str:
    x = datetime.fromisoformat(d)
    return f"{x.strftime('%b')} {x.day}"


def member(kind: str, price: float, *, touches: int | None = None, times: list[float] | None = None,
           dates: list[str] | None = None, note: str | None = None) -> dict[str, Any]:
    return {"kind": kind, "price": round(float(price), 4), "label": word(kind, float(price), touches),
            "touches": touches, "times": [float(t) for t in times or []], "dates": list(dates or []), "note": note}


def word(kind: str, price: float, touches: int | None) -> str:
    """A member in a few words: "$7.50", "top ×8", "daily lows ×4", "HOD"."""
    if kind in ROUND_KINDS:
        return f"${price:.2f}"
    n = touches or 0
    if kind in ("top", "bottom"):
        return f"{kind} ×{n}" if n >= 4 else f"{'triple' if n == 3 else 'double'} {kind}"
    if kind in ("daily_highs", "daily_lows"):
        return f"{kind.replace('_', ' ')} ×{n}"
    return WORDS.get(kind, kind)


# -- finding the levels -------------------------------------------------------------------------------

def swings(bars: list[dict[str, Any]], key: str, sign: int, side: int = STOCK_READ_LEVEL_SWING_BARS) -> list[tuple[float, float]]:
    """``(price, t)`` of each swing high (``sign`` 1, ``key`` "h") or low (-1, "l"): over (under) the
    ``side`` candles before it and at least even with the ``side`` after it, so a run of equal highs
    counts once. The last ``side`` candles cannot be one yet."""
    out: list[tuple[float, float]] = []
    vals = [float(b[key]) * sign for b in bars]
    for i in range(side, len(bars) - side):
        v = vals[i]
        if v > max(vals[i - side:i]) + EPS and v >= max(vals[i + 1:i + side + 1]) - EPS:
            out.append((float(bars[i][key]), float(bars[i]["t"])))
    return out


def clusters(points: list[tuple[float, Any]], tol_pct: float, tol_min: float) -> list[list[tuple[float, Any]]]:
    """Points within ``max(tol_min, tol_pct x price)`` of their group's mean price, cheapest first."""
    groups: list[list[tuple[float, Any]]] = []
    for p in sorted(points, key=lambda x: x[0]):
        if groups:
            g = groups[-1]
            mean = sum(x[0] for x in g) / len(g)
            if p[0] - mean <= max(tol_min, tol_pct * p[0]) + EPS:
                g.append(p)
                continue
        groups.append([p])
    return groups


def rounds_near(rnd: rounds.Rounds, span_pct: float = STOCK_READ_LEVEL_ROUND_SPAN_PCT) -> list[float]:
    """Every round number of the price's scale within ``span_pct`` of it."""
    step, price = rnd.minor, rnd.price
    lo, hi = price * (1 - span_pct), price * (1 + span_pct)
    k = max(1, math.ceil(lo / step - EPS))
    out = []
    while k * step <= hi + EPS:
        out.append(round(k * step, 2))
        k += 1
    return out


def round_members(price: float | None) -> list[dict[str, Any]]:
    """The round numbers near the price as members: ``whole`` the heavier kind (a whole dollar, a $10
    round number), ``half`` the lighter (a half dollar, a $5 round number)."""
    rnd = rounds.of(price)
    if rnd is None:
        return []
    return [member("whole" if rnd.is_major(p) else "half", p, note=rnd.name(p)) for p in rounds_near(rnd)]


def candle_members(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The levels the session's candles show, whatever their length: the high and low of day, the
    premarket high, the 09:30 open, and the tops and bottoms tested twice or more."""
    out: list[dict[str, Any]] = []
    if bars:
        top = max(bars, key=lambda b: float(b["h"]))
        low = min(bars, key=lambda b: float(b["l"]))
        out.append(member("hod", top["h"], times=[top["t"]], note=f"high of day at {hhmm(top['t'])}"))
        out.append(member("lod", low["l"], times=[low["t"]], note=f"low of day at {hhmm(low['t'])}"))
        pre = [b for b in bars if _minute(b["t"]) < REGULAR_OPEN_MIN]
        reg = [b for b in bars if _minute(b["t"]) >= REGULAR_OPEN_MIN]
        if pre and reg:
            ph = max(pre, key=lambda b: float(b["h"]))
            out.append(member("pmh", ph["h"], times=[ph["t"]], note=f"premarket high at {hhmm(ph['t'])}"))
        if reg and _minute(reg[0]["t"]) == REGULAR_OPEN_MIN:
            out.append(member("open", reg[0]["o"], times=[reg[0]["t"]], note="the 09:30 open"))
        for key, sign, kind in (("h", 1, "top"), ("l", -1, "bottom")):
            for g in clusters(swings(bars, key, sign), STOCK_READ_LEVEL_TOUCH_PCT, STOCK_READ_LEVEL_TOUCH_MIN):
                if len(g) < STOCK_READ_LEVEL_MIN_TOUCHES:
                    continue
                edge = max(x[0] for x in g) if sign > 0 else min(x[0] for x in g)
                times = sorted(x[1] for x in g)
                out.append(member(kind, edge, touches=len(g), times=times,
                                  note=f"tested {len(g)} times: " + ", ".join(hhmm(t) for t in times)))
    return out


def intraday_members(bars: list[dict[str, Any]], *, price: float | None, vwap: float | None,
                     yday: dict[str, Any] | None, prior_close: float | None) -> list[dict[str, Any]]:
    """Today's levels from the session's closed one-minute bars (04:00 ET on)."""
    out = candle_members(bars)
    if vwap is not None:
        out.append(member("vwap", vwap, note="the chart's session VWAP"))
    if yday:
        out.append(member("yday_high", yday["h"], dates=[yday["d"]], note=f"high of {_mmdd(yday['d'])} (with extended hours)"))
        out.append(member("yday_low", yday["l"], dates=[yday["d"]], note=f"low of {_mmdd(yday['d'])} (with extended hours)"))
    if prior_close is not None:
        out.append(member("prior_close", prior_close, note="the regular session's close"))
    return out + round_members(price)


FIVE_MIN_SEC = 300


def five_minute_bars(bars: list[dict[str, Any]], now: float) -> list[dict[str, Any]]:
    """The session's 5-minute candles made from its closed one-minute bars: on the clock (:00, :05 ...),
    each one complete once its five minutes are over; five minutes without a trade make no candle."""
    out: list[dict[str, Any]] = []
    for b in bars:
        t0 = float(int(float(b["t"]) // FIVE_MIN_SEC) * FIVE_MIN_SEC)
        v = float(b.get("v") or 0)
        if out and out[-1]["t"] == t0:
            c = out[-1]
            c["h"] = max(c["h"], float(b["h"]))
            c["l"] = min(c["l"], float(b["l"]))
            c["c"] = float(b["c"])
            c["v"] += v
        else:
            out.append({"t": t0, "o": float(b["o"]), "h": float(b["h"]), "l": float(b["l"]), "c": float(b["c"]), "v": v})
    return [c for c in out if c["t"] + FIVE_MIN_SEC <= now + EPS]


def five_minute_members(bars5: list[dict[str, Any]], *, price: float | None) -> list[dict[str, Any]]:
    """The 5-minute chart's levels: what its candles show, and the round numbers near the price (kept
    only where one falls in a zone with something else, ``build``)."""
    out = candle_members(bars5)
    return out + round_members(price) if out else out


def _minute(ts: float) -> int:
    t = datetime.fromtimestamp(float(ts), ET)
    return t.hour * 60 + t.minute


def unfilled_gaps(daily: list[dict[str, Any]], today: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The part of each gap between two sessions that no later session (today's included) traded:
    ``{lo, hi, since}``."""
    later_all = daily + ([today] if today else [])
    out = []
    for i in range(1, len(daily)):
        a, b = daily[i - 1], daily[i]
        if float(b["l"]) > float(a["h"]) + EPS:
            lo, hi = float(a["h"]), float(b["l"])
        elif float(b["h"]) < float(a["l"]) - EPS:
            lo, hi = float(b["h"]), float(a["l"])
        else:
            continue
        for s in later_all[i + 1:]:
            sl, sh = float(s["l"]), float(s["h"])
            if sl <= lo and sh >= hi:
                lo = hi
                break
            if sl <= lo < sh:
                lo = sh
            if sl < hi <= sh:
                hi = sl
            if lo >= hi:
                break
        if hi - lo > EPS:
            out.append({"lo": round(lo, 4), "hi": round(hi, 4), "since": b["d"]})
    return out


def daily_members(daily: list[dict[str, Any]], *, price: float | None, today: str,
                  sma200: float | None = None) -> list[dict[str, Any]]:
    """The Full Day chart's levels from the stored daily bars before ``today``."""
    before = [b for b in daily if b["d"] < today]
    look = before[-STOCK_READ_DAILY_LEVEL_SESSIONS:]
    out: list[dict[str, Any]] = []
    for key, kind in (("h", "daily_highs"), ("l", "daily_lows")):
        for g in clusters([(float(b[key]), b["d"]) for b in look], STOCK_READ_DAILY_LEVEL_TOUCH_PCT, STOCK_READ_LEVEL_TOUCH_MIN):
            if len(g) < STOCK_READ_LEVEL_MIN_TOUCHES:
                continue
            edge = max(x[0] for x in g) if key == "h" else min(x[0] for x in g)
            dates = sorted(x[1] for x in g)
            out.append(member(kind, edge, touches=len(g), dates=dates, note=", ".join(_mmdd(d) for d in dates)))
    if price is not None:
        taken = [m["price"] for m in out if m["kind"] == "daily_highs"]
        top, kept = -math.inf, 0
        for b in reversed(look):
            h = float(b["h"])
            if h <= top + EPS:
                continue
            top = h
            if h > price + EPS and not any(abs(h - t) <= STOCK_READ_DAILY_LEVEL_TOUCH_PCT * h for t in taken):
                out.append(member("daily_high", h, dates=[b["d"]], note=f"high of {_mmdd(b['d'])}"))
                kept += 1
                if kept >= STOCK_READ_DAILY_STAIR_MAX:
                    break
    for g in unfilled_gaps(look):
        out.append(member("gap", g["lo"], note=f"unfilled gap {px(g['lo'])}-{px(g['hi'])} since {_mmdd(g['since'])}")
                   | {"hi": g["hi"]})
    if sma200 is not None:
        out.append(member("sma200", sma200, note="200-day average (daily closes after hours)"))
    if before:
        y = before[-1]
        out.append(member("yday_high", y["h"], dates=[y["d"]], note=f"high of {_mmdd(y['d'])}"))
        out.append(member("yday_low", y["l"], dates=[y["d"]], note=f"low of {_mmdd(y['d'])}"))
    return out


# -- zones ----------------------------------------------------------------------------------------------

def strength(members: list[dict[str, Any]]) -> int:
    return sum(WEIGHT.get(m["kind"], 1) * (min(m.get("touches") or 1, 4) if m["kind"] in COUNTED else 1)
               for m in members)


def grouped(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per counted kind in a zone: two top clusters 2c apart read "top ×8", not "top ×5 ·
    triple top". The zone keeps every member for its hover."""
    out: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for m in members:
        if m["kind"] not in COUNTED:
            out.append(m)
            continue
        have = seen.get(m["kind"])
        if have is None:
            seen[m["kind"]] = have = dict(m)
            out.append(have)
            continue
        high = m["kind"] in ("top", "daily_highs")
        have["touches"] = (have.get("touches") or 0) + (m.get("touches") or 0)
        have["price"] = max(have["price"], m["price"]) if high else min(have["price"], m["price"])
    for m in seen.values():
        m["label"] = word(m["kind"], m["price"], m["touches"])
    return out


def zone_label(members: list[dict[str, Any]], price: float) -> tuple[str, str]:
    """``(label, tag)``: every reason, strongest first ("$7.50 · top ×8 · VWAP"), and the short form."""
    ms = sorted(grouped(members), key=lambda m: (-WEIGHT.get(m["kind"], 1) * (min(m.get("touches") or 1, 9)
                                                                               if m["kind"] in COUNTED else 1), m["price"]))
    rnd = next((m for m in ms if m["kind"] in ROUND_KINDS), None)
    hod = next((m for m in ms if m["kind"] in ("hod", "lod")), None)
    head = rnd["label"] if rnd else f"{hod['label']} {px(hod['price'])}" if hod else px(price)
    rest = [m["label"] for m in ms if m is not rnd and m is not hod]
    return " · ".join([head, *rest]), head if (rnd or hod) else f"{ms[0]['label']} {px(price)}"


def zones(members: list[dict[str, Any]], *, price: float | None, home: str, merge_pct: float,
          merge_min: float = STOCK_READ_LEVEL_MERGE_MIN) -> list[dict[str, Any]]:
    """Members within ``max(merge_min, merge_pct x price)`` of the zone's top are one zone, a zone at
    most twice that wide; highest first. ``side`` is where the zone sits against the price and
    ``price`` its edge nearest to it."""
    groups: list[list[dict[str, Any]]] = []
    for m in sorted(members, key=lambda x: x["price"]):
        tol = max(merge_min, merge_pct * m["price"])
        if groups:
            g = groups[-1]
            lo = min(x["price"] for x in g)
            hi = max(x.get("hi", x["price"]) for x in g)
            if m["price"] - hi <= tol + EPS and max(hi, m.get("hi", m["price"])) - lo <= 2 * tol + EPS:
                g.append(m)
                continue
        groups.append([m])
    out = []
    for g in groups:
        lo = min(x["price"] for x in g)
        hi = max(x.get("hi", x["price"]) for x in g)
        if price is None:
            side, edge = "unknown", lo
        else:
            at = max(STOCK_READ_LEVEL_AT_MIN, STOCK_READ_LEVEL_AT_PCT * price)
            side = "above" if lo > price + at else "below" if hi < price - at else "at"
            edge = lo if side == "above" else hi if side == "below" else min((lo, hi), key=lambda p: abs(p - price))
        label, tag = zone_label(g, edge)
        clean = [{k: v for k, v in x.items() if k != "hi"} for x in g]
        out.append({"id": f"{home}:{lo:.4f}", "lo": round(lo, 4), "hi": round(hi, 4), "price": round(edge, 4),
                    "side": side, "strength": strength(g), "label": label, "tag": tag, "home": home,
                    "members": clean})
    out.sort(key=lambda z: -z["lo"])
    return out


def build(bars: list[dict[str, Any]], daily: list[dict[str, Any]] | None, *, price: float | None,
          prior_close: float | None, vwap: float | None, now: float, sma200: float | None = None,
          daily_error: str | None = None) -> dict[str, Any]:
    """The level map the read carries: ``{schema_version, price, rounds, intraday, five_minute, daily,
    daily_sessions, daily_error, study}``. ``bars`` are the session's closed one-minute bars; ``rounds``
    is the price's scale of round numbers (``rounds.Rounds.wire``), None without a price."""
    today = datetime.fromtimestamp(now, ET).date().isoformat()
    past = [b for b in (daily or []) if b["d"] < today]
    yday = past[-1] if past else None
    intra = intraday_members(bars, price=price, vwap=vwap, yday=yday, prior_close=prior_close)
    day = daily_members(past, price=price, today=today, sma200=sma200) if daily is not None else []
    five = five_minute_members(five_minute_bars(bars, now), price=price)
    five_zones = [z for z in zones(five, price=price, home="five_minute", merge_pct=STOCK_READ_LEVEL_MERGE_PCT)
                  if any(m["kind"] not in ROUND_KINDS for m in z["members"])]
    return {
        "schema_version": STOCK_READ_LEVELS_SCHEMA_VERSION,
        "price": price,
        "rounds": rnd.wire() if (rnd := rounds.of(price)) else None,
        "intraday": zones(intra, price=price, home="intraday", merge_pct=STOCK_READ_LEVEL_MERGE_PCT),
        "five_minute": five_zones,
        "daily": zones(day, price=price, home="daily", merge_pct=STOCK_READ_DAILY_MERGE_PCT),
        "daily_sessions": len(past[-STOCK_READ_DAILY_LEVEL_SESSIONS:]),
        "daily_error": daily_error if daily is None else None,
        "study": {k: list(v) if isinstance(v, tuple) else v for k, v in STOCK_READ_LEVEL_STUDY.items()},
    }
