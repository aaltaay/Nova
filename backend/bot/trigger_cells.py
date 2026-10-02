"""How each trigger of a day met Nova's ten gates (ADR 043, the squares). Pure.

``triggers(lines)`` folds a day's eyes' journal -- the lines of each setup's template in play
(``playing: true``) -- into its triggers: the first ``triggered`` line of each setup id (a restart's
warm-up says the same trigger again), with its grade (its ``armed`` line) and its score (its last
``scored`` line). ``judge(trigger, ctx)`` meets it with the gates in the order Nova runs them
(``BOT_TRIGGER_GATES``), from what was recorded at the trigger:

- ``bot_on``: the bot's state the journal stamped on the line (``bot: {level, active, venue}``);
- ``strategy_on`` / ``nova_buys``: the strategy's own level and the stock's mode on the trigger's
  venue at its moment (``bot.trigger_timeline``);
- ``grade``: the grade it armed with against the strategy's ``bot_grades``, and NOT A TRADE's
  checks of the setup itself -- grade C, the spread at or over the risk, too thin to trade
  (``setup_scanner.trade_verdict``): Nova's bot reads them on the same trigger;
- ``setups_a_day``: the setup's ``nth`` against ``bot_setups_a_day``;
- ``bot_window``: the trigger's time against the strategy's bot window;
- ``hot_list``: on the day's hot list at or before the trigger;
- ``level2_line`` / ``tape_go``: the tape the lane read at the trigger. BLIND is the Level 2 line's
  red, never the tape's (``tape_go`` did not apply);
- ``trades_today`` (``take_cap``): the venue's daily cap -- the first trigger that passes every other
  gate takes it.

The strategy's bot rules and window are not recorded at a trigger: they are today's
(``BOT_TRIGGER_JUDGED_NOW``). ``{ok: null}`` is a gate that did not apply, or that nothing recorded;
its ``why`` says which. Owner: this module (no state).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from bot import strategy_rules
from bot.trigger_timeline import UNKNOWN, Timeline
from constants_bot import BOT_LEVEL_STRATEGY, BOT_SETUP_FIRST_PULLBACK, BOT_TRIGGER_GATES, BOT_TZ
from constants_setups import TAPE_VERDICT_BLIND, TAPE_VERDICT_GO
from constants_stock_mode import STOCK_MODE_APPROVE, STOCK_MODE_AUTO_ENTRY, STOCK_MODE_BOT, STOCK_MODE_SIGNAL

GATE_IDS = tuple(gate for gate, _label in BOT_TRIGGER_GATES)
_ET = ZoneInfo(BOT_TZ)
# A ``session`` line this long after midnight ET is Nova starting, not the eyes' date turning.
RESTART_AFTER_MIDNIGHT_SEC = 300.0
_MODE_WORDS = {
    STOCK_MODE_AUTO_ENTRY: (True, "Buy was Nova (Auto-entry: Nova buys, you sell)"),
    STOCK_MODE_BOT: (True, "Buy was Nova (Bot: Nova buys and sells)"),
    STOCK_MODE_SIGNAL: (False, "Buy was You (Signal only): Nova buys only stocks whose Buy is Nova"),
    STOCK_MODE_APPROVE: (False, "Buy was You (Approve: Nova sends only a plan you approve)"),
}


def cell(ok: bool | None, why: str) -> dict[str, Any]:
    return {"ok": ok, "why": why}


def num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def hhmm(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), _ET).strftime("%H:%M")


def _minutes(text: Any) -> int | None:
    try:
        hour, minute = str(text).split(":")[:2]
        return int(hour) * 60 + int(minute)
    except (TypeError, ValueError):
        return None


# -- the day's triggers -------------------------------------------------------------------
def triggers(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The day's triggers of the templates in play, oldest first."""
    armed: dict[str, list[tuple[float, Any]]] = {}
    scored: dict[str, dict[str, Any]] = {}
    first: dict[str, dict[str, Any]] = {}
    for line in lines:
        sid = line.get("setup_id")
        if line.get("playing") is not True or not sid:
            continue
        event = line.get("event")
        if event == "armed":
            armed.setdefault(sid, []).append((num(line.get("ts")) or 0.0, line.get("grade")))
        elif event == "scored":
            scored[sid] = line
        elif event == "triggered" and sid not in first:
            first[sid] = line
    out = []
    for sid, line in first.items():
        setup = line.get("setup") if isinstance(line.get("setup"), dict) else {}
        ts = num(setup.get("triggered_at")) or num(line.get("ts")) or 0.0
        setup_type = str(line.get("setup_type") or BOT_SETUP_FIRST_PULLBACK)
        arms = armed.get(sid) or []
        grade = next((g for t, g in reversed(arms) if t <= ts + 1e-6), arms[-1][1] if arms else None)
        score = scored.get(sid) or {}
        out.append({"ts": ts, "symbol": str(line.get("symbol") or "").upper(), "setup_id": sid,
                    "setup_type": setup_type, "kind": setup.get("kind"),
                    "nth": strategy_rules.number_of(setup, setup_type), "grade": grade,
                    "tape": line.get("tape") if isinstance(line.get("tape"), dict) else None, "setup": setup,
                    "bot": line.get("bot") if isinstance(line.get("bot"), dict) else None,
                    "liquidity": line.get("liquidity"), "outcome": score.get("outcome"),
                    "r": num(score.get("bar_r"))})
    out.sort(key=lambda t: t["ts"])
    return out


