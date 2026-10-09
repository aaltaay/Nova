"""What a go trigger meets before Nova buys it by itself (ADR 042 F, I): one set of rules for
Nova's bot and Auto-entry.

``blockers`` lists every rule that holds a trigger back -- all of them, not the first (the
visibility rule): the venue (Paper, or Sim: its live edge or a loaded replay, ADR 052), Activate, the setup at
effective Strategy, the strategy's bot rules (ADR 044, ``bot.strategy_rules``: the grades it
buys and its setups a stock a day), the tape at go, NOT A TRADE
(``setup_scanner.trade_verdict``), a fresh trigger, the padlock, the kill switch, this venue's
day lock and bot trip, #564's commission hold, the setup's bot window, today's 04:00 reset of
yesterday's bot buys (``hot_list.day_reset_block``; being on the hot list is no rule: ADR 044,
amended 2026-10-06), extended hours, the venue's shared daily cap and the sleeve's size. Then each taker's own:

- the bot: the stock on this venue's bot list with a held depth line, one trade at a time,
  no bot entry still working, the L2 session not held by another brain;
- Auto-entry: the stock not on the bot list (one mode per stock), no entry of it still working.

The strategy that triggers decides the side (ADR 049, #778 step 5): a short trigger meets every rule
above, never a stock you hold long (``against_held``), and its own short check -- its price at the ask
under SSR, borrow, the halt, 09:35-15:50, the margin and its 25% cushion (``short_side``).

``size`` is the sleeve's (``bot.sizing``) against what Nova's automatic entries already hold or
have working on this venue. ``taker`` says who would take a setup's go trigger on a stock
(the proposals carry it). Reads only; the runners send.
"""
from __future__ import annotations

import logging
from typing import Any

from bot.first_pullback.short_side import blocks as short_blocks
from bot.first_pullback.short_side import side_of
from constants_bot import (
    BOT_FP_TRIGGER_MAX_AGE_SEC,
    BOT_LEVEL_STRATEGY,
    BOT_REASON_BRAIN_EXCLUSIVE,
    BOT_REASON_COMMISSIONS_UNKNOWN,
    BOT_REASON_DAY_LOCK,
    BOT_REASON_DAY_TRADE_CAP,
    BOT_REASON_KIND_BLOCKED,
    BOT_REASON_NO_DEPTH_LINE,
    BOT_REASON_OUTSIDE_WINDOW,
    BOT_REASON_PADLOCK_LOCKED,
    BOT_REASON_SYMBOL_BLOCKED,
    BOT_REASON_TRIP_LATCHED,
    BOT_REASON_WORKING_BLOCK,
    BOT_RUNNER_BRAIN_ID,
    BOT_SETUP_FIRST_PULLBACK,
    BOT_SKIP_EXTENDED_HOURS,
    BOT_SKIP_GRADE,
    BOT_SKIP_HELD_OTHER_SIDE,
    BOT_SKIP_NOT_A_TRADE,
    BOT_SKIP_DAY_NOT_RESET,
    BOT_SKIP_NOT_ACTIVE,
    BOT_SKIP_NOT_FIRST,
    BOT_SKIP_ONE_TRADE,
    BOT_SKIP_SETUP_NOT_STRATEGY,
    BOT_SKIP_SIZE,
    BOT_SKIP_STALE,
    BOT_SKIP_TAPE,
    BOT_SKIP_VENUE_CHANGING,
    SIDE_SHORT,
)
from constants_setups import TAPE_VERDICT_GO

logger = logging.getLogger(__name__)
LIVE_STATES = frozenset({"entering", "open", "exiting"})
Blocker = tuple[str, str]


def name(setup_type: str | None) -> str:
    return str(setup_type or BOT_SETUP_FIRST_PULLBACK).replace("_", " ")


def setup_of(event: dict[str, Any]) -> str:
    return str(event.get("setup_type") or BOT_SETUP_FIRST_PULLBACK)


