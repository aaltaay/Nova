"""The read while you hold a stock short (ADR 048: "the This trade card, mirrored"). Pure.

``held`` measures a long from the price up; a short runs the other way, so every rule is the mirror:

- **The buy stop**: Nova's when Nova holds the cover, else yours, else proposed (the highest high of the
  last few closed 1-minute candles over the price, else 1c over the nearest zone of today's map over it).
  It printed when a price at or over it traded since you shorted.
- **Broke and through**, on the stock's own round scale: a round is *broke* when a 1-minute candle since
  you shorted closed 1c or more under it after the ``STOCK_READ_ROUND_FRESH_BARS`` closes before it stayed
  over it; *through* when the price stands under it and a candle's low crossed it but no close has.
- **Lower**: the lowest broke round whose ``round + near`` is under the stop and over the price ("Lower
  stop to 5.55, 5c over $5.50"). Down only.
- **The cover target**: the average less ``STOCK_READ_TARGET_R`` x the risk you measure R in.
- **The ladder**: the stop and the average over the price, the broke and through rounds, a resistance, the
  price, and the next two zones under it -- highest price first, as the long ladder.

Nothing here places or moves an order. ``stock_mode.exit_trade`` lowers Nova's own buy stop by the same
rule (``lower_for``).
"""
from __future__ import annotations

from typing import Any

from constants_stock_read import (
    STOCK_READ_HELD_BROKE_ROWS,
    STOCK_READ_HELD_SCHEMA_VERSION,
    STOCK_READ_MANUAL_STOP_BARS,
    STOCK_READ_ROUND_CROSS_SEC,
    STOCK_READ_ROUND_FRESH_BARS,
    STOCK_READ_TARGET_R,
)
from stock_read import level_notes_short, rounds
from stock_read.indicators import manual_stop_short
from stock_read.level_map import CENT, EPS, hhmm, px
from stock_read.level_notes import _cents

MIN = 60
_ORDER = {"stop": 0, "cost": 1, "resistance": 2, "broke": 3, "through": 4, "now": 5, "next": 6, "then": 7}


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def crosses(bars: list[dict[str, Any]], rnd: rounds.Rounds | None, since: float | None, price: float | None,
            fresh: int = STOCK_READ_ROUND_FRESH_BARS) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """``(broke, through)`` for the rounds the price stands under, from the closed 1-minute ``bars`` (oldest
    first) of candles that closed after ``since``. Broke: ``{round, at, close}``, lowest round first;
    through: ``{round, at, low}``."""
    if rnd is None or since is None or price is None or not bars:
        return [], []
    after = [i for i, b in enumerate(bars) if float(b["t"]) + MIN > since]
    if not after:
        return [], []
    lo = min(min(float(bars[i]["l"]) for i in after), price)
    hi = max(float(bars[i]["h"]) for i in after)
    broke: list[dict[str, Any]] = []
    through: list[dict[str, Any]] = []
    for r in rnd.between(lo - rnd.minor, hi + rnd.minor):
        if price > r - EPS:
            continue                       # the price does not stand under it
        closed = None
        for i in after:
            c = float(bars[i]["c"])
            before = [float(b["c"]) for b in bars[max(0, i - fresh):i]]
            if c <= r - CENT + EPS and before and len(before) >= fresh and min(before) > r + EPS:
                closed = {"round": r, "at": float(bars[i]["t"]) + MIN, "close": round(c, 4)}
                break
        if closed:
            broke.append(closed)
            continue
        if any(float(bars[i]["c"]) <= r - CENT + EPS for i in after):
            continue                       # closed under it, but not fresh: neither
        low = next((bars[i] for i in after if float(bars[i]["l"]) <= r - CENT + EPS), None)
        if low is not None or price <= r - CENT + EPS:
            through.append({"round": r, "at": float(low["t"]) if low else None,
                            "low": round(float(low["l"]), 4) if low else None})
    broke.sort(key=lambda b: b["round"])
    through.sort(key=lambda b: b["round"])
    return broke, through


def lower_for(broke: list[dict[str, Any]], rnd: rounds.Rounds | None, stop: float | None,
              price: float | None) -> dict[str, Any] | None:
    """The buy stop a broke round offers: ``round + near`` (5c over a half dollar), only under the stop and
    over the price. ``{to, round, at, text}`` or None."""
    if rnd is None or price is None:
        return None
    for b in broke:                       # lowest round first
        to = round(b["round"] + rnd.near, 4)
        if to > price + EPS and (stop is None or to < stop - EPS):
            return {"to": to, "round": b["round"], "at": b["at"],
                    "text": f"Lower the stop to {px(to)}, {_cents(rnd.near)} over ${b['round']:.2f}"}
    return None