def restarts(lines: list[dict[str, Any]], day_start: float) -> list[float]:
    """When Nova started that day: the eyes' ``session`` lines, less the one the date's turn writes."""
    out = []
    for line in lines:
        ts = num(line.get("ts"))
        if line.get("event") == "session" and ts is not None and ts - day_start > RESTART_AFTER_MIDNIGHT_SEC:
            out.append(ts)
    return sorted(out)


# -- the cells ------------------------------------------------------------------------------
@dataclass
class Context:
    """What a trigger is judged against: the recorded changes, today's rules and the settings now."""

    timeline: Timeline
    rules: dict[str, dict[str, Any]]                     # setup -> {grades, setups_a_day, window, error}
    listed: dict[str, dict[str, Any]] = field(default_factory=dict)   # symbol -> its hot list entry
    hot_error: str | None = None
    audit_error: str | None = None
    level_now: Callable[[str | None, str], Any] = lambda venue, setup: None
    mode_now: Callable[[str | None, str], Any] = lambda venue, symbol: UNKNOWN
    cap_now: Callable[[str | None], Any] = lambda venue: None


def _bot_on(bot: dict[str, Any] | None) -> dict[str, Any]:
    level, active = num((bot or {}).get("level")), (bot or {}).get("active")
    if level is None or active is None:
        return cell(None, "the journal did not record the bot's state at this trigger")
    if level >= BOT_LEVEL_STRATEGY and active:
        return cell(True, "the bot was on")
    said = {0: " (at Off)", 1: " (at Eyes)"}.get(int(level), " (not turned on)")
    return cell(False, f"the bot was off{said}")


def _strategy_on(t: dict[str, Any], venue: str | None, ctx: Context) -> dict[str, Any]:
    name = strategy_rules.name(t["setup_type"])
    if venue is None:
        return cell(None, "the journal did not record the venue at this trigger")
    if ctx.audit_error:
        return cell(None, ctx.audit_error)
    level = ctx.timeline.level_at(venue, t["setup_type"], t["ts"], lambda: ctx.level_now(venue, t["setup_type"]))
    try:
        level = int(level)
    except (TypeError, ValueError):
        return cell(None, f"the {name}'s level at this trigger is not recorded")
    if level >= BOT_LEVEL_STRATEGY:
        return cell(True, f"the {name} was On")
    said = "at Eyes" if level == 1 else "Off"
    return cell(False, f"the {name} was {said}: Nova buys only the strategies that are On")


