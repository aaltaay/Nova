"""The squares' ``now`` row (ADR 043): would Nova buy this listed stock if its setup triggered this minute?

The same ten gates as a trigger (``bot.trigger_cells``), read from the desk as it stands -- the desk
venue's dial, the strategies' rules today, the live setup board, the Who trades switch, the depth
lines held and the day's Nova entries:

- ``bot_on``: the Bot switch reads ON (``bot.switch``), else why not;
- ``strategy_on``: a strategy is On;
- ``grade``: ``null`` unless a setup of a strategy that is On is armed or near on the stock -- then its
  grade against the strategy's ``bot_grades`` and NOT A TRADE's checks (grade C, too thin);
- ``setups_a_day``: an On strategy may still buy its next setup on the stock today;
- ``bot_window``: an On strategy's bot window is open now;
- ``hot_list``: true (only listed stocks have a ``now`` row);
- ``nova_buys``: the stock's Buy is Nova on the desk's venue (Auto-entry or Bot);
- ``level2_line``: Nova holds the stock's Level 2 line now; ``null`` when it does not -- a line may
  still open, or be lent, before the trigger;
- ``tape_go``: ``null`` -- the tape is read at the trigger;
- ``trades_today``: the venue's daily cap has room.

``answer`` is ``yes`` only when no gate is false; ``reasons`` are the false gates' words. Owner: this
module (no state; it reads, never writes).
"""
from __future__ import annotations

import logging
from typing import Any

from bot import strategy_rules
from bot.trigger_cells import GATE_IDS, cell, hhmm, num
from constants_bot import BOT_GRADES_A, BOT_LEVEL_STRATEGY
from constants_stock_mode import STOCK_MODE_AUTO_ENTRY, STOCK_MODE_BOT

logger = logging.getLogger(__name__)
_ARMED = ("armed", "near")


class Desk:
    """What every ``now`` row of one answer shares: read once."""

    def __init__(self, now_state: Any, rules: dict[str, dict[str, Any]]):
        from bot import entry_rules
        from bot.setup_levels import own_levels

        self.now = now_state
        self.rules = rules
        self.row = now_state.row
        self.venue = now_state.venue
        own = own_levels(self.row)
        self.on = [s for s, level in own.items() if level >= BOT_LEVEL_STRATEGY]
        self.cap = now_state.cap(self.venue)
        try:
            self.used: int | None = int(entry_rules.today(self.venue, cap=self.cap)["count"])
        except Exception:
            logger.warning("triggers audit: the day's Nova entries could not be counted", exc_info=True)
            self.used = None


def desk(now_state: Any, rules: dict[str, dict[str, Any]]) -> Desk | None:
    """The desk as it stands, or None when it cannot be read (every ``now`` row says so)."""
    if now_state is None:
        return None
    try:
        return Desk(now_state, rules)
    except Exception:
        logger.warning("triggers audit: the desk could not be read -- no answer for now", exc_info=True)
        return None


def _lanes(sym: str) -> list[dict[str, Any]] | None:
    try:
        from setup_scanner.engine import get_engine
        from setup_scanner.symbol_view import symbol_view

        return list(symbol_view(get_engine(), sym).get("setups") or [])
    except Exception:
        logger.warning("triggers audit: the setup board for %s could not be read", sym, exc_info=True)
        return None


def _grade(sym: str, desk: Desk, lanes: list[dict[str, Any]] | None) -> dict[str, Any]:
    from setup_scanner.trade_verdict import verdict

    if lanes is None:
        return cell(None, "the setup board could not be read (the backend log has the error)")
    armed = [lane for lane in lanes if lane.get("setup_type") in desk.on
             and (lane.get("state") in _ARMED or (lane.get("state") == "filtered" and lane.get("phase") in _ARMED))]
    if not armed:
        return cell(None, f"no setup of a strategy that is On is armed or near on {sym}")
    whys = []
    for lane in armed:
        name = strategy_rules.name(lane.get("setup_type"))
        reasons = list(verdict(grade=lane.get("grade"), liquidity=lane.get("liquidity"))["reasons"])
        if lane.get("state") == "filtered":
            reasons.append("the template's stock filter keeps it out")
        grades = desk.rules.get(lane["setup_type"], {}).get("grades", BOT_GRADES_A)   # unread: the strictest
        block = strategy_rules.grade_block(lane.get("grade"), grades)
        if block:
            reasons.append(block)
        if not reasons:
            return cell(True, f"the {name} is {lane['state']} at grade {lane.get('grade')}")
        whys.append(f"the {name}: " + "; ".join(reasons))
    return cell(False, " | ".join(whys))