def against_held(sym: str, side: str = "long") -> Blocker | None:
    """Nova never enters against a position you hold (ADR 048: "never buys a stock you are short"): a long
    entry while the venue holds the stock short, a short entry while it holds it long. A position Nova cannot
    read refuses too -- unknown is never flat."""
    from bot.first_pullback.orders import ReadError, held_qty, short_held_qty

    sym = (sym or "").strip().upper()
    try:
        other = held_qty(sym) if side == "short" else short_held_qty(sym)
    except ReadError as exc:
        return (BOT_SKIP_HELD_OTHER_SIDE, f"Nova cannot read your {sym} position ({exc}): no automatic entry")
    if other > 0:
        held = "long" if side == "short" else "short"
        return (BOT_SKIP_HELD_OTHER_SIDE, f"you hold {sym} {held}: Nova enters nothing on {sym} while you do")
    return None


def triggered_at(event: dict[str, Any]) -> float:
    return float((event.get("setup") or {}).get("triggered_at") or event.get("ts") or 0)


# -- the rules every taker shares --------------------------------------------------------
def _level_block(row: dict[str, Any], setup_type: str) -> Blocker | None:
    from bot.setup_levels import LEVEL_NAMES, effective, master, own_levels

    if effective(row).get(setup_type, 0) >= BOT_LEVEL_STRATEGY:
        return None
    top, own = master(row), own_levels(row).get(setup_type, 0)
    if top < BOT_LEVEL_STRATEGY:
        return BOT_SKIP_SETUP_NOT_STRATEGY, (f"the master level is {LEVEL_NAMES[top]}: Nova buys only setups at "
                                             "Strategy")
    return BOT_SKIP_SETUP_NOT_STRATEGY, (f"the {name(setup_type)} is at {LEVEL_NAMES.get(own, own)}: Nova buys "
                                         "only setups at Strategy")


def _desk_blocks(row: dict[str, Any], venue: str | None) -> list[Blocker]:
    """The padlock, the kill switch, this venue's day lock and bot trip; an unreadable gate counts as closed."""
    from bot import activation
    from bot.clock import soft_latched
    from bot.gates import day_lock, lock_text

    out: list[Blocker] = []
    ok, why = activation.padlock()
    if not ok:
        out.append((BOT_REASON_PADLOCK_LOCKED, f"the desk padlock is locked ({why}): unlock it so Nova can place"))
    try:
        import kill_switch

        killed = bool(kill_switch.is_tripped())
    except Exception as exc:
        logger.warning("bot: the kill switch could not be read -- it counts as tripped", exc_info=True)
        killed, exc_text = True, f" (unreadable: {exc})"
    else:
        exc_text = ""
    if killed:
        out.append(("KILL_SWITCH", f"the kill switch is tripped{exc_text}: nothing is sent until you reset it"))
    lock = day_lock(row, venue)
    if lock.get("active"):
        out.append((BOT_REASON_DAY_LOCK, lock_text(lock)))
    if soft_latched(row):
        out.append((BOT_REASON_TRIP_LATCHED, activation.trip_text(row)))
    return out


def _strategy_blocks(event: dict[str, Any], setup_type: str) -> list[Blocker]:
    """The strategy's bot rules (ADR 044): the grades its template in play buys, and its setups a stock a day."""
    from bot import strategy_rules

    rules = strategy_rules.rules(setup_type)
    unread = f" ({rules['error']})" if rules["error"] else ""
    out: list[Blocker] = []
    graded = strategy_rules.grade_block(event.get("grade"), rules["grades"])
    if graded:
        out.append((BOT_SKIP_GRADE, graded + unread))
    number = strategy_rules.number_of(event.get("setup"), setup_type)
    late = strategy_rules.nth_block(number, rules["setups_a_day"], setup_type)
    if late:
        out.append((BOT_SKIP_NOT_FIRST, late + unread))
    return out


def day_reset() -> Blocker | None:
    """The bot buys nothing until today's 04:00 ET reset of yesterday's bot buys has run (see the module)."""
    try:
        import hot_list

        why = hot_list.day_reset_block()
    except Exception:
        logger.warning("bot: whether today's 04:00 reset ran could not be read -- no automatic entry", exc_info=True)
        why = "whether today's 04:00 ET reset of yesterday's bot buys ran could not be read (the backend log has the error)"
    return None if why is None else (BOT_SKIP_DAY_NOT_RESET, why)


