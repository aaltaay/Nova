"""What a plan has against the trend lines (ADR 036 amendment 2026-10-12). Pure.

The lines are ``trend_lines``': each chart's own, the 1-minute's and the 5-minute's. At most one note each, measured
on the plan's side -- a short's are the mirror (ADR 048):

- ``way``: the nearest holding line between the entry and the target -- a descending resistance over a long's entry,
  an ascending support under a short's: ``warn``, the trade has to get through a line everyone can see. A line the
  entry is already through (it runs between the price and the entry) is ``info``: the entry is its break.
- ``stop``: the nearest holding line between the stop's side and the entry -- an ascending support under a long's
  entry, a descending resistance over a short's: ``ok`` when the stop sits beyond its band, so a test of the line does
  not reach it; ``warn`` when the stop is inside the band or between the line and the entry.
- ``broke``: a line that broke in the last few candles while the price stays through it -- ``bad`` when it is against
  the plan (a long's support broke under it, a short's resistance broke over it), ``info`` when with it.

A line is where it runs at the last closed candle (``now_p``) and moves ``slope`` a candle. Nothing here blocks or
places anything: the bot and the scanners keep their own rules.
"""
from __future__ import annotations

from typing import Any

from stock_read.level_map import EPS, hhmm, px
from stock_read.trend_lines import CHART_WORDS, RESISTANCE, SUPPORT

ARROW = {"up": "↗", "down": "↘"}


def _name(line: dict[str, Any]) -> str:
    """ "↗ support (5-min)" """
    return f"{ARROW[line['dir']]} {line['kind']} ({CHART_WORDS.get(line['home'], line['home'])})"


def _story(line: dict[str, Any]) -> str:
    """Where the line runs and how it was drawn, in a sentence."""
    word = "ascending" if line["dir"] == "up" else "descending"
    step = _step(abs(float(line["slope"])))
    per = "candle" if line["home"] == "one_minute" else "5-minute candle"
    return (f"The {CHART_WORDS.get(line['home'], line['home'])} chart's {word} {line['kind']} runs at "
            f"{px(line['now_p'])} now and {'rises' if line['dir'] == 'up' else 'falls'} {step} a {per}; "
            f"{line['note']}.")


def _step(move: float) -> str:
    """A line's move a candle: "6c", "2.1c", "0.04c", "$1.20"."""
    if move >= 1:
        return f"${move:.2f}"
    cents = move * 100
    return f"{cents:.1f}".rstrip("0").rstrip(".") + "c" if cents >= 1 else f"{cents:.2g}c"


