"""What a short plan says about the day's levels (ADR 048: "levels, room and round numbers are measured
downward"). Pure; ``level_notes`` is the long side and dispatches here.

A short sells at its entry and covers under it, so its Room is the distance down to the first zone of
today's map under the entry, its target is judged against the round just under it (a cover over the
round fills before the round; one on or under it needs the round to break), its buy stop against the
round just over it, its next round is the one under the entry, and a round the price just lost is the
short's trigger while one it just broke is against it.

The level study measured approaches and breaks from below (the long side); of its figures only the
break *under* a round -- the short's trigger -- reads the short's way, so that is the only one quoted
here. Trial T7 was registered on long entries: a short's Room describes and is in no trial.
"""
from __future__ import annotations

from typing import Any

from constants_stock_read import STOCK_READ_ROOM_MIN_R, STOCK_READ_ROUND_CROSS_SEC
from stock_read import rounds
from stock_read.level_map import EPS, hhmm, px
from stock_read.level_notes import _cents, _pair, _study, cross_events

NO_TRIAL = "Trial T7 was registered on long entries: a short's Room describes and is in no trial."


def _lost_words(rnd: rounds.Rounds) -> str:
    lost, rand = _pair("round_lost")
    return _study(rnd, f"After a break under a half or whole dollar, -1.5% came before +1.5% in {lost}% of "
                       f"breaks (random {rand}%).")


def room(plan: dict[str, Any], intraday: list[dict[str, Any]], daily: list[dict[str, Any]],
         rnd: rounds.Rounds | None = None) -> dict[str, Any]:
    """The first zone of today's map under the entry, in R; under ``STOCK_READ_ROOM_MIN_R`` it reads amber."""
    entry, risk, target = plan.get("entry"), plan.get("risk"), plan.get("target")
    base = {"trial": None, "r": None, "price": None, "label": None}
    if entry is None or not risk or risk <= EPS:
        return base | {"state": "unknown", "text": "Room is not known: no buy stop over the entry", "detail": None}
    below = sorted((z for z in intraday if z["hi"] < entry - EPS), key=lambda z: -z["hi"])
    in_way = [z for z in daily if target is not None and target + EPS < z["hi"] < entry - EPS]
    daily_note = ("The Full Day chart has " + ", ".join(z["label"] for z in in_way[:3])
                  + " in the way; daily levels never count here." if in_way else None)
    if not below:
        return base | {"state": "ok", "text": "No level of today's map under the entry",
                       "detail": " ".join(x for x in (daily_note, NO_TRIAL) if x)}
    first = below[0]
    r = (entry - first["hi"]) / risk
    then = f"Then {below[1]['tag']} at {(entry - below[1]['hi']) / risk:.1f}R. " if len(below) > 1 else ""
    warn = r < STOCK_READ_ROOM_MIN_R - EPS
    note = f"Under {STOCK_READ_ROOM_MIN_R:g}R it is a warning; it blocks nothing. " if warn else ""
    detail = " ".join(x for x in (then + note, daily_note or "", NO_TRIAL) if x).strip()
    return {"trial": None, "r": round(r, 2), "price": first["hi"], "label": first["label"],
            "state": "warn" if warn else "ok", "text": f"{r:.1f}R to {first['tag']}", "detail": detail}


def target_note(target: float | None, rnd: rounds.Rounds | None) -> dict[str, Any] | None:
    """A cover just over a round fills before it; one on or just under it needs the round to break."""
    if target is None or rnd is None:
        return None
    under = rnd.below(target)
    over = rnd.at_or_above(target)
    if 0 < target - under <= rnd.near + EPS:
        return {"state": "ok", "round": under, "text": f"{px(target)} covers {_cents(target - under)} over ${under:.2f}",
                "detail": "You cover before the round: buyers often defend it before it breaks."}
    if 0 <= over - target <= rnd.near + EPS:
        where = "on" if over - target < EPS else f"{_cents(over - target)} under"
        return {"state": "warn", "round": over, "text": f"{px(target)} is {where} ${over:.2f}",
                "detail": f"It fills only once ${over:.2f} breaks. " + _lost_words(rnd)}
    return None


def stop_note(stop: float | None, entry: float | None, rnd: rounds.Rounds | None) -> dict[str, Any] | None:
    """A buy stop over a round the entry is under survives a test of it; one on or just under it does not."""
    if stop is None or entry is None or rnd is None:
        return None
    under = rnd.below(stop)
    over = rnd.at_or_above(stop)
    if under > entry + EPS and 0 < stop - under <= rnd.near + EPS:
        return {"state": "ok", "round": under, "text": f"{px(stop)} is {_cents(stop - under)} over ${under:.2f}",
                "detail": f"A test of ${under:.2f} does not reach it."}
    if over > entry + EPS and 0 <= over - stop <= rnd.near + EPS:
        where = "on" if over - stop < EPS else f"{_cents(over - stop)} under"
        return {"state": "warn", "round": over, "text": f"{px(stop)} is {where} ${over:.2f}",
                "detail": f"A test of ${over:.2f} can take the stop without breaking it: a buy stop over the round "
                          "survives its test."}
    return None


def round_notes(bars: list[dict[str, Any]], *, price: float | None, entry: float | None,
                now: float, rnd: rounds.Rounds | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """``(next, recent)``: the next round under the entry (else the price) -- support until it prints
    through, a trigger after -- and a round the price lost (the short's way) or broke (against it) in the
    last ``STOCK_READ_ROUND_CROSS_SEC`` while it still stands on that side."""
    if rnd is None:
        return None, None
    ref = entry if entry is not None else price
    nxt = None
    if ref is not None and ref > 0:
        r = rnd.below(ref)
        gap = ref - r
        near = gap <= rnd.near + EPS
        who = "entry" if entry is not None else "price"
        nxt = {"state": "warn" if near else "info", "round": r,
               "text": (f"{who.capitalize()} {_cents(gap)} over ${r:.2f}: a round number in the way"
                        if near else f"${r:.2f} next: support until it prints through, a trigger after"),
               "detail": _lost_words(rnd)}
    recent = None
    if price is not None and bars:
        levels = sorted({rnd.at_or_above(price), rnd.below(price)})
        events = [e for e in cross_events(bars, levels) if now - e["t"] <= STOCK_READ_ROUND_CROSS_SEC]
        for e in reversed(events):
            if e["dir"] == "down" and price <= e["price"] + EPS:
                recent = {"state": "ok", "round": e["price"], "at": e["t"],
                          "text": f"Lost ${e['price']:.2f} at {hhmm(e['t'])}",
                          "detail": _lost_words(rnd) + " It is a description: nothing shorts on it."}
                break
            if e["dir"] == "up" and price >= e["price"] - EPS:
                recent = {"state": "bad", "round": e["price"], "at": e["t"],
                          "text": f"Broke ${e['price']:.2f} at {hhmm(e['t'])}: against a short",
                          "detail": "A round the price broke over is a long's trigger; a short is against it."}
                break
    return nxt, recent
