"""The plan on top of Level 2 (ADR 036): entry, stop, two targets, and what stands in the way. Pure.

A setup plan is the most advanced lane's own levels -- its armed (or triggered) setup, else the
levels it would arm with while it forms (provisional). A hand plan starts from the operator's entry:
the stop is theirs or the low of the last few closed one-minute candles. The targets are the menu's
(#845, ``setup_scanner/targets.py``): a setup plan's are its lane's, each with its reason ("+20c",
"1c under $5.50", "1c under HOD 6.12"); a hand plan's are the menu's defaults from today's map and the
high of day. ``target`` is target 1 (the first part's sell), ``target2`` the rest's or None, and
``target1_fraction`` the share sold at target 1. A plan has a ``side`` (ADR 048): a short plan -- a short
setup's lane (``lane["side"]``), or the operator's own plan with ``side="short"`` -- sells at its entry,
protects with a buy stop over it (theirs, or the high of the last few candles) and covers at its targets
under it; its checks, marks, level notes and liquidity are the mirror (``plan_checks``, ``level_notes``,
``plan_liquidity``).
The checks and marks describe; they never block anything. ``trade`` says when a setup plan is not a
trade and why (operator report, 2026-09-29: a grade C that triggered with the tape at WAIT read
TRIGGERED for twenty minutes after its stop printed); it too only describes -- the runners and the
bot keep their own rules. ``liquidity`` (operator decision 2026-10-01, ``plan_liquidity.py``) says
whether the stock is too thin to trade: it leads the checks and a thin setup plan is not a trade.
A watch-only setup (#847, the pullback dip) leads the plan only when no tradeable lane has anything to show,
and its plan is never a trade.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_bot import watch_only
from constants_setups import (
    SETUP_OUTCOME_STOP_FIRST,
    SETUP_OUTCOME_TARGET_FIRST,
    SETUP_STATE_ARMED,
    SETUP_STATE_NEAR,
    SETUP_STATE_TRIGGERED,
)
from constants_stock_read import (
    STOCK_READ_MANUAL_STOP_BARS,
    STOCK_READ_TRIGGERED_PLAN_SEC,
)
from setup_scanner import targets as target_menu
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
          "flat_top_5m": "5-minute flat top", "red_to_green": "red to green", "gap_and_go": "Gap and Go",
          "pullback_dip": "pullback dip", "abcd": "ABCD",
          # ADR 049: the short setups.
          "backside_lower_high": "backside lower high", "bear_flag": "bear flag", "failed_breakout": "failed breakout",
          "lost_vwap": "lost VWAP", "ssr_bounce": "SSR bounce short"}
_ENTRY_RULES = {
    "first_pullback": "1 cent over the last pullback candle's high",
    "bull_flag": "1 cent over the last flag candle's high",
    "flat_top_breakout": "1 cent over the flat top (the taught entry waits for a candle to hold over it)",
    "flat_top_5m": "1 cent over the close of the first 1-minute candle that holds the 5-minute flat top after the break",
    "red_to_green": "1 cent over the open",
    "gap_and_go": "1 cent over the pre-market high, from the open",
    "pullback_dip": "1 cent over the close of the candle that bottoms the pullback (a bottoming wick, or the first "
                    "green close)",
    "abcd": "1 cent over B, the push that failed under the high",
    "backside_lower_high": "1 cent under the last bounce candle's low",
    "bear_flag": "1 cent under the last flag candle's low",
    "failed_breakout": "1 cent under the low of the candle that closed back under the flat top",
    "lost_vwap": "1 cent under the low of the candle that failed at VWAP",
    "ssr_bounce": "a short resting 1 cent under the level the bounce runs into",
}
_STOP_RULES = {
    "first_pullback": "the pullback's low",
    "bull_flag": "the flag's low",
    "flat_top_breakout": "the base's low",
    "flat_top_5m": "the 1-minute pullback's low, once a candle holds (the 5-minute base's low until then)",
    "red_to_green": "the lowest low since the open",
    "gap_and_go": "20 cents or 4% under the entry, whichever is smaller",
    "pullback_dip": "1 cent under the pullback's low",
    "abcd": "1 cent under C, the higher low",
    "backside_lower_high": "1 cent over the bounce's high",
    "bear_flag": "1 cent over the flag's high",
    "failed_breakout": "1 cent over the poke's high",
    "lost_vwap": "1 cent over the retest's high, or over VWAP when VWAP is higher",
    "ssr_bounce": "2% over the entry, at least 5 cents",
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
    at Strategy (the one Nova's bot would trade, ADR 042) first on a tie, then the playbook's order. A
    watch-only setup (#847) follows every tradeable lane that has something to show."""
    best: tuple[int, int, int, int] | None = None
    pick = None
    for i, lane in enumerate(setups):
        r = _rank(lane, now)
        if r is None:
            continue
        key = (1 if watch_only(lane.get("setup_type")) else 0, r, 0 if lane.get("level") == 2 else 1, i)
        if best is None or key < best:
            best, pick = key, lane
    return pick