def _all(lines: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [*((lines or {}).get("one_minute") or []), *((lines or {}).get("five_minute") or [])]


def way_note(plan: dict[str, Any], holding: list[dict[str, Any]], price: float | None) -> dict[str, Any] | None:
    short = plan.get("side") == "short"
    sgn = -1.0 if short else 1.0
    entry, t1, risk = plan.get("entry"), plan.get("target"), plan.get("risk")
    target = plan.get("target2") or t1                         # the furthest target (#845)
    kind = SUPPORT if short else RESISTANCE
    if entry is None:
        return None
    ahead = [(sgn * (ln["now_p"] - entry), ln) for ln in holding if ln["kind"] == kind
             and sgn * (ln["now_p"] - entry) > ln["band"] - EPS
             and (target is None or sgn * (target - ln["now_p"]) > EPS)]
    if ahead:
        gap, ln = min(ahead, key=lambda x: x[0])
        r = gap / risk if risk and risk > EPS else None
        in_r = f" ({r:.1f}R)" if r is not None else ""
        which = 1 if t1 is None or sgn * (t1 - ln["now_p"]) > EPS else 2
        side_word = "Selling over" if short else "Buying under"
        role = "support" if short else "resistance"
        return {"role": "way", "state": "warn", "line": ln["id"], "price": ln["now_p"], "r": round(r, 2) if r else None,
                "text": f"{_name(ln)} at {px(ln['now_p'])}{in_r} before target {which}",
                "detail": f"{_story(ln)} {side_word} a line everyone can see trades into its {role}. It blocks nothing."}
    if price is None:
        return None
    through = [ln for ln in holding if ln["kind"] == kind and sgn * (ln["now_p"] - price) > EPS
               and sgn * (entry - ln["now_p"]) >= -ln["band"] - EPS]
    if not through:
        return None
    ln = min(through, key=lambda x: sgn * (x["now_p"] - price))
    return {"role": "way", "state": "info", "line": ln["id"], "price": ln["now_p"], "r": None,
            "text": f"The entry is {'under' if short else 'over'} the {_name(ln)} at {px(ln['now_p'])}: it trades the break",
            "detail": f"{_story(ln)} It describes; nothing trades on it."}


def stop_note(plan: dict[str, Any], holding: list[dict[str, Any]]) -> dict[str, Any] | None:
    short = plan.get("side") == "short"
    sgn = -1.0 if short else 1.0
    entry, stop, risk = plan.get("entry"), plan.get("stop"), plan.get("risk")
    kind = RESISTANCE if short else SUPPORT
    if entry is None:
        return None
    reach = (risk or 0.0) * 2 if stop is not None else None      # a line past the stop by more than 1R does not matter
    behind = [(sgn * (entry - ln["now_p"]), ln) for ln in holding if ln["kind"] == kind
              and sgn * (entry - ln["now_p"]) > EPS and (reach is None or sgn * (entry - ln["now_p"]) <= reach + EPS)]
    if not behind:
        return None
    _gap, ln = min(behind, key=lambda x: x[0])
    v, band = float(ln["now_p"]), float(ln["band"])
    under = "over" if short else "under"
    if stop is None:
        return {"role": "stop", "state": "info", "line": ln["id"], "price": v,
                "text": f"{_name(ln)} {under} the entry at {px(v)}", "detail": _story(ln)}
    if sgn * (v - stop) > band + EPS:
        return {"role": "stop", "state": "ok", "line": ln["id"], "price": v,
                "text": f"Stop {px(stop)} is {under} the {_name(ln)} at {px(v)}",
                "detail": f"{_story(ln)} A test of the line does not reach the stop."}
    where = "on" if abs(v - stop) <= band + EPS else ("under" if short else "over")
    return {"role": "stop", "state": "warn", "line": ln["id"], "price": v,
            "text": f"Stop {px(stop)} is {where} the {_name(ln)} at {px(v)}: a test of the line can take it",
            "detail": f"{_story(ln)} A stop {'over' if short else 'under'} the line's band survives a test of it."}


def broke_note(plan: dict[str, Any], broken: list[dict[str, Any]], price: float | None) -> dict[str, Any] | None:
    if price is None:
        return None
    short = plan.get("side") == "short"
    against_kind = RESISTANCE if short else SUPPORT
    out = []
    for ln in broken:
        b = ln.get("broke") or {}
        through = price < ln["now_p"] - EPS if ln["kind"] == SUPPORT else price > ln["now_p"] + EPS
        if b.get("t") is None or not through:
            continue
        out.append((ln["kind"] == against_kind, float(b["t"]), ln))
    if not out:
        return None
    against, _t, ln = max(out, key=lambda x: (x[0], x[1]))
    when = hhmm(ln["broke"]["t"])
    flip = ""
    if ln.get("retest_t") is not None:
        became = "resistance" if ln["kind"] == SUPPORT else "support"
        flip = f" It was tested from the other side at {hhmm(ln['retest_t'])} and turned: the {ln['kind']} became {became}."
    if against:
        sign = "bearish" if ln["kind"] == SUPPORT else "bullish"
        return {"role": "broke", "state": "bad", "line": ln["id"], "price": ln["now_p"],
                "text": f"{_name(ln)} broke at {when}",
                "detail": f"{_story(ln)} A broken {ln['kind']} line is a {sign} sign.{flip}"}
    return {"role": "broke", "state": "info", "line": ln["id"], "price": ln["now_p"],
            "text": f"Broke the {_name(ln)} at {when}",
            "detail": f"{_story(ln)}{flip} It describes; nothing trades on it."}


def notes(plan: dict[str, Any], lines: dict[str, Any] | None, *, price: float | None) -> list[dict[str, Any]]:
    """The plan's line rows, ``way`` then ``stop`` then ``broke``; empty without lines."""
    every = _all(lines)
    holding = [ln for ln in every if ln.get("state") == "holding"]
    broken = [ln for ln in every if ln.get("state") == "broken"]
    found = (way_note(plan, holding, price), stop_note(plan, holding), broke_note(plan, broken, price))
    return [n for n in found if n is not None]
