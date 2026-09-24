"""The plan on top of Level 2 (ADR 036): entry, stop and a target of at least 2R, and what stands in
the way. Pure.

A setup plan is the most advanced lane's own levels -- its armed (or triggered) setup, else the
levels it would arm with while it forms (provisional). A hand plan starts from the operator's entry:
the stop is theirs or the low of the last few closed one-minute candles, the target entry + 2R.
The checks and marks describe; they never block anything.
"""
from __future__ import annotations

from typing import Any

from constants_setups import (
    SETUP_STATE_ARMED,
    SETUP_STATE_NEAR,
    SETUP_STATE_TRIGGERED,
    TAPE_GATE_BIG_SELLER_SHARES,
    TAPE_GATE_WALL_SHARES,
)
from constants_stock_read import (
    STOCK_READ_MANUAL_STOP_BARS,
    STOCK_READ_STOP_CAP_DEFAULT,
    STOCK_READ_TARGET_R,
    STOCK_READ_TRIGGERED_PLAN_SEC,
)
from stock_read.indicators import manual_stop

FILTERED = "filtered"
LIVE_STATES = (SETUP_STATE_NEAR, SETUP_STATE_ARMED, FILTERED)
EPS = 1e-9
_NAMES = {"first_pullback": "first pullback", "bull_flag": "bull flag", "flat_top_breakout": "flat-top breakout",
          "red_to_green": "red to green"}
_ENTRY_RULES = {
    "first_pullback": "1 cent over the last pullback candle's high",
    "bull_flag": "1 cent over the last flag candle's high",
    "flat_top_breakout": "1 cent over the flat top (the taught entry waits for a candle to hold over it)",
    "red_to_green": "1 cent over the open",
}
_STOP_RULES = {
    "first_pullback": "the pullback's low",
    "bull_flag": "the flag's low",
    "flat_top_breakout": "the base's low",
    "red_to_green": "the lowest low since the open",
}


def setup_name(setup_type: str | None) -> str:
    return _NAMES.get(setup_type or "", (setup_type or "setup").replace("_", " "))


def _rank(lane: dict[str, Any], now: float) -> int | None:
    state, setup = lane.get("state"), lane.get("setup")
    if state == SETUP_STATE_NEAR and setup:
        return 0
    if state in (SETUP_STATE_ARMED, FILTERED) and setup:
        return 1
    if state == SETUP_STATE_TRIGGERED and setup:
        at = float(setup.get("triggered_at") or 0)
        return 2 if now - at <= STOCK_READ_TRIGGERED_PLAN_SEC else None
    return 3 if lane.get("forming") else None


def choose(setups: list[dict[str, Any]], now: float) -> dict[str, Any] | None:
    """The lane the plan follows: near, armed, triggered in the last 30 minutes, then forming; the
    bot's chosen setup first on a tie, then the playbook's order."""
    best: tuple[int, int, int] | None = None
    pick = None
    for i, lane in enumerate(setups):
        r = _rank(lane, now)
        if r is None:
            continue
        key = (r, 0 if lane.get("chosen") else 1, i)
        if best is None or key < best:
            best, pick = key, lane
    return pick


def target_rule(setup_type: str, rules: dict[str, Any]) -> str:
    r = rules.get("target_r") or STOCK_READ_TARGET_R
    mode = rules.get("target_mode") or "r"
    if mode == "fixed":
        return "a fixed amount over the entry (the template's)"
    if setup_type == "flat_top_breakout" or mode == "r":
        return f"entry + {r:g} x risk"
    if setup_type == "red_to_green":
        return f"the higher of entry + {r:g} x risk and the high of day"
    high = "pole" if setup_type == "bull_flag" else "leg"
    if mode == "leg":
        return f"the {high} high (entry + {r:g} x risk when the {high} high is not above the entry)"
    return f"the higher of entry + {r:g} x risk and the {high} high"


