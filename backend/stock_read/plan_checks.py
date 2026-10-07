"""What stands in a plan's way, either side (ADR 036; shorts ADR 048). Pure.

A long plan runs up from its entry to its target: the levels over the entry and a large seller on Nova's
book are in its way, and a rising 1-minute MACD, a price over the 9 EMA and an entry over VWAP are on its
side. A short plan (``plan["side"] == "short"``) is the mirror: it runs down from its entry to its cover
target, so the levels under the entry and a large buyer on the bids are in its way, and a falling MACD, a
price under the 9 EMA and an entry under VWAP are on its side; a flush on the tape is for it, a burst
against it, and offers being pulled (sellers stepping away) are the warning bids being pulled are for a
long. The checks and marks describe; they never block anything.
"""
from __future__ import annotations

from typing import Any

from constants_setups import TAPE_GATE_BIG_SELLER_SHARES, TAPE_GATE_WALL_SHARES
from constants_stock_read import STOCK_READ_STOP_CAP_DEFAULT
from setup_scanner.five_minute import words as tf5_words
from stock_read import rounds

EPS = 1e-9


def is_short(plan: dict[str, Any]) -> bool:
    return plan.get("side") == "short"


def obstacles(plan: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Levels strictly between the entry and the target: the high of day, VWAP, the premarket
    high, the open, each round number of the stock's scale (``rounds``: the half and whole dollars up
    to $25, the $5 numbers on ACN at $223), and a large seller on Nova's book -- for a short, a large
    buyer on its bids. Ordered as the price meets them: up for a long, down for a short."""
    entry, target = plan.get("entry"), plan.get("target")
    if entry is None or target is None:
        return []
    short = is_short(plan)
    lo, hi = (target, entry) if short else (entry, target)
    rnd = (rounds.of((ctx.get("level_map") or {}).get("price")) or rounds.of(ctx.get("price"))
           or rounds.of(entry))
    lv = ctx.get("levels") or {}
    out: list[dict[str, Any]] = []

    def add(price: float | None, label: str, kind: str, size: float | None = None) -> None:
        if price is not None and lo + EPS < float(price) < hi - EPS:
            out.append({"price": round(float(price), 4), "label": label, "kind": kind,
                        "size": int(size) if size is not None else None})

    add((lv.get("hod") or {}).get("price"), "high of day", "hod")
    add(lv.get("vwap"), "VWAP", "vwap")
    add(lv.get("pmh"), "premarket high", "pmh")
    add(lv.get("open"), "the open", "open")
    for r in rnd.between(lo, hi) if rnd else []:
        add(r, f"${r:.2f}", "round")
    who, book = ("a buyer", ctx.get("bids")) if short else ("a seller", ctx.get("asks"))
    for row in book or []:
        size = float(row.get("size") or 0)
        if size >= TAPE_GATE_WALL_SHARES:
            add(row.get("price"), f"{who} of {int(size):,}", "wall", size)
    out.sort(key=lambda m: -m["price"] if short else m["price"])
    return out


def _listing(labels: list[str]) -> str:
    """"$225.00", "$225.00 and $230.00", "$5.50, $6.00 and $6.50", "4 round numbers ($15.50 to $17.00)"."""
    if len(labels) > 3:
        return f"{len(labels)} round numbers ({labels[0]} to {labels[-1]})"
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + f" and {labels[-1]}" if labels else ""


def _risk_check(plan: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    risk = plan.get("risk")
    cap = ctx.get("stop_cap") or STOCK_READ_STOP_CAP_DEFAULT
    floor = ctx.get("min_stop")
    if risk is None or risk <= 0:
        none = "no buy stop over the entry" if is_short(plan) else "no stop under the entry"
        return {"id": "risk", "state": "unknown", "text": f"{none}: nothing to measure"}
    if risk > cap + EPS:
        return {"id": "risk", "state": "bad", "text": f"risk {risk:.2f} is over the {cap:.2f} stop cap"}
    if floor is not None and risk < floor - EPS:
        return {"id": "risk", "state": "warn", "text": f"risk {risk:.2f} is under the {floor:.2f} floor"}
    return {"id": "risk", "state": "ok", "text": f"risk {risk:.2f} within the {cap:.2f} cap"}


def _trend_checks(plan: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """The 1-minute MACD, the 9 EMA, the 5-minute chart and VWAP: with the trade's side, or against it."""
    short = is_short(plan)
    out: list[dict[str, Any]] = []
    hist = ctx.get("macd_hist")
    if hist is None:
        out.append({"id": "macd", "state": "unknown", "text": "1-min MACD not known yet"})
    else:
        good = hist < 0 if short else hist > 0
        out.append({"id": "macd", "state": "ok" if good else "bad", "text": f"1-min MACD histogram {hist:+.3f}"})
    price, ema9, vw = ctx.get("price"), ctx.get("ema9"), (ctx.get("levels") or {}).get("vwap")
    if price is not None and ema9 is not None:
        over = price >= ema9
        out.append({"id": "ema9", "state": "ok" if over != short else "bad",
                    "text": f"{'above' if over else 'under'} the 9 EMA {ema9:.2f}"})
    tf5 = ctx.get("tf5")
    if isinstance(tf5, dict) and isinstance(tf5.get("agrees"), bool):
        out.append({"id": "tf5", "state": "info", "text": f"{tf5_words(tf5)} (trial T8)"})
    entry = plan.get("entry")
    if entry is not None and vw is not None:
        over = entry >= vw
        out.append({"id": "vwap", "state": "ok" if over != short else "bad",
                    "text": f"{'above' if over else 'under'} VWAP {vw:.2f}"})
    return out


