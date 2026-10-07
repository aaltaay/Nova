"""The plan on top of Level 2 (ADR 036): entry, stop and a target of at least 2R, and what stands in
the way. Pure.

A setup plan is the most advanced lane's own levels -- its armed (or triggered) setup, else the
levels it would arm with while it forms (provisional). A hand plan starts from the operator's entry:
the stop is theirs or the low of the last few closed one-minute candles, the target entry + 2R.
A plan has a ``side`` (ADR 048): a short plan -- a short setup's lane (``lane["side"]``), or the
operator's own plan with ``side="short"`` -- sells at its entry, protects with a buy stop over it
(theirs, or the high of the last few candles) and covers at entry - 2R; its checks, marks, level notes
and liquidity are the mirror (``plan_checks``, ``level_notes``, ``plan_liquidity``).
The checks and marks describe; they never block anything. ``trade`` says when a setup plan is not a
trade and why (operator report, 2026-09-29: a grade C that triggered with the tape at WAIT read
TRIGGERED for twenty minutes after its stop printed); it too only describes -- the runners and the
bot keep their own rules. ``liquidity`` (operator decision 2026-10-01, ``plan_liquidity.py``) says
whether the stock is too thin to trade: it leads the checks and a thin setup plan is not a trade.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_setups import (
    SETUP_OUTCOME_STOP_FIRST,
    SETUP_OUTCOME_TARGET_FIRST,
    SETUP_STATE_ARMED,
    SETUP_STATE_NEAR,
    SETUP_STATE_TRIGGERED,
)
from constants_stock_read import (
    STOCK_READ_MANUAL_STOP_BARS,
    STOCK_READ_TARGET_R,
    STOCK_READ_TRIGGERED_PLAN_SEC,
)
from setup_scanner.grade import pillar_count
from stock_read import plan_liquidity
from stock_read.indicators import manual_stop, manual_stop_short
from stock_read.level_notes import notes as level_notes
from stock_read.plan_checks import checks, obstacles

__all__ = ["build", "checks", "choose", "manual", "obstacles", "setup_name", "trade_verdict"]

ET = ZoneInfo("America/New_York")
FILTERED = "filtered"
LIVE_STATES = (SETUP_STATE_NEAR, SETUP_STATE_ARMED, FILTERED)
EPS = 1e-9
_NAMES = {"first_pullback": "first pullback", "bull_flag": "bull flag", "flat_top_breakout": "flat-top breakout",
          "flat_top_5m": "5-minute flat top", "red_to_green": "red to green", "gap_and_go": "Gap and Go"}
_ENTRY_RULES = {
    "first_pullback": "1 cent over the last pullback candle's high",
    "bull_flag": "1 cent over the last flag candle's high",
    "flat_top_breakout": "1 cent over the flat top (the taught entry waits for a candle to hold over it)",
    "flat_top_5m": "1 cent over the close of the first 1-minute candle that holds the 5-minute flat top after the break",
    "red_to_green": "1 cent over the open",
    "gap_and_go": "1 cent over the pre-market high, from the open",
}
_STOP_RULES = {
    "first_pullback": "the pullback's low",
    "bull_flag": "the flag's low",
    "flat_top_breakout": "the base's low",
    "flat_top_5m": "the 1-minute pullback's low, once a candle holds (the 5-minute base's low until then)",
    "red_to_green": "the lowest low since the open",
    "gap_and_go": "20 cents or 4% under the entry, whichever is smaller",
}


def setup_name(setup_type: str | None) -> str:
    return _NAMES.get(setup_type or "", (setup_type or "setup").replace("_", " "))


def _rank(lane: dict[str, Any], now: float) -> int | None:
    state, setup = lane.get("state"), lane.get("setup")
    if state == SETUP_STATE_NEAR and setup:
        return 0
    if state in (SETUP_STATE_ARMED, FILTERED) and setup and lane.get("phase") != SETUP_STATE_TRIGGERED:
        return 1
    if (state == SETUP_STATE_TRIGGERED or lane.get("phase") == SETUP_STATE_TRIGGERED) and setup:
        at = float(setup.get("triggered_at") or 0)
        return 2 if now - at <= STOCK_READ_TRIGGERED_PLAN_SEC else None
    return 3 if lane.get("forming") else None


def choose(setups: list[dict[str, Any]], now: float) -> dict[str, Any] | None:
    """The lane the plan follows: near, armed, triggered in the last 30 minutes, then forming; a setup
    at Strategy (the one Nova's bot would trade, ADR 042) first on a tie, then the playbook's order."""
    best: tuple[int, int, int] | None = None
    pick = None
    for i, lane in enumerate(setups):
        r = _rank(lane, now)
        if r is None:
            continue
        key = (r, 0 if lane.get("level") == 2 else 1, i)
        if best is None or key < best:
            best, pick = key, lane
    return pick


def target_rule(setup_type: str, rules: dict[str, Any], side: str = "long") -> str:
    r = rules.get("target_r") or STOCK_READ_TARGET_R
    mode = rules.get("target_mode") or "r"
    if side == "short":     # a short covers under its entry (ADR 049: entry - 2 x risk)
        return "a fixed amount under the entry (the template's)" if mode == "fixed" else f"entry - {r:g} x risk"
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
    where = (lane.get("phase") or state) if state == FILTERED else state   # a filtered pattern's own state
    tape = lane.get("tape")
    if where == SETUP_STATE_TRIGGERED and lane.get("trigger_tape"):
        tape = lane["trigger_tape"]            # the tape the trigger printed on, not the last read
    if live:
        shown = {SETUP_STATE_NEAR: "near", SETUP_STATE_TRIGGERED: "triggered"}.get(where, "armed")
        reason = lane.get("reason") or ""
    else:
        shown = "forming"
        bits = [lane.get("reason") or ""]
        if lv.get("waiting"):
            bits.append(f"arms after {lv['waiting']}")
        if lv.get("blocked") and lv.get("blocked") not in bits[0]:
            bits.append(f"blocked: {lv['blocked']}")
        reason = " -- ".join(b for b in bits if b)
    side = "short" if lane.get("side") == "short" else "long"
    return _levels({
        "source": "setup", "side": side, "setup_type": lane.get("setup_type"),
        "setup_id": lane.get("setup_id") if live else None, "kind": lane.get("kind"), "state": shown,
        "provisional": not live, "trigger": lv.get("trigger"), "grade": lane.get("grade"),
        "pillars": pillar_count((lane.get("pillars") or {}).get("checks")), "reason": reason,
        "target_rule": target_rule(lane.get("setup_type") or "", lane.get("rules") or {}, side),
        "entry_rule": _ENTRY_RULES.get(lane.get("setup_type") or "",
                                       "the setup's trigger - 1 cent" if side == "short"
                                       else "the setup's trigger + 1 cent"),
        "stop_rule": _STOP_RULES.get(lane.get("setup_type") or "", "the setup's stop"),
        "tape": ({"verdict": tape.get("verdict"), "reasons": tape.get("reasons") or []}
                 if live and tape else None),
        "window": lane.get("window"),
    }, entry, stop, target)


def manual(entry: float, stop: float | None, bars: list[dict[str, Any]], side: str = "long") -> dict[str, Any]:
    """The operator's own plan: their entry, their stop or the last candles' low, a 2R target. A short
    (``side="short"``): their buy stop over the entry or the last candles' high, a cover at entry - 2R."""
    short = side == "short"
    own = stop is not None and (stop > entry + EPS if short else stop < entry - EPS)
    if own:
        stop_px = stop
    elif short:
        stop_px = manual_stop_short(bars, entry, STOCK_READ_MANUAL_STOP_BARS)
    else:
        stop_px = manual_stop(bars, entry, STOCK_READ_MANUAL_STOP_BARS)
    extreme = "highest high" if short else "lowest low"
    base = {"source": "manual", "side": "short" if short else "long", "setup_type": None, "setup_id": None,
            "kind": None, "state": "manual", "provisional": True,
            "trigger": None, "grade": None, "pillars": None,
            "reason": ("no setup is forming: your short, a 2:1 cover" if short
                       else "no setup is forming: your entry, a 2:1 target"),
            "target_rule": f"entry {'-' if short else '+'} {STOCK_READ_TARGET_R:g} x risk",
            "entry_rule": "your entry",
            "stop_rule": (("your buy stop" if short else "your stop") if own
                          else f"the {extreme} of the last {STOCK_READ_MANUAL_STOP_BARS} closed 1-min candles"),
            "tape": None, "window": None}
    if stop_px is None:
        missing = ("no candle high over your entry to stop at -- name a buy stop" if short
                   else "no candle low under your entry to stop at -- name a stop")
        return {**base, "entry": round(entry, 4), "stop": None, "target": None, "risk": None, "reward": None,
                "rr": None, "reason": missing}
    risk = abs(entry - stop_px)
    return _levels(base, entry, stop_px, entry - STOCK_READ_TARGET_R * risk if short
                   else entry + STOCK_READ_TARGET_R * risk)


def _levels(plan: dict[str, Any], entry: float, stop: float, target: float) -> dict[str, Any]:
    """Risk and reward a share, either side: the distance to the stop and to the target."""
    risk, reward = round(abs(entry - stop), 4), round(abs(target - entry), 4)
    return {**plan, "entry": round(entry, 4), "stop": round(stop, 4), "target": round(target, 4), "risk": risk,
            "reward": reward, "rr": round(reward / risk, 2) if risk > EPS else None}


def _hhmm(ts: Any) -> str:
    try:
        return datetime.fromtimestamp(float(ts), ET).strftime("%H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def result_of(plan: dict[str, Any], lane: dict[str, Any] | None) -> dict[str, Any] | None:
    """A triggered setup's first touch once it printed: target 1 or the stop, when, and the score's R."""
    if lane is None or plan.get("state") != "triggered":
        return None
    outcome = lane.get("outcome")
    if outcome not in (SETUP_OUTCOME_TARGET_FIRST, SETUP_OUTCOME_STOP_FIRST):
        return None
    at, r = lane.get("outcome_at"), lane.get("bar_r")
    what = "target 1 printed first" if outcome == SETUP_OUTCOME_TARGET_FIRST else "the stop printed first"
    when = f" at {_hhmm(at)}" if at else ""
    score = f" ({float(r):+.2f}R)" if r is not None else ""
    return {"outcome": outcome, "at": at, "r": r, "text": f"{what}{when}{score}"}


def trade_verdict(plan: dict[str, Any], lane: dict[str, Any] | None,
                  spread: float | None = None, liquidity: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Whether a setup plan is a trade, with every reason it is not; None for the operator's own plan.

    The rule is ``setup_scanner.trade_verdict`` -- the one Nova's bot, Auto-entry, Approve and the
    proposals ask too (ADR 042 H)."""
    from setup_scanner.trade_verdict import verdict

    if plan.get("source") != "setup":
        return None
    filtered: str | bool | None = None
    if (lane or {}).get("state") == FILTERED:
        filtered = str((lane or {}).get("reason") or "") or True
    return verdict(grade=plan.get("grade"), pillars=plan.get("pillars"), filtered=filtered,
                   triggered=plan.get("state") == "triggered", tape=plan.get("tape"),
                   played_out=(plan.get("result") or {}).get("text"), spread=spread, risk=plan.get("risk"),
                   liquidity=liquidity)


def build(setups: list[dict[str, Any]], ctx: dict[str, Any], *, now: float, entry: float | None = None,
          stop: float | None = None, side: str = "long") -> dict[str, Any] | None:
    """The plan for the read: the operator's when they named an entry (``side``: theirs), else the leading lane's."""
    lane = None
    if entry is not None and entry > 0:
        plan = manual(float(entry), stop, ctx.get("bars") or [], side)
    else:
        lane = choose(setups, now)
        if lane is None:
            return None
        plan = from_setup(lane)
        ctx = {**ctx, "stop_cap": (lane.get("rules") or {}).get("stop_cap") or ctx.get("stop_cap"),
               "min_stop": (lane.get("rules") or {}).get("min_stop"),
               "flow": ctx.get("flow") if lane.get("state") in LIVE_STATES else None}
    plan["liquidity"] = plan_liquidity.read(ctx, now, plan.get("risk"), plan.get("side") or "long")
    plan["checks"] = [plan_liquidity.check(plan["liquidity"]), *checks(plan, ctx)]
    plan["marks"] = obstacles(plan, ctx)
    plan["flow"] = ctx.get("flow") if (ctx.get("flow") or {}).get("label") else None
    plan["result"] = result_of(plan, lane)
    plan["trade"] = trade_verdict(plan, lane, ctx.get("spread"), plan["liquidity"])
    plan["levels"] = level_notes(plan, ctx.get("level_map"), ctx.get("bars") or [], price=ctx.get("price"), now=now)
    return plan