def blockers(event: dict[str, Any], row: dict[str, Any], *, now: float,
             venue_now: tuple[str | None, bool, bool] | None = None) -> list[Blocker]:
    """Every rule the bot and Auto-entry share that holds this trigger back (empty: none)."""
    from bot import activation, entry_rules
    from bot.arming import is_desk_active
    from bot.day_pnl import commission_hold
    from bot.sleeve import of as sleeve_of
    from setup_scanner.trade_verdict import of_event

    from stock_mode.leave import leaving, leaving_text

    out: list[Blocker] = []
    venue, edge, readable = venue_now or activation.venue_state()
    blocked = activation.venue_block(venue, edge, readable)
    if blocked is not None:
        out.append(blocked)
    move = leaving()
    if move is not None:
        out.append((BOT_SKIP_VENUE_CHANGING, leaving_text(move)))
    if not is_desk_active(row):
        out.append((BOT_SKIP_NOT_ACTIVE, "the bot is not active: turn the Bot switch on (Bots page)"))
    setup_type = setup_of(event)
    level = _level_block(row, setup_type)
    if level is not None:
        out.append(level)
    out.extend(_strategy_blocks(event, setup_type))
    tape = event.get("tape") or {}
    verdict = tape.get("verdict")
    if verdict != TAPE_VERDICT_GO:
        why = next(iter(tape.get("reasons") or ()), None)
        said = f" ({why})" if why else ""
        out.append((BOT_SKIP_TAPE, f"the tape read {verdict or 'nothing'} at the trigger{said} -- Nova enters on go"))
    judged = of_event(event)
    if not judged["ok"]:
        out.append((BOT_SKIP_NOT_A_TRADE, "not a trade: " + "; ".join(judged["reasons"])))
    held = against_held(str(event.get("symbol") or ""), side_of(event))
    if held is not None:
        out.append(held)
    age = now - triggered_at(event)
    if age > BOT_FP_TRIGGER_MAX_AGE_SEC:
        out.append((BOT_SKIP_STALE, f"the trigger is {age:.0f}s old (Nova enters on one at most "
                                    f"{BOT_FP_TRIGGER_MAX_AGE_SEC:g}s old)"))
    out.extend(_desk_blocks(row, venue))
    hold = commission_hold(venue)
    if hold is not None:
        out.append((BOT_REASON_COMMISSIONS_UNKNOWN, f"the session's commissions are unreadable ({hold.get('error')}): "
                                                    "no new automatic entry until they read again"))
    clock = entry_rules.venue_now()
    win = entry_rules.window(setup_type, clock)
    if not win.get("open"):
        out.append((BOT_REASON_OUTSIDE_WINDOW, f"outside the bot's window: {entry_rules.window_text(win)} "
                                               f"(venue clock {clock.strftime('%H:%M')})"))
    reset = day_reset()
    if reset is not None:
        out.append(reset)
    caps = sleeve_of(row)
    late = entry_rules.extended_hours_block(caps)
    if late is not None:
        out.append((BOT_SKIP_EXTENDED_HOURS, late))
    try:
        daily = entry_rules.today(venue, clock, cap=int(caps["entries_per_day"]))
    except Exception as exc:
        logger.warning("bot: the day's entries could not be counted -- no automatic entry", exc_info=True)
        out.append((BOT_REASON_DAY_TRADE_CAP, f"the day's entries could not be counted ({exc}): no automatic entry"))
    else:
        if daily["count"] >= daily["cap"]:
            out.append((BOT_REASON_DAY_TRADE_CAP, entry_rules.cap_text(daily["count"], daily["cap"])))
    return out


