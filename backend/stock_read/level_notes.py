"""What the plan says about the day's levels (ADR 036 amendment 2026-09-30). Pure.

Room (the first zone of today's map above the entry, in R: a warning under 2R while trial T7 runs),
the half or whole dollar at the target and at the stop, the next one over the entry, a round the price
just broke or lost, and today's zones between the stop and the target (the 1-minute chart's lines and
the ruler's marks). Every sentence quotes the level study's in-sample figures; nothing here blocks or
places anything. The zones come from ``level_map``.
"""
from __future__ import annotations

import math
from typing import Any

from constants_stock_read import (
    STOCK_READ_LEVEL_STUDY,
    STOCK_READ_ROOM_MIN_R,
    STOCK_READ_ROUND_CROSS_SEC,
    STOCK_READ_ROUND_FRESH_BARS,
    STOCK_READ_ROUND_NEAR,
    STOCK_READ_ROUND_STEP,
)
from stock_read.level_map import CENT, EPS, ROUND_KINDS, hhmm, px

ROOM_TRIAL = "T7"


def _pair(key: str) -> tuple[int, int]:
    a, b = STOCK_READ_LEVEL_STUDY[key]
    return int(a), int(b)


def _cents(x: float) -> str:
    return f"{round(abs(x) * 100):d}c"


def room(plan: dict[str, Any], intraday: list[dict[str, Any]], daily: list[dict[str, Any]]) -> dict[str, Any]:
    """The first zone of today's map above the entry, in R. Under ``STOCK_READ_ROOM_MIN_R`` it reads
    amber; it blocks nothing (trial T7 decides whether it ever does). Daily levels never count here:
    they are named, faint, for the Full Day chart."""
    entry, risk, target = plan.get("entry"), plan.get("risk"), plan.get("target")
    base = {"trial": ROOM_TRIAL, "r": None, "price": None, "label": None}
    if entry is None or not risk or risk <= EPS:
        return base | {"state": "unknown", "text": "Room is not known: no stop under the entry", "detail": None}
    above = sorted((z for z in intraday if z["lo"] > entry + EPS), key=lambda z: z["lo"])
    in_way = [z for z in daily if target is not None and entry + EPS < z["lo"] < target - EPS]
    daily_note = ("The Full Day chart has " + ", ".join(z["label"] for z in in_way[:3])
                  + f" in the way; daily levels never count here: old daily highs did not slow gappers in the "
                    f"study ({_pair('daily_past')[0]}% went on past them, {_pair('daily_past')[1]}% at a random price)."
                  if in_way else None)
    if not above:
        return base | {"state": "ok", "text": "No level of today's map above the entry",
                       "detail": daily_note}
    first = above[0]
    r = (first["lo"] - entry) / risk
    then = f"Then {above[1]['tag']} at {(above[1]['lo'] - entry) / risk:.1f}R. " if len(above) > 1 else ""
    warn = r < STOCK_READ_ROOM_MIN_R - EPS
    trial = (f"Under {STOCK_READ_ROOM_MIN_R:g}R it is a warning while trial {ROOM_TRIAL} runs; it blocks nothing."
             if warn else "")
    detail = " ".join(x for x in (then + trial, daily_note or "") if x).strip() or None
    return {"trial": ROOM_TRIAL, "r": round(r, 2), "price": first["lo"], "label": first["label"],
            "state": "warn" if warn else "ok", "text": f"{r:.1f}R to {first['tag']}", "detail": detail}


def _round_above(p: float) -> float:
    return round(math.floor(p / STOCK_READ_ROUND_STEP + EPS) * STOCK_READ_ROUND_STEP + STOCK_READ_ROUND_STEP, 2)


def _round_at_or_below(p: float) -> float:
    return round(math.floor(p / STOCK_READ_ROUND_STEP + EPS) * STOCK_READ_ROUND_STEP, 2)


def target_note(target: float | None) -> dict[str, Any] | None:
    if target is None:
        return None
    turn, rand = _pair("round_turn")
    over = _round_at_or_below(target)
    under = _round_above(target)
    if 0 < under - target <= STOCK_READ_ROUND_NEAR + EPS:
        return {"state": "ok", "round": under, "text": f"{px(target)} is {_cents(under - target)} under ${under:.2f}",
                "detail": f"You sell before the round. A half or whole dollar turns price back {turn}% of the time "
                          f"before it breaks, against {rand}% at a random price."}
    if 0 <= target - over <= STOCK_READ_ROUND_NEAR + EPS:
        through, rand_t = _pair("round_through")
        where = "on" if target - over < EPS else f"{_cents(target - over)} over"
        return {"state": "warn", "round": over, "text": f"{px(target)} is {where} ${over:.2f}",
                "detail": f"It fills only once ${over:.2f} prints through: a half or whole dollar turns price back "
                          f"{turn}% of the time before it breaks (random price {rand}%); once through, price ran on in "
                          f"{through}% of breaks (random {rand_t}%)."}
    return None


