"""The squares' ``now`` row (ADR 044): would the bot trade this stock if its setup triggered this minute?

The same gates as a trigger (``bot.trigger_cells``), read from the desk as it stands -- the desk
venue's dial, the strategies' rules today, the live setup board, the Who trades switch, the depth
lines held and the day's Nova entries:

- ``bot_on``: the Bot switch reads ON (``bot.switch``), else why not;
- ``strategy_on``: a strategy is On;
- ``grade``: ``null`` unless a setup of a strategy that is On is armed or near on the stock -- then its
  grade against the strategy's ``bot_grades`` and NOT A TRADE's checks (grade C, too thin);
- ``setups_a_day``: an On strategy may still buy its next setup on the stock today;
- ``bot_window``: an On strategy's bot window is open now;
- ``nova_buys`` ("Bot buys"): the stock's Buy is the bot's on the desk's venue (Auto-entry or Bot), and
  today's 04:00 reset of yesterday's bot buys has run (``hot_list.day_reset_block``);
- ``level2_line``: Nova holds the stock's Level 2 line now; ``null`` when it does not -- a line may
  still open, or be lent, before the trigger;
- ``tape_go``: ``null`` -- the tape is read at the trigger;
- ``trades_today``: the venue's daily cap has room;
- ``not_against`` and, with a short strategy On, the short block (ADR 049, #778 step 5): the position you
  hold against the sides the On strategies enter, and the short check's facts now (``bot.trigger_short``).

``answer`` is ``yes`` only when no gate is false; ``reasons`` are the false gates' words. A square of the short
block stops only the short side: while a long strategy that is On could still trade the stock (its window open,
its next setup allowed, no short held), it stays red and leaves the answer alone. Owner: this module (no state;
it reads, never writes).
"""
from __future__ import annotations

import logging
from typing import Any

from bot import strategy_rules, trigger_short
from bot.trigger_cells import ALL_GATE_IDS, GATE_IDS, cell, hhmm
from constants_bot import BOT_GRADES_A, BOT_LEVEL_STRATEGY, SIDE_LONG, SIDE_SHORT, setup_side
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


def _next_setup(sym: str, desk: Desk, todays: list[dict[str, Any]],
                setup: str) -> tuple[int, list[dict[str, Any]], str | None]:
    """``(its number today, the day's triggers of it, what stops it)`` for ``setup``'s next trigger on ``sym``."""
    done = [t for t in todays if t["symbol"] == sym and t["setup_type"] == setup]
    number = max((t["nth"] for t in done), default=0) + 1
    rule = desk.rules.get(setup, {}).get("setups_a_day", 1)
    return number, done, strategy_rules.nth_block(number, rule, setup)


def _setups_a_day(sym: str, desk: Desk, todays: list[dict[str, Any]]) -> dict[str, Any]:
    if not desk.on:
        return cell(None, "no strategy is On")
    blocks = []
    for setup in desk.on:
        number, done, block = _next_setup(sym, desk, todays, setup)
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
    from bot.first_pullback.admit import day_reset

    mode = desk.now.mode(desk.venue, sym)
    if mode not in (STOCK_MODE_BOT, STOCK_MODE_AUTO_ENTRY):
        return cell(False, f"Entry is You on {sym}: set its Entry to Bot (Who trades)")
    reset = day_reset()
    if reset is not None:
        return cell(False, reset[1])
    return cell(True, "Entry: Bot (Bot)" if mode == STOCK_MODE_BOT else "Entry: Bot (Auto-entry)")


def _line(sym: str) -> dict[str, Any]:
    from bot.eligibility import holds_depth_line

    if holds_depth_line(sym):
        return cell(True, f"Nova holds {sym}'s Level 2 line")
    try:
        from line_lending import lines, setting

        free = lines.free_lines()
        lending, unread = setting.is_on()
    except Exception:
        logger.warning("triggers audit: who could give %s a Level 2 line is unknown", sym, exc_info=True)
        return cell(None, f"Nova holds no Level 2 line on {sym} now, and whether one would open could not be read "
                          "(the backend log has the error)")
    if free:
        return cell(None, f"Nova holds no Level 2 line on {sym} now; {free} of IBKR's lines are free for a setup "
                          "that comes near")
    if lending:
        return cell(None, f"Nova holds no Level 2 line on {sym} now and every line is taken; a Trader tab you are not "
                          "looking at lends its lines when a setup comes near")
    return cell(False, f"Nova holds no Level 2 line on {sym}, every line is taken and "
                       f"{unread or 'lending is off'}: a trigger now would read BLIND")