def from_setup(lane: dict[str, Any]) -> dict[str, Any]:
    state = lane.get("state")
    live = state in LIVE_STATES + (SETUP_STATE_TRIGGERED,) and lane.get("setup")
    lv = lane["setup"] if live else lane["forming"]
    entry, stop, target = float(lv["entry"]), float(lv["stop"]), float(lv["target1"])
    if live:
        shown = {SETUP_STATE_NEAR: "near", SETUP_STATE_TRIGGERED: "triggered"}.get(state, "armed")
        reason = lane.get("reason") or ""
    else:
        shown = "forming"
        bits = [lane.get("reason") or ""]
        if lv.get("waiting"):
            bits.append(f"arms after {lv['waiting']}")
        if lv.get("blocked") and lv.get("blocked") not in bits[0]:
            bits.append(f"blocked: {lv['blocked']}")
        reason = " -- ".join(b for b in bits if b)
    return _levels({
        "source": "setup", "setup_type": lane.get("setup_type"), "kind": lane.get("kind"), "state": shown,
        "provisional": not live, "trigger": lv.get("trigger"), "grade": lane.get("grade"), "reason": reason,
        "target_rule": target_rule(lane.get("setup_type") or "", lane.get("rules") or {}),
        "entry_rule": _ENTRY_RULES.get(lane.get("setup_type") or "", "the setup's trigger + 1 cent"),
        "stop_rule": _STOP_RULES.get(lane.get("setup_type") or "", "the setup's stop"),
        "tape": ({"verdict": lane["tape"].get("verdict"), "reasons": lane["tape"].get("reasons")}
                 if live and lane.get("tape") else None),
        "window": lane.get("window"),
    }, entry, stop, target)


def manual(entry: float, stop: float | None, bars: list[dict[str, Any]]) -> dict[str, Any]:
    """The operator's own plan: their entry, their stop or the last candles' low, a 2R target."""
    own = stop is not None and stop < entry - EPS
    stop_px = stop if own else manual_stop(bars, entry, STOCK_READ_MANUAL_STOP_BARS)
    base = {"source": "manual", "setup_type": None, "kind": None, "state": "manual", "provisional": True,
            "trigger": None, "grade": None,
            "reason": "no setup is forming: your entry, a 2:1 target",
            "target_rule": f"entry + {STOCK_READ_TARGET_R:g} x risk",
            "entry_rule": "your entry",
            "stop_rule": ("your stop" if own
                          else f"the lowest low of the last {STOCK_READ_MANUAL_STOP_BARS} closed 1-min candles"),
            "tape": None, "window": None}
    if stop_px is None:
        return {**base, "entry": round(entry, 4), "stop": None, "target": None, "risk": None, "reward": None,
                "rr": None, "reason": "no candle low under your entry to stop at -- name a stop"}
    risk = entry - stop_px
    return _levels(base, entry, stop_px, entry + STOCK_READ_TARGET_R * risk)


def _levels(plan: dict[str, Any], entry: float, stop: float, target: float) -> dict[str, Any]:
    risk, reward = round(entry - stop, 4), round(target - entry, 4)
    return {**plan, "entry": round(entry, 4), "stop": round(stop, 4), "target": round(target, 4), "risk": risk,
            "reward": reward, "rr": round(reward / risk, 2) if risk > EPS else None}