# -- size ----------------------------------------------------------------------------------
def exposure(row: dict[str, Any], venue: str | None) -> float:
    """Dollars Nova's automatic entries hold or have working on this venue, long or short: the bot's and
    Auto-entry's."""
    from bot.risk import open_plus_working_usd

    from stock_mode import store

    total = open_plus_working_usd(row)
    for t in store.trades():
        if t.get("venue") == venue and t.get("kind") == "auto_entry" and t.get("state") in ("entering", "holding"):
            total += float(t.get("qty") or 0) * float(t.get("fill_price") or t.get("entry") or 0)
    return total


def size(event: dict[str, Any], row: dict[str, Any], venue: str | None) -> dict[str, Any]:
    """The sleeve's size for this trigger (``bot.sizing``); an unreadable budget sizes nothing, and says so.
    A short's carries its price and its short check (``short_side.size``)."""
    from bot.first_pullback import short_side
    from bot.sizing import size as sized
    from bot.sleeve import of as sleeve_of

    caps = sleeve_of(row)
    setup = event.get("setup") or {}
    short = side_of(event) == SIDE_SHORT
    try:
        left = float(caps["bp_budget_usd"]) - exposure(row, venue)
    except Exception as exc:
        logger.warning("bot: what Nova's automatic entries hold could not be read for the budget", exc_info=True)
        verb = "short" if short else "buy"
        return {"qty": 0, "by_risk": None, "capped_by": None, "side": side_of(event),
                "text": f"what Nova's automatic entries hold could not be read ({exc}): Nova does not {verb}"}
    if short:
        return short_side.size(event, caps, left, venue)
    return {**sized(caps["risk_usd"], setup.get("entry"), setup.get("stop"), caps["max_shares"], left),
            "side": "long"}


def size_blocks(sized: dict[str, Any]) -> list[Blocker]:
    """What the size says: under one share (or a short with no price), then the short check's failures."""
    out: list[Blocker] = []
    if sized["qty"] < 1:
        out.append((str(sized.get("price_code") or BOT_SKIP_SIZE), str(sized.get("text"))))
    return out + short_blocks(sized)


# -- the bot ---------------------------------------------------------------------------------
def for_bot(event: dict[str, Any], row: dict[str, Any], *, now: float) -> tuple[list[Blocker], dict[str, Any] | None]:
    """``(blockers, size)`` for Nova's bot on this trigger."""
    from bot import activation
    from bot.eligibility import holds_depth_line, no_line_text, normalize_symbols
    from bot.risk import is_working_entry, working_bot_orders

    venue_now = activation.venue_state()
    out = blockers(event, row, now=now, venue_now=venue_now)
    sym = str(event.get("symbol") or "").upper()
    if sym not in normalize_symbols(row.get("symbol_allowlist")):
        out.append((BOT_REASON_SYMBOL_BLOCKED, f"{sym} is not set to Bot on this venue"))
    elif not holds_depth_line(sym):
        out.append((BOT_REASON_NO_DEPTH_LINE, no_line_text(sym)))
    current = row.get("trade")
    if isinstance(current, dict) and current.get("state") in LIVE_STATES:
        out.append((BOT_SKIP_ONE_TRADE, f"already in {current.get('symbol')} -- one trade at a time"))
    if any(is_working_entry(w) for w in working_bot_orders(row)):
        out.append((BOT_REASON_WORKING_BLOCK, "a bot entry is still working"))
    held = (row.get("brain_session_id") or "").strip()
    if held and held != BOT_RUNNER_BRAIN_ID:
        out.append((BOT_REASON_BRAIN_EXCLUSIVE, f"another bot ({held}) holds the Strategy session"))
    sized = size(event, row, venue_now[0])
    return out + size_blocks(sized), sized