def stop_note(stop: float | None, entry: float | None) -> dict[str, Any] | None:
    if stop is None or entry is None:
        return None
    lost, rand = _pair("round_lost")
    over = _round_above(stop)
    under = _round_at_or_below(stop)
    if over < entry - EPS and 0 < over - stop <= STOCK_READ_ROUND_NEAR + EPS:
        return {"state": "ok", "round": over, "text": f"{px(stop)} is {_cents(over - stop)} under ${over:.2f}",
                "detail": f"A test of ${over:.2f} does not reach it. If ${over:.2f} breaks, the drop usually keeps "
                          f"going: -1.5% before +1.5% in {lost}% of breaks, against {rand}%."}
    if under < entry - EPS and 0 <= stop - under <= STOCK_READ_ROUND_NEAR + EPS:
        where = "on" if stop - under < EPS else f"{_cents(stop - under)} over"
        return {"state": "warn", "round": under, "text": f"{px(stop)} is {where} ${under:.2f}",
                "detail": f"A test of ${under:.2f} can take the stop without breaking it. Under ${under:.2f} the drop "
                          f"usually keeps going ({lost}% of breaks, against {rand}%)."}
    return None


def cross_events(bars: list[dict[str, Any]], levels: list[float],
                 fresh: int = STOCK_READ_ROUND_FRESH_BARS) -> list[dict[str, Any]]:
    """Each fresh cross of each level: up when a candle prints 1c over it after ``fresh`` candles
    entirely under it, down the mirror. ``{price, dir: "up" | "down", t}``, oldest first."""
    out = []
    highs = [float(b["h"]) for b in bars]
    lows = [float(b["l"]) for b in bars]
    for p in levels:
        for k in range(fresh, len(bars)):
            if highs[k] >= p + CENT - EPS and max(highs[k - fresh:k]) < p - EPS:
                out.append({"price": p, "dir": "up", "t": float(bars[k]["t"])})
            if lows[k] <= p - CENT + EPS and min(lows[k - fresh:k]) > p + EPS:
                out.append({"price": p, "dir": "down", "t": float(bars[k]["t"])})
    out.sort(key=lambda e: e["t"])
    return out


def round_notes(bars: list[dict[str, Any]], *, price: float | None, entry: float | None,
                now: float) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """``(next, recent)``: the next half / whole dollar over the entry (else the price) -- resistance
    until it prints through, a trigger after -- and a round the price broke or lost in the last
    ``STOCK_READ_ROUND_CROSS_SEC`` while it still stands on that side."""
    turn, rand = _pair("round_turn")
    through, rand_t = _pair("round_through")
    lost, rand_l = _pair("round_lost")
    ref = entry if entry is not None else price
    nxt = None
    if ref is not None and ref > 0:
        r = _round_above(ref)
        gap = r - ref
        near = gap <= STOCK_READ_ROUND_NEAR + EPS
        who = "entry" if entry is not None else "price"
        nxt = {"state": "warn" if near else "info", "round": r,
               "text": (f"{who.capitalize()} {_cents(gap)} under ${r:.2f}: it turns back about 1 in 4 before it breaks"
                        if near else f"${r:.2f} is {_cents(gap)} above: resistance until it prints through, a trigger after"),
               "detail": f"A fresh approach to a half or whole dollar turned back {turn}% of the time (random price {rand}%). "
                         f"Once 1c through, price ran +1.5% before -1.5% in {through}% of breaks (random {rand_t}%)."}
    recent = None
    if price is not None and bars:
        levels = sorted({_round_at_or_below(price), _round_above(price)})
        events = [e for e in cross_events(bars, levels) if now - e["t"] <= STOCK_READ_ROUND_CROSS_SEC]
        for e in reversed(events):
            if e["dir"] == "up" and price >= e["price"] - EPS:
                recent = {"state": "ok", "round": e["price"], "at": e["t"],
                          "text": f"Broke ${e['price']:.2f} at {hhmm(e['t'])}",
                          "detail": f"Once through, price ran +1.5% before -1.5% in {through}% of breaks "
                                    f"(random {rand_t}%). It is a description: nothing buys on it."}
                break
            if e["dir"] == "down" and price <= e["price"] + EPS:
                recent = {"state": "bad", "round": e["price"], "at": e["t"],
                          "text": f"Lost ${e['price']:.2f} at {hhmm(e['t'])}: the drop usually keeps going",
                          "detail": f"After a break under a half or whole dollar, -1.5% came before +1.5% in {lost}% "
                                    f"of breaks (random {rand_l}%)."}
                break
    return nxt, recent


def between(plan: dict[str, Any], intraday: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Today's zones strictly between the stop and the target: the 1-minute chart's lines and the
    ruler's marks."""
    stop, target = plan.get("stop"), plan.get("target")
    if stop is None or target is None:
        return []
    out = []
    for z in sorted(intraday, key=lambda z: z["lo"]):
        if z["lo"] > stop + EPS and z["hi"] < target - EPS:
            out.append({"price": z["price"], "lo": z["lo"], "hi": z["hi"], "tag": z["tag"], "label": z["label"],
                        "round": any(m["kind"] in ROUND_KINDS for m in z["members"]),
                        "hod": any(m["kind"] == "hod" for m in z["members"])})
    return out


def notes(plan: dict[str, Any], level_map: dict[str, Any] | None, bars: list[dict[str, Any]], *,
          price: float | None, now: float) -> dict[str, Any] | None:
    """The plan's level rows: Room (T7), the target's and the stop's round, the next round and a
    round just broken or lost, and today's zones between the stop and the target."""
    if not level_map:
        return None
    intra, day = level_map.get("intraday") or [], level_map.get("daily") or []
    nxt, recent = round_notes(bars, price=price, entry=plan.get("entry"), now=now)
    return {
        "room": room(plan, intra, day),
        "target": target_note(plan.get("target")),
        "stop": stop_note(plan.get("stop"), plan.get("entry")),
        "next": nxt,
        "recent": recent,
        "between": between(plan, intra),
    }