def _obstacles(plan: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Levels strictly between the entry and the target: the high of day, VWAP, the premarket
    high, the open, each half / whole dollar, and a large seller on Nova's book."""
    lo, hi = plan.get("entry"), plan.get("target")
    if lo is None or hi is None:
        return []
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
    step = 0.5
    k = int(lo / step) + 1
    while k * step < hi - EPS:
        add(k * step, f"${k * step:.2f}", "round")
        k += 1
    for ask in ctx.get("asks") or []:
        size = float(ask.get("size") or 0)
        if size >= TAPE_GATE_WALL_SHARES:
            add(ask.get("price"), f"a seller of {int(size):,}", "wall", size)
    out.sort(key=lambda m: m["price"])
    return out


def checks(plan: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """What stands in the way, in the order a trader reads it. ``state``: ok / warn / bad / unknown."""
    out: list[dict[str, Any]] = []
    risk = plan.get("risk")
    cap = ctx.get("stop_cap") or STOCK_READ_STOP_CAP_DEFAULT
    floor = ctx.get("min_stop")
    if risk is None or risk <= 0:
        out.append({"id": "risk", "state": "unknown", "text": "no stop under the entry: nothing to measure"})
    elif risk > cap + EPS:
        out.append({"id": "risk", "state": "bad", "text": f"risk {risk:.2f} is over the {cap:.2f} stop cap"})
    elif floor is not None and risk < floor - EPS:
        out.append({"id": "risk", "state": "warn", "text": f"risk {risk:.2f} is under the {floor:.2f} floor"})
    else:
        out.append({"id": "risk", "state": "ok", "text": f"risk {risk:.2f} within the {cap:.2f} cap"})
    med = ctx.get("median_range")
    if risk and med and risk < med - EPS:
        out.append({"id": "candle", "state": "warn",
                    "text": f"the {risk:.2f} stop is inside one normal 1-min candle ({med:.2f})"})
    hist = ctx.get("macd_hist")
    if hist is None:
        out.append({"id": "macd", "state": "unknown", "text": "1-min MACD not known yet"})
    else:
        out.append({"id": "macd", "state": "ok" if hist > 0 else "bad", "text": f"1-min MACD histogram {hist:+.3f}"})
    price, ema9, vw = ctx.get("price"), ctx.get("ema9"), (ctx.get("levels") or {}).get("vwap")
    if price is not None and ema9 is not None:
        out.append({"id": "ema9", "state": "ok" if price >= ema9 else "bad",
                    "text": f"{'above' if price >= ema9 else 'under'} the 9 EMA {ema9:.2f}"})
    entry = plan.get("entry")
    if entry is not None and vw is not None:
        out.append({"id": "vwap", "state": "ok" if entry >= vw else "bad",
                    "text": f"{'above' if entry >= vw else 'under'} VWAP {vw:.2f}"})
    for m in _obstacles(plan, ctx):
        big = m["kind"] == "wall" and (m.get("size") or 0) >= TAPE_GATE_BIG_SELLER_SHARES
        where = m["label"] if m["kind"] == "round" else f"{m['label']} at {m['price']:.2f}"
        out.append({"id": f"in_way_{m['kind']}", "state": "bad" if big else "warn",
                    "text": f"{where} before the target"})
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
        out.append({"id": "flow", "state": "ok" if flow["label"] == "burst" else "bad",
                    "text": f"the tape is {'bursting' if flow['label'] == 'burst' else 'flushing'} ({flow['score']:+.2f})"})
    pulls = ctx.get("bid_pulls") or 0
    if pulls:
        out.append({"id": "pulls", "state": "warn",
                    "text": f"bids being pulled ({pulls} flag{'' if pulls == 1 else 's'} in the last minute)"})
    if ctx.get("halted") is True:
        out.append({"id": "halted", "state": "bad", "text": "halted now"})
    win = plan.get("window") or {}
    if plan.get("source") == "setup" and win.get("state") in ("before", "after"):
        out.append({"id": "window", "state": "warn",
                    "text": f"outside the bot's {win.get('start')}-{win.get('end')} window: a hand trade"})
    return out


def build(setups: list[dict[str, Any]], ctx: dict[str, Any], *, now: float, entry: float | None = None,
          stop: float | None = None) -> dict[str, Any] | None:
    """The plan for the read: the operator's when they named an entry, else the leading lane's."""
    if entry is not None and entry > 0:
        plan = manual(float(entry), stop, ctx.get("bars") or [])
    else:
        lane = choose(setups, now)
        if lane is None:
            return None
        plan = from_setup(lane)
        ctx = {**ctx, "stop_cap": (lane.get("rules") or {}).get("stop_cap") or ctx.get("stop_cap"),
               "min_stop": (lane.get("rules") or {}).get("min_stop"),
               "flow": ctx.get("flow") if lane.get("state") in LIVE_STATES else None}
    plan["checks"] = checks(plan, ctx)
    plan["marks"] = _obstacles(plan, ctx)
    plan["flow"] = ctx.get("flow") if (ctx.get("flow") or {}).get("label") else None
    return plan