def proposed_stop(bars: list[dict[str, Any]], price: float, intraday: list[dict[str, Any]]) -> tuple[float, str] | None:
    """The hand short's buy stop over the price: the last candles' high, else 1c over the nearest zone."""
    high = manual_stop_short(bars, price, STOCK_READ_MANUAL_STOP_BARS)
    if high is not None:
        return high, f"the highest high of the last {STOCK_READ_MANUAL_STOP_BARS} closed 1-min candles"
    over = sorted((z for z in intraday if z["lo"] > price + EPS), key=lambda z: z["lo"])
    if over:
        z = over[0]
        return round(float(z["hi"]) + CENT, 4), f"1c over {z['label']}"
    return None


def _stop(bars: list[dict[str, Any]], price: float | None, intraday: list[dict[str, Any]],
          yours: float | None, nova: float | None, since: float | None) -> dict[str, Any] | None:
    if nova is not None:
        price_s, source, rule = nova, "nova", "Nova's resting buy stop"
    elif yours is not None:
        price_s, source, rule = yours, "yours", "your buy stop"
    elif price is not None:
        got = proposed_stop(bars, price, intraday)
        if got is None:
            return None
        price_s, rule = got
        source = "proposed"
    else:
        return None
    # The stop printed: the price is at or over it now, or the last closed candle since you shorted reached it.
    last = bars[-1] if bars and since is not None and float(bars[-1]["t"]) + MIN > since else None
    printed = (price is not None and price >= price_s - EPS) or (last is not None and float(last["h"]) >= price_s - EPS)
    return {"price": round(price_s, 4), "source": source, "rule": rule, "printed": bool(printed)}


def _row(role: str, p: float, text: str, avg: float, qty: float, risk: float | None) -> dict[str, Any]:
    return {"role": role, "price": round(p, 4), "text": text,
            "r": round((avg - p) / risk, 2) if risk else None, "usd": round((avg - p) * qty, 2)}


def _levels(price: float | None, risk: float | None, stop: dict[str, Any] | None, target: dict[str, Any] | None,
            below: list[dict[str, Any]], broke: list[dict[str, Any]], through: list[dict[str, Any]],
            bars: list[dict[str, Any]], rnd: rounds.Rounds | None, now: float) -> dict[str, Any]:
    """The card's rows, measured from the price, downward."""
    if price is None:
        room = {"state": "unknown", "text": "Room is not known: no price", "detail": None, "trial": None}
    elif not below:
        room = {"state": "info", "text": "No level of today's map under the price", "detail": None, "trial": None}
    elif not risk:
        room = {"state": "info", "text": f"{_cents(price - below[0]['price'])} to {below[0]['tag']}",
                "detail": "R is not known: no buy stop over your average.", "trial": None}
    else:
        r = (price - float(below[0]["price"])) / risk
        room = {"state": "info", "text": f"{r:.1f}R to {below[0]['tag']}, from the price",
                "detail": f"R is your {px(risk)} risk a share, measured from the price.", "trial": None,
                "r": round(r, 2)}
    tnote = None
    if target is not None:
        if target.get("traded_at"):
            tnote = {"state": "ok", "text": f"{px(target['price'])} ({STOCK_READ_TARGET_R:g}R) traded at "
                                            f"{hhmm(target['traded_at'])}: you are past it", "detail": target["rule"]}
        elif price is not None:
            tnote = {"state": "info", "text": f"{px(target['price'])} ({STOCK_READ_TARGET_R:g}R) is "
                                              f"{_cents(price - target['price'])} below", "detail": target["rule"]}
    snote = level_notes_short.stop_note(stop["price"], price, rnd) if stop and price is not None else None
    nxt = level_notes_short.round_notes(bars, price=price, entry=None, now=now, rnd=rnd)[0] if price is not None else None
    recent = None
    fresh_broke = [b for b in broke if now - b["at"] <= STOCK_READ_ROUND_CROSS_SEC]
    if fresh_broke:
        b = fresh_broke[0]
        recent = {"state": "ok", "round": b["round"], "at": b["at"],
                  "text": f"Lost ${b['round']:.2f}: the {hhmm(b['at'] - MIN)} candle closed {px(b['close'])}",
                  "detail": "A candle closed under it: a buy stop over it is the lower offered."}
    elif through:
        t = through[0]
        when = f" at {hhmm(t['at'])}" if t.get("at") else ""
        recent = {"state": "warn", "round": t["round"], "at": t.get("at"),
                  "text": f"${t['round']:.2f} traded through{when}, no candle closed under it yet",
                  "detail": "A print under a round is not a break: only a close moves a stop."}
    return {"room": room, "target": tnote, "stop": snote, "next": nxt, "recent": recent}


