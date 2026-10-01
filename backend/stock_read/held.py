"""The read while you hold the stock (ADR 036 amendment 2026-10-01). Pure.

Operator ask: "If I enter a trade, can it tell me on the chart when I should sell ... if we pass that
level, okay, this is the next level". Fed a position, the plan box measured from the entry: holding APUS
at 6.64 it read "$5.50 is 42c above". This measures from the price.

- **The stop**: Nova's when Nova holds the exit, else yours, else proposed (the hand plan's rule: the
  lowest low of the last few closed 1-minute candles under the price, else 1c under the nearest zone of
  today's map under the price).
- **Broke and through**, on the stock's own round scale (``rounds``): a round is *broke* when a 1-minute
  candle since you held closed 1c or more over it after the ``STOCK_READ_ROUND_FRESH_BARS`` closes before it
  stayed under it; *through* when the price stands over it and a candle's high crossed it but no close has.
  A one-second sweep is at most through (APUS 2026-09-24 08:56:14: 6.02 and back to 5.30 in six seconds).
- **Raise**: the highest broke round whose ``round - near`` is over the stop and under the price. Up only.
- **The target**: the average plus ``STOCK_READ_TARGET_R`` x the risk you measure R in.
- **The ladder**: the next two zones over the price, the price, the through and broke rounds, a support,
  the stop and the average -- highest first.

Nothing here places or moves an order: it says what the levels are. ``stock_mode.exit_trade`` raises
Nova's own stop by the same rule (``raise_for``).
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
from stock_read import rounds
from stock_read.indicators import manual_stop
from stock_read.level_map import CENT, EPS, hhmm, px
from stock_read.level_notes import _cents, round_notes, stop_note

MIN = 60


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def crosses(bars: list[dict[str, Any]], rnd: rounds.Rounds | None, since: float | None, price: float | None,
            fresh: int = STOCK_READ_ROUND_FRESH_BARS) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """``(broke, through)`` for the rounds the price stands over, from the closed 1-minute ``bars`` (oldest
    first) of candles that closed after ``since``. Broke: ``{round, at, close}`` (``at`` when the candle
    closed), highest round first; through: ``{round, at, high}``."""
    if rnd is None or since is None or price is None or not bars:
        return [], []
    after = [i for i, b in enumerate(bars) if float(b["t"]) + MIN > since]
    if not after:
        return [], []
    lo = min(float(bars[i]["l"]) for i in after)
    hi = max(max(float(bars[i]["h"]) for i in after), price)
    broke: list[dict[str, Any]] = []
    through: list[dict[str, Any]] = []
    for r in rnd.between(lo - rnd.minor, hi + rnd.minor):
        if price < r + EPS:
            continue                       # the price does not stand over it
        closed = None
        for i in after:
            c = float(bars[i]["c"])
            before = [float(b["c"]) for b in bars[max(0, i - fresh):i]]
            if c >= r + CENT - EPS and before and len(before) >= fresh and max(before) < r - EPS:
                closed = {"round": r, "at": float(bars[i]["t"]) + MIN, "close": round(c, 4)}
                break
        if closed:
            broke.append(closed)
            continue
        if any(float(bars[i]["c"]) >= r + CENT - EPS for i in after):
            continue                       # closed over it, but not fresh: neither
        high = next((bars[i] for i in after if float(bars[i]["h"]) >= r + CENT - EPS), None)
        if high is not None or price >= r + CENT - EPS:
            through.append({"round": r, "at": float(high["t"]) if high else None,
                            "high": round(float(high["h"]), 4) if high else None})
    broke.sort(key=lambda b: -b["round"])
    through.sort(key=lambda b: -b["round"])
    return broke, through


def raise_for(broke: list[dict[str, Any]], rnd: rounds.Rounds | None, stop: float | None,
              price: float | None) -> dict[str, Any] | None:
    """The stop a broke round offers: ``round - near`` (5c under a half dollar), only over the stop and
    under the price. ``{to, round, at, text}`` or None."""
    if rnd is None or price is None:
        return None
    for b in broke:                       # highest round first
        to = round(b["round"] - rnd.near, 4)
        if to < price - EPS and (stop is None or to > stop + EPS):
            return {"to": to, "round": b["round"], "at": b["at"],
                    "text": f"Raise the stop to {px(to)}, {_cents(rnd.near)} under ${b['round']:.2f}"}
    return None


def proposed_stop(bars: list[dict[str, Any]], price: float, intraday: list[dict[str, Any]]) -> tuple[float, str] | None:
    """The hand plan's stop under the price: the last candles' low, else 1c under the nearest zone."""
    low = manual_stop(bars, price, STOCK_READ_MANUAL_STOP_BARS)
    if low is not None:
        return low, f"the lowest low of the last {STOCK_READ_MANUAL_STOP_BARS} closed 1-min candles"
    under = sorted((z for z in intraday if z["hi"] < price - EPS), key=lambda z: -z["hi"])
    if under:
        z = under[0]
        return round(float(z["lo"]) - CENT, 4), f"1c under {z['label']}"
    return None


def _stop(bars: list[dict[str, Any]], price: float | None, intraday: list[dict[str, Any]],
          yours: float | None, nova: float | None, since: float | None) -> dict[str, Any] | None:
    if nova is not None:
        price_s, source, rule = nova, "nova", "Nova's resting stop"
    elif yours is not None:
        price_s, source, rule = yours, "yours", "your stop"
    elif price is not None:
        got = proposed_stop(bars, price, intraday)
        if got is None:
            return None
        price_s, rule = got
        source = "proposed"
    else:
        return None
    # The stop printed: the price is at or under it now, or the last closed candle since you held reached it.
    last = bars[-1] if bars and since is not None and float(bars[-1]["t"]) + MIN > since else None
    printed = (price is not None and price <= price_s + EPS) or (last is not None and float(last["l"]) <= price_s + EPS)
    return {"price": round(price_s, 4), "source": source, "rule": rule, "printed": bool(printed)}


def _zone_row(z: dict[str, Any], role: str, avg: float, qty: float, risk: float | None) -> dict[str, Any]:
    p = float(z["price"])
    return {"role": role, "price": round(p, 4), "text": z["label"],
            "r": round((p - avg) / risk, 2) if risk else None, "usd": round((p - avg) * qty, 2)}


def _levels(price: float | None, avg: float, risk: float | None, stop: dict[str, Any] | None,
            target: dict[str, Any] | None, above: list[dict[str, Any]], broke: list[dict[str, Any]],
            through: list[dict[str, Any]], bars: list[dict[str, Any]], rnd: rounds.Rounds | None,
            now: float) -> dict[str, Any]:
    """The plan's rows, measured from the price."""
    room: dict[str, Any]
    if price is None:
        room = {"state": "unknown", "text": "Room is not known: no price", "detail": None, "trial": None}
    elif not above:
        room = {"state": "info", "text": "No level of today's map above the price", "detail": None, "trial": None}
    elif not risk:
        room = {"state": "info", "text": f"{_cents(above[0]['price'] - price)} to {above[0]['tag']}",
                "detail": "R is not known: no stop under your average.", "trial": None}
    else:
        r = (float(above[0]["price"]) - price) / risk
        room = {"state": "info", "text": f"{r:.1f}R to {above[0]['tag']}, from the price",
                "detail": f"R is your {px(risk)} risk a share. Room measured from the price, not from your entry; "
                          "trial T7 reads entries.", "trial": None, "r": round(r, 2)}
    tnote = None
    if target is not None:
        if target.get("traded_at"):
            tnote = {"state": "ok", "text": f"{px(target['price'])} ({STOCK_READ_TARGET_R:g}R) traded at "
                                            f"{hhmm(target['traded_at'])}: you are past it", "detail": target["rule"]}
        elif price is not None:
            tnote = {"state": "info", "text": f"{px(target['price'])} ({STOCK_READ_TARGET_R:g}R) is "
                                              f"{_cents(target['price'] - price)} above", "detail": target["rule"]}
    snote = stop_note(stop["price"], price, rnd) if stop and price is not None else None
    nxt = round_notes(bars, price=price, entry=None, now=now, rnd=rnd)[0] if price is not None else None
    recent = None
    fresh_broke = [b for b in broke if now - b["at"] <= STOCK_READ_ROUND_CROSS_SEC]
    if fresh_broke:
        b = fresh_broke[0]
        recent = {"state": "ok", "round": b["round"], "at": b["at"],
                  "text": f"Broke ${b['round']:.2f}: the {hhmm(b['at'] - MIN)} candle closed {px(b['close'])}",
                  "detail": "A candle closed over it: a stop under it is the raise offered."}
    elif through:
        t = through[0]
        when = f" at {hhmm(t['at'])}" if t.get("at") else ""
        recent = {"state": "warn", "round": t["round"], "at": t.get("at"),
                  "text": f"${t['round']:.2f} traded through{when}, no candle closed over it yet",
                  "detail": "A print over a round is not a break: only a close moves a stop."}
    return {"room": room, "target": tnote, "stop": snote, "next": nxt, "recent": recent}