def target_rule(rule: dict[str, Any] | None) -> str:
    """The strategy's choice from the menu in words: "target 1: ...; target 2: ...; half at target 1"."""
    spec = target_menu.TargetSpec(**{k: v for k, v in (rule or {}).items()
                                     if k in ("first", "second", "fixed", "split", "stop")})
    one = target_menu.words(spec.first, fixed=spec.fixed)
    two = target_menu.words(spec.second, second=True, fixed=spec.fixed)
    split = f"{round(spec.split * 100):d}% at target 1" if spec.second != "none" else "everything at target 1"
    return f"target 1: {one}; target 2: {two}; {split}"


def _targets_of(lv: dict[str, Any]) -> dict[str, Any]:
    """A levels dict's target fields (``targets.Targets.wire``), None where it carries none."""
    return {"target2": lv.get("target2"), "target1_fraction": lv.get("target1_fraction"),
            "targets": lv.get("targets")}


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
    stop_choice = (lv.get("targets") or {}).get("stop") or {}      # the template's round-number stop (#845)
    return _levels({
        "source": "setup", "side": side, "setup_type": lane.get("setup_type"),
        "setup_id": lane.get("setup_id") if live else None, "kind": lane.get("kind"), "state": shown,
        "provisional": not live, "trigger": lv.get("trigger"), "grade": lane.get("grade"),
        "pillars": pillar_count((lane.get("pillars") or {}).get("checks")), "reason": reason,
        "target_rule": target_rule((lv.get("targets") or {}).get("rule") or (lane.get("rules") or {}).get("targets")),
        "entry_rule": _ENTRY_RULES.get(lane.get("setup_type") or "",
                                       "the setup's trigger - 1 cent" if side == "short"
                                       else "the setup's trigger + 1 cent"),
        "stop_rule": (stop_choice.get("why") if stop_choice.get("kind") == "round"
                      else _STOP_RULES.get(lane.get("setup_type") or "", "the setup's stop")),
        "tape": ({"verdict": tape.get("verdict"), "reasons": tape.get("reasons") or []}
                 if live and tape else None),
        "window": lane.get("window"),
    }, entry, stop, target, **_targets_of(lv))


def manual(entry: float, stop: float | None, bars: list[dict[str, Any]], side: str = "long", *,
           level_map: dict[str, Any] | None = None) -> dict[str, Any]:
    """The operator's own plan: their entry, their stop or the last candles' low, and the menu's default
    targets from today's map (``level_map``) and the high of day. A short (``side="short"``): their buy stop
    over the entry or the last candles' high, the targets under the entry."""
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
            "reason": ("no setup is forming: your short, the menu's cover targets" if short
                       else "no setup is forming: your entry, the menu's targets"),
            "target_rule": target_rule(None),
            "entry_rule": "your entry",
            "stop_rule": (("your buy stop" if short else "your stop") if own
                          else f"the {extreme} of the last {STOCK_READ_MANUAL_STOP_BARS} closed 1-min candles"),
            "tape": None, "window": None}
    if stop_px is None:
        missing = ("no candle high over your entry to stop at -- name a buy stop" if short
                   else "no candle low under your entry to stop at -- name a stop")
        return {**base, "entry": round(entry, 4), "stop": None, "target": None, "target2": None,
                "target1_fraction": None, "targets": None, "risk": None, "reward": None, "rr": None,
                "reward2": None, "rr2": None, "reason": missing}
    highs = [float(b["l"] if short else b["h"]) for b in bars]
    extreme = (min(highs) if short else max(highs)) if highs else None
    got = target_menu.plan(None, side=side if short else "long", entry=entry,
                           levels=(level_map or {}).get("intraday"), hod=extreme)
    aim = got.wire()
    return _levels(base, entry, stop_px, aim["target1"], target2=aim["target2"],
                   target1_fraction=aim["target1_fraction"], targets=aim["targets"])


def _levels(plan: dict[str, Any], entry: float, stop: float, target: float, *, target2: float | None = None,
            target1_fraction: float | None = None, targets: dict[str, Any] | None = None) -> dict[str, Any]:
    """Risk and reward a share, either side: the distance to the stop and to each target; ``rr`` / ``rr2`` are
    the targets in R (the unit results are measured in, never a target)."""
    risk, reward = round(abs(entry - stop), 4), round(abs(target - entry), 4)
    reward2 = round(abs(target2 - entry), 4) if target2 is not None else None
    return {**plan, "entry": round(entry, 4), "stop": round(stop, 4), "target": round(target, 4),
            "target2": round(target2, 4) if target2 is not None else None,
            "target1_fraction": target1_fraction if target1_fraction is not None else 1.0, "targets": targets,
            "risk": risk, "reward": reward, "rr": round(reward / risk, 2) if risk > EPS else None,
            "reward2": reward2, "rr2": round(reward2 / risk, 2) if reward2 is not None and risk > EPS else None}


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
                   liquidity=liquidity, setup_type=plan.get("setup_type"))


def build(setups: list[dict[str, Any]], ctx: dict[str, Any], *, now: float, entry: float | None = None,
          stop: float | None = None, side: str = "long") -> dict[str, Any] | None:
    """The plan for the read: the operator's when they named an entry (``side``: theirs), else the leading lane's."""
    lane = None
    if entry is not None and entry > 0:
        plan = manual(float(entry), stop, ctx.get("bars") or [], side, level_map=ctx.get("level_map"))
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