def _trades(desk: Desk) -> dict[str, Any]:
    from bot import entry_rules

    if desk.used is None:
        return cell(None, "the day's Nova entries could not be counted (the backend log has the error)")
    if desk.used >= desk.cap:
        return cell(False, entry_rules.cap_text(desk.used, desk.cap))
    return cell(True, f"{desk.used} of {desk.cap} Nova entr{'y' if desk.cap == 1 else 'ies'} a day used")


def _short_block(sym: str, desk: Desk) -> dict[str, Any]:
    """The short check's squares now, when a short strategy is On; nothing otherwise (the block stays empty)."""
    shorts = [s for s in desk.on if setup_side(s) == SIDE_SHORT]
    if not shorts:
        return {}
    lanes = _lanes(sym) or []
    armed = [lane for lane in lanes if lane.get("setup_type") in shorts and lane.get("state") in _ARMED]
    return trigger_short.now_cells(sym, desk.venue, armed, desk.row)


def _long_can(sym: str, desk: Desk, todays: list[dict[str, Any]],
              against: dict[str, tuple[str, str] | None]) -> bool:
    """A long strategy that is On could still take a trigger on ``sym`` now: its own bot window is open, its next
    setup today is allowed, and you hold none of the stock short. Then a square of the short block stops only the
    short side: it stays red, and never makes the answer no (PR #790 review)."""
    if against.get(SIDE_LONG) is not None:
        return False
    for setup in desk.on:
        if setup_side(setup) == SIDE_SHORT or not (desk.rules.get(setup, {}).get("window") or {}).get("open"):
            continue
        if _next_setup(sym, desk, todays, setup)[2] is None:
            return True
    return False


def _unread(said: str) -> dict[str, Any]:
    """A ``now`` row Nova could not read: never a yes."""
    return {"cells": {g: cell(None, said) for g in GATE_IDS}, "answer": "no", "reasons": [said]}


def row(desk: Desk | None, sym: str, todays: list[dict[str, Any]]) -> dict[str, Any]:
    """``{cells, answer, reasons}`` for one stock now (``todays``: the day's triggers so far)."""
    from bot.switch import is_on, why_off

    if desk is None:
        return _unread("the bot's session could not be read (the backend log has the error)")
    try:
        sides = {setup_side(s) for s in desk.on}
        against = trigger_short.against_now(sym, sides)
        cells = {
            "bot_on": cell(True, "the bot is on") if is_on(desk.row) else cell(False, str(why_off(desk.row))),
            "strategy_on": (cell(True, "On: " + ", ".join(strategy_rules.name(s) for s in desk.on)) if desk.on
                            else cell(False, "no strategy is On: turn one On")),
            "grade": _grade(sym, desk, _lanes(sym)),
            "setups_a_day": _setups_a_day(sym, desk, todays),
            "bot_window": _window(desk),
            "nova_buys": _nova_buys(sym, desk),
            "level2_line": _line(sym),
            "tape_go": cell(None, "the tape is read at the trigger"),
            "trades_today": _trades(desk),
            "not_against": trigger_short.not_against_now(sym, sides, against),
            **_short_block(sym, desk),
        }
        long_can = _long_can(sym, desk, todays, against)
    except Exception:
        logger.warning("triggers audit: the desk could not be read for %s", sym, exc_info=True)
        return _unread("the desk could not be read (the backend log has the error)")
    short_ids = set(trigger_short.SHORT_GATE_IDS)
    reasons = [cells[g]["why"] for g in ALL_GATE_IDS if cells.get(g, {}).get("ok") is False
               and not (long_can and g in short_ids)]
    return {"cells": cells, "answer": "no" if reasons else "yes", "reasons": reasons}