def _grade(t: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    from setup_scanner.trade_verdict import verdict

    setup, tape = t.get("setup") or {}, t.get("tape") or {}
    spread = (tape.get("metrics") or {}).get("spread") if isinstance(tape.get("metrics"), dict) else None
    reasons = list(verdict(grade=t.get("grade"), spread=spread, risk=setup.get("risk"),
                           liquidity=t.get("liquidity"))["reasons"])
    if t.get("grade"):
        block = strategy_rules.grade_block(t["grade"], rules["grades"])
        if block:
            reasons.append(block)
    if reasons:
        return cell(False, "; ".join(reasons))
    if not t.get("grade"):
        return cell(None, "no armed line recorded this setup's grade")
    return cell(True, f"grade {t['grade']}: this strategy buys {strategy_rules.GRADES_WORDS[rules['grades']]}")


def _setups_a_day(t: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    block = strategy_rules.nth_block(t["nth"], rules["setups_a_day"], t["setup_type"])
    if block:
        return cell(False, block)
    return cell(True, f"the {strategy_rules.ordinal(t['nth'])} {strategy_rules.name(t['setup_type'])} of the day")


def _window(t: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    w = rules.get("window") or {}
    start, end = _minutes(w.get("start")), _minutes(w.get("end"))
    if start is None or end is None:
        return cell(None, "the strategy's bot window could not be read")
    at = datetime.fromtimestamp(t["ts"], _ET)
    inside = start <= at.hour * 60 + at.minute < end
    said = "inside" if inside else "outside"
    return cell(inside, f"{at:%H:%M} ET, {said} the {w['start']}-{w['end']} bot window")


def _hot(t: dict[str, Any], ctx: Context) -> dict[str, Any]:
    if ctx.hot_error:
        return cell(None, ctx.hot_error)
    entry = ctx.listed.get(t["symbol"])
    if entry is None:
        return cell(False, f"{t['symbol']} was not on the day's hot list")
    at = num(entry.get("at"))
    how = "starred" if entry.get("how") == "star" else "listed by the leaders rule"
    if at is not None and at > t["ts"]:
        return cell(False, f"{how} at {hhmm(at)} ET, after this trigger")
    return cell(True, f"{how}" + (f" at {hhmm(at)} ET" if at is not None else ""))


def _nova_buys(t: dict[str, Any], venue: str | None, ctx: Context) -> dict[str, Any]:
    if venue is None:
        return cell(None, "the journal did not record the venue at this trigger")
    if ctx.audit_error:
        return cell(None, ctx.audit_error)
    mode = ctx.timeline.mode_at(venue, t["symbol"], t["ts"], lambda: ctx.mode_now(venue, t["symbol"]))
    if mode in _MODE_WORDS:
        return cell(*_MODE_WORDS[mode])
    return cell(None, f"not known: a restart or the 04:00 rollover came between this trigger and the last record of "
                      f"who trades {t['symbol']}")


def _tape(t: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    tape = t.get("tape")
    if not tape:
        missing = cell(None, "the journal did not record the tape at this trigger")
        return missing, missing
    verdict = str(tape.get("verdict") or "")
    first = next(iter(tape.get("reasons") or ()), None)
    line = tape.get("line") if isinstance(tape.get("line"), dict) else {}
    if verdict == TAPE_VERDICT_BLIND or line.get("depth") is False:
        said = first or f"Nova held no Level 2 line on {t['symbol']}"
        return cell(False, f"BLIND: {said}"), cell(None, "not read: no Level 2 line")
    held = cell(True, f"Nova held {t['symbol']}'s Level 2 line")
    words = f"{verdict.upper() or 'NOTHING'}" + (f": {first}" if first else "")
    return held, cell(verdict == TAPE_VERDICT_GO, words)


def judge(t: dict[str, Any], ctx: Context) -> dict[str, dict[str, Any]]:
    """Every gate but the daily cap (``take_cap``), in Nova's order."""
    venue = (t.get("bot") or {}).get("venue")
    rules = ctx.rules.get(t["setup_type"]) or {}
    line, tape = _tape(t)
    return {"bot_on": _bot_on(t.get("bot")), "strategy_on": _strategy_on(t, venue, ctx),
            "grade": _grade(t, rules) if rules else cell(None, "the strategy's bot rules could not be read"),
            "setups_a_day": _setups_a_day(t, rules) if rules else cell(None, "the strategy's bot rules could not "
                                                                             "be read"),
            "bot_window": _window(t, rules), "hot_list": _hot(t, ctx), "nova_buys": _nova_buys(t, venue, ctx),
            "level2_line": line, "tape_go": tape, "trades_today": cell(None, "")}


def _entries(n: int) -> str:
    return f"{n} Nova entr{'y' if n == 1 else 'ies'}"


def take_cap(judged: list[dict[str, Any]], ctx: Context) -> None:
    """The venue's daily cap, oldest first: the first trigger that passes every other gate takes it."""
    taken: dict[str | None, list[dict[str, Any]]] = {}
    for t in judged:
        venue = (t.get("bot") or {}).get("venue")
        read = num(ctx.timeline.cap_at(venue, t["ts"], lambda v=venue: ctx.cap_now(v)))
        if read is None or read < 1:
            t["cells"]["trades_today"] = cell(None, "the venue's daily cap could not be read")
            continue
        cap = int(read)
        used = taken.setdefault(venue, [])
        passes = all(c["ok"] is not False for g, c in t["cells"].items() if g != "trades_today")
        if len(used) >= cap:
            went = ", ".join(f"{u['symbol']} at {hhmm(u['ts'])} ET" for u in used)
            t["cells"]["trades_today"] = cell(False, f"the day's {_entries(cap)} went to {went}")
            continue
        if passes:
            used.append(t)
            t["cells"]["trades_today"] = cell(True, f"it takes Nova's {strategy_rules.ordinal(len(used))} entry of "
                                                    f"the day ({_entries(cap)} a day)")
        else:
            t["cells"]["trades_today"] = cell(True, f"{len(used)} of {_entries(cap)} a day used before it")


def reasons(cells: dict[str, dict[str, Any]]) -> list[str]:
    return [cells[g]["why"] for g in GATE_IDS if cells.get(g, {}).get("ok") is False]


def impact(judged: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What each gate did: the triggers it held back, how they came out, and their R summed."""
    out = []
    for gate in GATE_IDS:
        held = [t for t in judged if t["cells"][gate]["ok"] is False]
        r = [t["r"] for t in held if t.get("r") is not None]
        out.append({"gate": gate, "blocked": len(held),
                    "target_first": sum(1 for t in held if t.get("outcome") == "target_first"),
                    "stop_first": sum(1 for t in held if t.get("outcome") == "stop_first"),
                    "r": round(sum(r), 3)})
    return out


def wire(t: dict[str, Any]) -> dict[str, Any]:
    """One trigger as the squares draw it."""
    return {"ts": t["ts"], "setup_id": t["setup_id"], "setup_type": t["setup_type"], "kind": t.get("kind"),
            "nth": t["nth"], "grade": t.get("grade"), "tape": (t.get("tape") or {}).get("verdict"),
            "outcome": t.get("outcome"), "r": t.get("r"), "cells": t["cells"], "reasons": reasons(t["cells"])}