def trade(event: dict[str, Any], row: dict[str, Any], *, qty: int, size_text: str | None = None,
          sized: dict[str, Any] | None = None) -> dict[str, Any]:
    """The bot's trade for an admitted trigger (``bot-session.json``'s ``trade``). A short's entry is the
    price its size was read at (``short_side.price``: the ask under SSR), and its risk runs up to its buy stop."""
    from bot.entry_rules import venue_day
    from bot.gates import current_venue
    from bot.replay_desk import desk as replay_desk
    from bot.sleeve import of as sleeve_of

    setup = event["setup"]
    side = side_of(event)
    entry, stop = float(setup["entry"]), float(setup["stop"])
    risk = float(setup["risk"])
    if side == SIDE_SHORT and sized and sized.get("limit") is not None:
        entry = float(sized["limit"])
        risk = round(stop - entry, 4)
    return {
        "setup_id": str(event.get("setup_id") or ""), "setup_type": setup_of(event), "side": side,
        "symbol": str(event.get("symbol") or "").upper(), "venue": current_venue(),
        "venue_day": venue_day(), "template_id": event.get("template_id"),
        "template_rev": event.get("template_rev"), "template_name": event.get("template_name"),
        "state": "entering", "qty": float(qty), "size_text": size_text, "trigger": setup.get("trigger"),
        "trigger_price": setup.get("trigger_price"), "triggered_at": triggered_at(event),
        "entry_planned": entry, "entry_scanned": float(setup["entry"]), "stop": stop,
        "target1": float(setup["target1"]), "risk": risk,
        "priced_at_ask": bool((sized or {}).get("priced_at_ask")), "ssr": (sized or {}).get("ssr"),
        "entry_order_id": None, "target_order_id": None, "stop_order_id": None,
        "stop_leg_at": None, "entry_sent_ts": None, "entry_ttl_sec": int(sleeve_of(row)["working_ttl_sec"]),
        "entry_cancel_ts": None, "entry_fill_price": None, "entry_filled_ts": None,
        "exit_order_id": None, "exit_attempt": 0, "exit_sent_ts": None,
        "exit_limit": None, "exit_protective": False, "exit_why": None, "exit_price": None,
        "exit_reason": None, "closed_ts": None, "slippage": None, "r": None, "note": None,
        # The Sim replay it was made on (ADR 052): it is managed only while the desk shows that replay.
        "replay_key": (replay_desk() or {}).get("key"),
    }


# -- Auto-entry ------------------------------------------------------------------------------
def for_auto_entry(event: dict[str, Any], row: dict[str, Any], *, now: float,
                   working: bool) -> tuple[list[Blocker], dict[str, Any] | None]:
    """``(blockers, size)`` for Auto-entry on this trigger; ``working`` is an entry of the stock still working."""
    from bot import activation
    from bot.eligibility import normalize_symbols

    venue_now = activation.venue_state()
    out = blockers(event, row, now=now, venue_now=venue_now)
    sym = str(event.get("symbol") or "").upper()
    if sym in normalize_symbols(row.get("symbol_allowlist")):
        out.append((BOT_REASON_KIND_BLOCKED, f"{sym} is set to Bot: the bot trades it, not Auto-entry"))
    if working:
        out.append((BOT_REASON_WORKING_BLOCK, "an entry Nova sent is still working"))
    sized = size(event, row, venue_now[0])
    return out + size_blocks(sized), sized


# -- who takes a setup's go trigger -------------------------------------------------------------
def taker(sym: str, setup_type: str) -> str | None:
    """``"bot"`` / ``"auto_entry"`` when Nova would take this setup's go trigger on ``sym`` by itself, else None."""
    from bot import activation
    from bot.arming import is_desk_active
    from bot.eligibility import normalize_symbols
    from bot.persist import load_session
    from bot.setup_levels import effective

    row = load_session()
    if not is_desk_active(row) or effective(row).get(setup_type, 0) < BOT_LEVEL_STRATEGY:
        return None
    if activation.venue_block(*activation.venue_state()) is not None:
        return None
    sym = (sym or "").strip().upper()
    if day_reset() is not None:
        return None                  # today's 04:00 reset of yesterday's bot buys has not run
    if sym in normalize_symbols(row.get("symbol_allowlist")):
        return "bot"
    from stock_mode import model, store

    sw = store.switch(sym)
    if sw and model.mode_of(sw.get("buy"), sw.get("sell")) == "auto_entry":
        return "auto_entry"
    return None


def text(found: list[Blocker]) -> str:
    return "; ".join(why for _code, why in found)