def build(*, bars: list[dict[str, Any]], price: float | None, level_map: dict[str, Any] | None, avg: float,
          qty: float, now: float, since: float | None = None, stop: float | None = None,
          nova_stop: float | None = None, risk: float | None = None,
          checks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """``held`` for the read (AGENTS.md "Managing a trade you hold"). ``bars``: the session's closed 1-minute
    candles, oldest first; ``stop``: yours; ``nova_stop``: Nova's resting stop when it holds the exit;
    ``risk``: the risk a share you measure R in."""
    lm = level_map or {}
    intraday = list(lm.get("intraday") or [])
    rnd = rounds.of(lm.get("price")) or rounds.of(price) or rounds.of(avg)
    st = _stop(bars, price, intraday, _f(stop), _f(nova_stop), since)
    stop_px = st["price"] if st else None
    risk_v = _f(risk)
    if risk_v is None and stop_px is not None and stop_px < avg - EPS:
        risk_v = round(avg - stop_px, 4)
    broke, through = crosses(bars, rnd, since, price)
    up = raise_for(broke, rnd, stop_px, price)
    target = None
    if risk_v:
        t_px = round(avg + STOCK_READ_TARGET_R * risk_v, 4)
        after = [b for b in bars if since is not None and float(b["t"]) + MIN > since]
        hit = next((float(b["t"]) for b in after if float(b["h"]) >= t_px - EPS), None)
        target = {"price": t_px, "rule": f"your average + {STOCK_READ_TARGET_R:g} x {px(risk_v)}", "traded_at": hit}
    above = sorted((z for z in intraday if price is not None and float(z["lo"]) > price + EPS),
                   key=lambda z: float(z["lo"]))
    below = sorted((z for z in intraday if price is not None and float(z["hi"]) < price - EPS
                    and (stop_px is None or float(z["lo"]) > stop_px + EPS)), key=lambda z: -float(z["hi"]))
    ladder: list[dict[str, Any]] = []
    for z, role in zip(above[:2], ("next", "then"), strict=False):
        ladder.append(_zone_row(z, role, avg, qty, risk_v))
    if price is not None:
        ladder.append({"role": "now", "price": round(price, 4), "text": f"{(price - avg) * qty:+,.2f} open",
                       "r": round((price - avg) / risk_v, 2) if risk_v else None, "usd": round((price - avg) * qty, 2)})
    for t in through:
        when = f" at {hhmm(t['at'])}" if t.get("at") else ""
        ladder.append({"role": "through", "price": t["round"],
                       "text": f"traded through{when}, no candle closed over it yet", "r": None, "usd": None})
    for b in broke[:STOCK_READ_HELD_BROKE_ROWS]:
        ladder.append({"role": "broke", "price": b["round"],
                       "text": f"the {hhmm(b['at'] - MIN)} candle closed {px(b['close'])} over it", "r": None, "usd": None})
    if below and not any(stop_px is None or b["round"] > stop_px for b in broke):
        ladder.append(_zone_row(below[0], "support", avg, qty, risk_v))
    if st:
        ladder.append({"role": "stop", "price": stop_px, "text": st["rule"],
                       "r": round((stop_px - avg) / risk_v, 2) if risk_v else None,
                       "usd": round((stop_px - avg) * qty, 2)})
    ladder.append({"role": "cost", "price": round(avg, 4), "text": f"your average, {qty:g} sh", "r": 0.0, "usd": 0.0})
    order = {"then": 0, "next": 1, "now": 2, "through": 3, "broke": 4, "support": 5, "stop": 6, "cost": 7}
    ladder.sort(key=lambda row: (-row["price"], order[row["role"]]))
    return {
        "schema_version": STOCK_READ_HELD_SCHEMA_VERSION,
        "qty": qty,
        "avg": round(avg, 4),
        "price": price,
        "open_usd": round((price - avg) * qty, 2) if price is not None else None,
        "r": round((price - avg) / risk_v, 2) if price is not None and risk_v else None,
        "risk": risk_v,
        "since": since,
        "stop": st,
        "raise": up,
        "target": target,
        "ladder": ladder,
        "broke": broke,
        "through": through,
        "levels": _levels(price, avg, risk_v, st, target, [{"price": float(z["lo"]), "tag": z["tag"]} for z in above],
                          broke, through, bars, rnd, now),
        "checks": checks or [],
    }