def build(*, bars: list[dict[str, Any]], price: float | None, level_map: dict[str, Any] | None, avg: float,
          qty: float, now: float, since: float | None = None, stop: float | None = None,
          nova_stop: float | None = None, risk: float | None = None,
          checks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """``held`` for a short you hold (``qty`` the shares short). ``stop``: your buy stop; ``nova_stop``: Nova's
    resting buy stop when it holds the cover; ``risk``: the risk a share you measure R in."""
    lm = level_map or {}
    intraday = list(lm.get("intraday") or [])
    rnd = rounds.of(lm.get("price")) or rounds.of(price) or rounds.of(avg)
    st = _stop(bars, price, intraday, _f(stop), _f(nova_stop), since)
    stop_px = st["price"] if st else None
    risk_v = _f(risk)
    if risk_v is None and stop_px is not None and stop_px > avg + EPS:
        risk_v = round(stop_px - avg, 4)
    broke, through = crosses(bars, rnd, since, price)
    down = lower_for(broke, rnd, stop_px, price)
    target = None
    if risk_v and avg - STOCK_READ_TARGET_R * risk_v > 0:
        t_px = round(avg - STOCK_READ_TARGET_R * risk_v, 4)
        after = [b for b in bars if since is not None and float(b["t"]) + MIN > since]
        hit = next((float(b["t"]) for b in after if float(b["l"]) <= t_px + EPS), None)
        target = {"price": t_px, "rule": f"your average - {STOCK_READ_TARGET_R:g} x {px(risk_v)}", "traded_at": hit}
    below = sorted((z for z in intraday if price is not None and float(z["hi"]) < price - EPS),
                   key=lambda z: -float(z["hi"]))
    above = sorted((z for z in intraday if price is not None and float(z["lo"]) > price + EPS
                    and (stop_px is None or float(z["hi"]) < stop_px - EPS)), key=lambda z: float(z["lo"]))
    ladder: list[dict[str, Any]] = []
    for z, role in zip(below[:2], ("next", "then"), strict=False):
        ladder.append(_row(role, float(z["price"]), z["label"], avg, qty, risk_v))
    if price is not None:
        ladder.append(_row("now", price, f"{(avg - price) * qty:+,.2f} open", avg, qty, risk_v))
    for t in through:
        when = f" at {hhmm(t['at'])}" if t.get("at") else ""
        ladder.append({"role": "through", "price": t["round"],
                       "text": f"traded through{when}, no candle closed under it yet", "r": None, "usd": None})
    for b in broke[:STOCK_READ_HELD_BROKE_ROWS]:
        ladder.append({"role": "broke", "price": b["round"],
                       "text": f"the {hhmm(b['at'] - MIN)} candle closed {px(b['close'])} under it", "r": None, "usd": None})
    if above and not any(stop_px is None or b["round"] < stop_px for b in broke):
        ladder.append(_row("resistance", float(above[0]["price"]), above[0]["label"], avg, qty, risk_v))
    if st:
        ladder.append(_row("stop", stop_px, st["rule"], avg, qty, risk_v))
    ladder.append({"role": "cost", "price": round(avg, 4), "text": f"your average, {qty:g} sh short", "r": 0.0, "usd": 0.0})
    ladder.sort(key=lambda row: (-row["price"], _ORDER[row["role"]]))
    return {
        "schema_version": STOCK_READ_HELD_SCHEMA_VERSION,
        "side": "short",
        "qty": qty,
        "avg": round(avg, 4),
        "price": price,
        "open_usd": round((avg - price) * qty, 2) if price is not None else None,
        "r": round((avg - price) / risk_v, 2) if price is not None and risk_v else None,
        "risk": risk_v,
        "since": since,
        "stop": st,
        "raise": None,
        "lower": down,
        "target": target,
        "ladder": ladder,
        "broke": broke,
        "through": through,
        "levels": _levels(price, risk_v, st, target, [{"price": float(z["hi"]), "tag": z["tag"]} for z in below],
                          broke, through, bars, rnd, now),
        "checks": checks or [],
    }