def _tape_checks(plan: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    short = is_short(plan)
    out: list[dict[str, Any]] = []
    tape = plan.get("tape")
    if tape and tape.get("verdict"):
        verdict = str(tape["verdict"])
        first = (tape.get("reasons") or [""])[0]
        state = {"go": "ok", "wait": "warn", "veto": "bad"}.get(verdict, "unknown")
        text = f"tape {verdict.upper()}" + (f": {first}" if first else "")
        if verdict == "blind":
            text = "tape blind: Nova holds no Level 2 line for it"
        out.append({"id": "tape", "state": state, "text": text})
    flow = ctx.get("flow") or {}
    if flow.get("label") in ("burst", "flush") and flow.get("score") is not None:
        with_it = (flow["label"] == "flush") if short else (flow["label"] == "burst")
        out.append({"id": "flow", "state": "ok" if with_it else "bad",
                    "text": f"the tape is {'bursting' if flow['label'] == 'burst' else 'flushing'} ({flow['score']:+.2f})"})
    pulls = (ctx.get("ask_pulls") if short else ctx.get("bid_pulls")) or 0
    if pulls:
        what = "offers" if short else "bids"
        out.append({"id": "pulls", "state": "warn",
                    "text": f"{what} being pulled ({pulls} flag{'' if pulls == 1 else 's'} in the last minute)"})
    return out


def checks(plan: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """What stands in the way, in the order a trader reads it. ``state``: ok / warn / bad / unknown / info."""
    out: list[dict[str, Any]] = [_risk_check(plan, ctx)]
    risk = plan.get("risk")
    spread = ctx.get("spread")
    if risk and risk > EPS and spread is not None:
        state = "bad" if spread >= risk - EPS else ("warn" if spread > risk / 2 + EPS else "ok")
        out.append({"id": "spread", "state": state,
                    "text": (f"the spread {spread:.2f} is at least the {risk:.2f} risk" if state == "bad"
                             else f"the spread {spread:.2f} is {'over half' if state == 'warn' else 'within half'} "
                                  f"the {risk:.2f} risk")})
    med = ctx.get("median_range")
    if risk and med and risk < med - EPS:
        out.append({"id": "candle", "state": "warn",
                    "text": f"the {risk:.2f} stop is inside one normal 1-min candle ({med:.2f})"})
    out += _trend_checks(plan, ctx)
    in_way = obstacles(plan, ctx)
    round_words = _listing([m["label"] for m in in_way if m["kind"] == "round"])
    for m in in_way:
        if m["kind"] == "round":
            # The rounds are one line, where the first of them sits: a wide plan crosses several.
            if round_words:
                out.append({"id": "in_way_round", "state": "warn", "text": f"{round_words} before the target"})
                round_words = ""
            continue
        big = m["kind"] == "wall" and (m.get("size") or 0) >= TAPE_GATE_BIG_SELLER_SHARES
        out.append({"id": f"in_way_{m['kind']}", "state": "bad" if big else "warn",
                    "text": f"{m['label']} at {m['price']:.2f} before the target"})
    out += _tape_checks(plan, ctx)
    if ctx.get("halted") is True:
        out.append({"id": "halted", "state": "bad", "text": "halted now"})
    win = plan.get("window") or {}
    if plan.get("source") == "setup" and win.get("state") in ("before", "after"):
        out.append({"id": "window", "state": "warn",
                    "text": f"outside the bot's {win.get('start')}-{win.get('end')} window: a hand trade"})
    return out