def _setups_a_day(sym: str, desk: Desk, todays: list[dict[str, Any]]) -> dict[str, Any]:
    if not desk.on:
        return cell(None, "no strategy is On")
    blocks = []
    for setup in desk.on:
        done = [t for t in todays if t["symbol"] == sym and t["setup_type"] == setup]
        number = max((t["nth"] for t in done), default=0) + 1
        rule = desk.rules.get(setup, {}).get("setups_a_day", 1)
        block = strategy_rules.nth_block(number, rule, setup)
        if block is None:
            return cell(True, f"the next {strategy_rules.name(setup)} would be its {strategy_rules.ordinal(number)} "
                              "today")
        last = done[-1]
        blocks.append(f"the {strategy_rules.name(setup)} already triggered at {hhmm(last['ts'])} ET: {block}")
    return cell(False, "; ".join(blocks))


def _window(desk: Desk) -> dict[str, Any]:
    from bot import entry_rules

    if not desk.on:
        return cell(None, "no strategy is On")
    wins = [{"setup": s, **(desk.rules.get(s, {}).get("window") or {})} for s in desk.on]
    open_ = [w for w in wins if w.get("open")]
    if open_:
        return cell(True, "open: " + "; ".join(entry_rules.window_text(w) for w in open_))
    return cell(False, "closed: " + "; ".join(entry_rules.window_text(w) for w in wins))


def _nova_buys(sym: str, desk: Desk) -> dict[str, Any]:
    mode = desk.now.mode(desk.venue, sym)
    if mode == STOCK_MODE_BOT:
        return cell(True, "Buy is Nova (Bot)")
    if mode == STOCK_MODE_AUTO_ENTRY:
        return cell(True, "Buy is Nova (Auto-entry)")
    return cell(False, f"Buy is You on {sym}: set its Buy to Nova (Who trades)")


def _line(sym: str) -> dict[str, Any]:
    from bot.eligibility import holds_depth_line

    if holds_depth_line(sym):
        return cell(True, f"Nova holds {sym}'s Level 2 line")
    return cell(None, f"Nova holds no Level 2 line on {sym} now: a trigger without one reads BLIND, unless a line "
                      "opens or is lent before it")


def _trades(desk: Desk) -> dict[str, Any]:
    from bot import entry_rules

    if desk.used is None:
        return cell(None, "the day's Nova entries could not be counted (the backend log has the error)")
    if desk.used >= desk.cap:
        return cell(False, entry_rules.cap_text(desk.used, desk.cap))
    return cell(True, f"{desk.used} of {desk.cap} Nova entr{'y' if desk.cap == 1 else 'ies'} a day used")


def _unread(said: str) -> dict[str, Any]:
    """A ``now`` row Nova could not read: never a yes."""
    return {"cells": {g: cell(None, said) for g in GATE_IDS}, "answer": "no", "reasons": [said]}


def row(desk: Desk | None, sym: str, entry: dict[str, Any], todays: list[dict[str, Any]]) -> dict[str, Any]:
    """``{cells, answer, reasons}`` for one listed stock now (``todays``: the day's triggers so far)."""
    from bot.switch import is_on, why_off

    if desk is None:
        return _unread("the bot's session could not be read (the backend log has the error)")
    try:
        how = "starred" if entry.get("how") == "star" else "listed by the leaders rule"
        at = num(entry.get("at"))
        cells = {
            "bot_on": cell(True, "the bot is on") if is_on(desk.row) else cell(False, str(why_off(desk.row))),
            "strategy_on": (cell(True, "On: " + ", ".join(strategy_rules.name(s) for s in desk.on)) if desk.on
                            else cell(False, "no strategy is On: turn one On")),
            "grade": _grade(sym, desk, _lanes(sym)),
            "setups_a_day": _setups_a_day(sym, desk, todays),
            "bot_window": _window(desk),
            "hot_list": cell(True, f"on today's hot list ({how}" + (f" at {hhmm(at)} ET)" if at is not None else ")")),
            "nova_buys": _nova_buys(sym, desk),
            "level2_line": _line(sym),
            "tape_go": cell(None, "the tape is read at the trigger"),
            "trades_today": _trades(desk),
        }
    except Exception:
        logger.warning("triggers audit: the desk could not be read for %s", sym, exc_info=True)
        return _unread("the desk could not be read (the backend log has the error)")
    reasons = [cells[g]["why"] for g in GATE_IDS if cells[g]["ok"] is False]
    return {"cells": cells, "answer": "no" if reasons else "yes", "reasons": reasons}
