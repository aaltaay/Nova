"""One stock's switch as the desk reads it (ADR 037, ADR 042 F): the mode, the locks, every note that
keeps Nova from acting, the size Nova would send, the approval, the trade and the last event.

Reads memory, the bot session, the scanner's lanes and today's hot list only: no network, no order read.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from constants_stock_mode import (
    STOCK_MODE_APPROVE,
    STOCK_MODE_AUTO_ENTRY,
    STOCK_MODE_BOT,
    STOCK_MODE_EXIT,
    STOCK_MODE_NOTE_NOT_FOLLOWED,
    STOCK_MODE_SCHEMA_VERSION,
    STOCK_MODE_SIDE_NOVA,
    STOCK_MODE_SIDE_YOU,
    STOCK_MODE_SIGNAL,
    STOCK_MODE_TRADE_CLOSED,
    STOCK_MODE_TRADE_ENTERING,
    STOCK_MODE_TRADE_HANDED,
    STOCK_MODE_TRADE_HOLDING,
    STOCK_MODE_TRADE_MISSED,
)
from stock_mode import gates, model, store

logger = logging.getLogger(__name__)

# The bot's trade states (ADR 030) as the view's.
_BOT_STATES = {"entering": STOCK_MODE_TRADE_ENTERING, "open": STOCK_MODE_TRADE_HOLDING,
               "exiting": STOCK_MODE_TRADE_HOLDING, "closed": STOCK_MODE_TRADE_CLOSED,
               "missed": STOCK_MODE_TRADE_MISSED, "handed": STOCK_MODE_TRADE_HANDED}
_DESK_NOTE_IDS = {"DESK_DISARMED": "padlock", "KILL_SWITCH": "kill", "BOT_DAY_LOCK": "day_lock", "BOT_TRIP": "bot_trip"}
_NOVA_BUYS = (STOCK_MODE_BOT, STOCK_MODE_AUTO_ENTRY)
_BOT_UNREADABLE = "the bot session could not be read"


def _bot_row() -> dict[str, Any] | None:
    """The bot session, or None when it cannot be read: unknown, never an empty session."""
    from bot.persist import load_session

    try:
        return load_session()
    except Exception:
        logger.warning("stock mode: the bot session could not be read", exc_info=True)
        return None


def _bot_part(sym: str, row: dict[str, Any], plan_setup: str | None) -> dict[str, Any]:
    from bot.arming import is_desk_active
    from bot.eligibility import normalize_symbols
    from bot.first_pullback import runner as bot_runner
    from bot.setup_levels import effective

    on_list = sym in set(normalize_symbols(row.get("symbol_allowlist")))
    status = bot_runner.status(row)
    eff = effective(row)
    return {"on_list": on_list, "playing": bool(status.get("playing")), "reason": status.get("reason"),
            "setup_at_strategy": (eff.get(plan_setup, 0) >= 2) if plan_setup else None,
            "active": bool(is_desk_active(row))}


def _bot_trade(sym: str, row: dict[str, Any]) -> dict[str, Any] | None:
    t = row.get("trade")
    if not isinstance(t, dict) or str(t.get("symbol") or "").upper() != sym:
        return None
    exits = STOCK_MODE_SIDE_YOU if t.get("state") == "handed" else STOCK_MODE_SIDE_NOVA
    return {
        "kind": STOCK_MODE_BOT, "state": _BOT_STATES.get(str(t.get("state")), STOCK_MODE_TRADE_CLOSED),
        "venue": t.get("venue"), "venue_day": t.get("venue_day"), "setup_id": t.get("setup_id"),
        "setup_type": t.get("setup_type"), "qty": t.get("qty"), "entry": t.get("entry_planned"),
        "stop": t.get("stop"), "target": t.get("target1"), "entry_order_id": t.get("entry_order_id"),
        "target_order_id": t.get("target_order_id"), "stop_order_id": t.get("stop_order_id"),
        "fill_price": t.get("entry_fill_price"), "filled_at": t.get("entry_filled_ts"),
        "exit_price": t.get("exit_price"), "exit_reason": t.get("exit_reason"), "exits": exits,
        "sent_at": t.get("entry_sent_ts"), "closed_at": t.get("closed_ts"), "note": t.get("note"),
        "exiting": t.get("state") == "exiting", "ttl_sec": t.get("entry_ttl_sec"),
    }


def _public_trade(t: dict[str, Any] | None) -> dict[str, Any] | None:
    if not t:
        return None
    keys = ("kind", "state", "venue", "venue_day", "setup_id", "setup_type", "qty", "entry", "stop", "target",
            "entry_order_id", "target_order_id", "stop_order_id", "fill_price", "filled_at", "exit_price",
            "exit_reason", "exits", "sent_at", "closed_at", "note", "ttl_sec", "trail", "raised")
    out = {k: t.get(k) for k in keys}
    out["exiting"] = bool(t.get("exiting"))
    return out


def _today(t: dict[str, Any] | None, day: str) -> dict[str, Any] | None:
    """A trade from an earlier day is history once it is done: the view shows today's, or a live one."""
    if t is None:
        return None
    live = t.get("state") in (STOCK_MODE_TRADE_ENTERING, STOCK_MODE_TRADE_HOLDING)
    return t if live or t.get("venue_day") in (None, day) else None


def _latest(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, Any] | None:
    if a is None or b is None:
        return a or b
    return a if float(a.get("sent_at") or 0) >= float(b.get("sent_at") or 0) else b


# -- the plan Nova would act on --------------------------------------------------------------
_UNREAD = {"unread": True}


def _plan_lane(sym: str, now: float) -> dict[str, Any] | None:
    """The scanner lane the stock's plan follows (``stock_read.plan.choose``), None without one, and
    ``_UNREAD`` when the scanner cannot be read (unknown, never "no plan")."""
    from stock_mode.runner import lanes_of
    from stock_read.plan import choose

    lanes = lanes_of(sym)
    if lanes is None:
        return _UNREAD
    return choose(lanes, now) if lanes else None


def _levels(lane: dict[str, Any] | None) -> dict[str, Any] | None:
    if not lane:
        return None
    lv = lane.get("setup") or lane.get("forming")
    return lv if isinstance(lv, dict) and lv.get("entry") is not None and lv.get("stop") is not None else None


def spread_of(sym: str) -> float | None:
    """The spread on Nova's book for the stock now (None when unknown)."""
    try:
        from bot.quotes import top_of_book

        bid, ask = top_of_book(sym)
    except Exception:
        logger.warning("stock mode: %s's book could not be read for the spread", sym, exc_info=True)
        return None
    return round(float(ask) - float(bid), 4) if bid and ask else None


def _size(mode: str, row: dict[str, Any], lane: dict[str, Any] | None, venue: str | None) -> dict[str, Any] | None:
    """What Nova would send for the stock's current plan: the sleeve's size for Bot and Auto-entry, risk over
    risk per share (no sleeve caps) for Approve; None in Signal only or with no plan."""
    from bot.first_pullback.admit import exposure
    from bot.sizing import size
    from bot.sleeve import of

    lv = _levels(lane)
    if mode == STOCK_MODE_SIGNAL or lv is None:
        return None
    caps = of(row)
    if mode == STOCK_MODE_APPROVE:
        out = size(caps["risk_usd"], lv.get("entry"), lv.get("stop"), None, None)
        return {**out, "text": f"{out['text']} -- you approve it; the sleeve's caps do not apply"}
    try:
        left = float(caps["bp_budget_usd"]) - exposure(row, venue)
    except Exception:
        logger.warning("stock mode: Nova's open trades could not be read for the budget", exc_info=True)
        return {"qty": 0, "by_risk": None, "capped_by": None,
                "text": "what Nova's automatic buys hold could not be read (the backend log has the error): Nova does not buy"}
    return size(caps["risk_usd"], lv.get("entry"), lv.get("stop"), caps["max_shares"], left)


# -- the notes -----------------------------------------------------------------------------
def _note(nid: str, text: str, tone: str = "warn") -> dict[str, Any]:
    return {"id": nid, "tone": tone, "text": text}


def _sentence(text: str) -> str:
    """First letter up, a full stop -- never ``str.capitalize``, which lowers "Nova"."""
    return (text[:1].upper() + text[1:]).rstrip(".") + "." if text else text


def _notes(sym: str, mode: str, venue: str | None, replay: bool, row: dict[str, Any] | None,
           lane: dict[str, Any] | None, daily: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Every condition that keeps Nova from acting on this stock -- all of them, not the first."""
    from bot import entry_rules
    from bot.eligibility import holds_depth_line
    from bot.setup_levels import LEVEL_NAMES, at_strategy, effective, own_levels
    from bot.sleeve import of

    out: list[dict[str, Any]] = []
    if mode == STOCK_MODE_SIGNAL:
        return out
    blocked = gates.venue_block(venue, replay)
    if blocked is not None:
        out.append(_note("replay" if blocked[0] == "STOCK_MODE_REPLAY" else "live", blocked[1]))
    for code, why in gates.desk_blocks():
        out.append(_note(_DESK_NOTE_IDS.get(code, code.lower()), why))
    if gates.followed(sym) is False:
        out.append(_note("not_followed", STOCK_MODE_NOTE_NOT_FOLLOWED.format(sym=sym)))
    if lane is not None:
        judged = model.lane_verdict(lane, spread_of(sym))
        if not judged["ok"]:
            out.append(_note("not_a_trade", "Not a trade: " + "; ".join(judged["reasons"])))
    if row is None or mode not in _NOVA_BUYS:
        return out
    from bot.arming import is_desk_active

    if not is_desk_active(row):
        out.append(_note("not_active", "The bot is not active: Nova buys nothing by itself until you turn the Bot "
                                       "switch on (Bots page)."))
    from bot.first_pullback.admit import listed

    on_list, unread = listed(sym)
    if not on_list:                       # ADR 044: Nova buys only the stocks on today's hot list
        out.append(_note("not_listed", _sentence(f"{unread}: Nova buys only listed stocks" if unread else
                                                 f"{sym} is not on today's hot list: Nova buys only listed stocks")))
    setup = (lane or {}).get("setup_type")
    if setup and effective(row).get(setup, 0) < 2:
        own = own_levels(row).get(setup, 0)
        out.append(_note("not_strategy", f"The {str(setup).replace('_', ' ')} is at {LEVEL_NAMES.get(own, own)}"
                                         + (f" (the master is {LEVEL_NAMES.get(int(row.get('level') or 0))})"
                                            if own >= 2 else "") + ": Nova buys only setups at Strategy."))
    elif not setup and not at_strategy(row):
        out.append(_note("not_strategy", "No setup is at Strategy: Nova buys only setups at Strategy."))
    if setup:
        win = entry_rules.window(setup)
        if not win.get("open"):
            out.append(_note("window", f"Outside the bot's window: {entry_rules.window_text(win)}."))
    if daily is not None and daily.get("count") is not None and daily["count"] >= daily["cap"]:
        out.append(_note("daily_cap", _sentence(entry_rules.cap_text(daily["count"], daily["cap"]))))
    elif daily is not None and daily.get("count") is None:
        out.append(_note("daily_cap", _sentence(f"the day's Nova entries could not be counted "
                                                f"({daily.get('error') or 'unknown'}): Nova sends no automatic entry")))
    late = entry_rules.extended_hours_block(of(row))
    if late is not None:
        out.append(_note("extended_hours", _sentence(late)))
    if not holds_depth_line(sym):
        out.append(_note("no_depth", f"Nova holds no Level 2 line for {sym}: the tape cannot read go -- open its "
                                     "Level 2 or record it."))
    return out


def _sim_waits(sym: str, venue: str | None, replay: bool, row: dict[str, Any] | None) -> list[dict[str, Any]]:
    """A live Nova trade on Sim waits while the desk is not on Sim at its live edge."""
    on_sim = venue == "sim" and not replay
    if on_sim:
        return []
    live = [t for t in store.trades() if t.get("venue") == "sim" and t.get("symbol") == sym
            and t.get("state") in (STOCK_MODE_TRADE_ENTERING, STOCK_MODE_TRADE_HOLDING)]
    bot = (row or {}).get("trade")
    if isinstance(bot, dict) and bot.get("venue") == "sim" and str(bot.get("symbol") or "").upper() == sym \
            and bot.get("state") in ("entering", "open", "exiting"):
        live.append(bot)
    if not live:
        return []
    return [_note("sim_waits", f"Nova's {sym} trade on Sim waits: Sim fills only at its live edge -- it moves again "
                               "when the desk is back on Sim following the wall clock.", "info")]


def build(symbol: str, *, now: float | None = None) -> dict[str, Any]:
    from bot import entry_rules
    from bot.sleeve import of
    from stock_mode.runner import venue_day

    now = time.time() if now is None else now
    sym = model.symbol(symbol)
    venue, replay = gates.venue_state()
    store.sync_venue(venue)
    loaded = _bot_row()
    row = loaded or {}
    lane = _plan_lane(sym, now)
    unread = lane is _UNREAD
    if unread:
        lane = None
    bot = _bot_part(sym, row, (lane or {}).get("setup_type")) if loaded is not None else \
        {"on_list": False, "playing": False, "reason": _BOT_UNREADABLE, "setup_at_strategy": None, "active": False}
    sw = store.switch(sym)
    live_lock = model.locks(venue, replay)["buy"] is not None and not replay
    if live_lock:
        buy, sell = STOCK_MODE_SIDE_YOU, STOCK_MODE_SIDE_YOU      # on Live a stock is never Nova's
    elif bot["on_list"]:
        buy, sell = STOCK_MODE_SIDE_NOVA, STOCK_MODE_SIDE_NOVA
    elif sw:
        buy, sell = sw["buy"], sw["sell"]
    else:
        buy, sell = STOCK_MODE_SIDE_YOU, STOCK_MODE_SIDE_YOU
    mode = model.mode_of(buy, sell)
    day = venue_day(now)
    exit_held = store.trade(venue, sym)
    if exit_held and exit_held.get("kind") == STOCK_MODE_EXIT and exit_held.get("state") == STOCK_MODE_TRADE_HOLDING             and exit_held.get("exits") == STOCK_MODE_SIDE_NOVA:
        sell = STOCK_MODE_SIDE_NOVA          # Nova holds the exit of a stock you bought (the mode stays yours)
    caps = of(row) if loaded is not None else None
    try:
        daily = entry_rules.today(venue, cap=int(caps["entries_per_day"])) if caps else None
    except Exception:
        logger.warning("stock mode: the day's Nova entries could not be counted", exc_info=True)
        daily = {"count": None, "cap": (caps or {}).get("entries_per_day"),
                 "error": "the day's entries could not be counted (the backend log has the error)", "entries": []}
    bot_trade = _bot_trade(sym, row)
    if bot_trade and bot_trade.get("venue") not in (None, venue):
        bot_trade = None                    # the bot's trade on another venue is not this desk's
    trade = _latest(_today(store.trade(venue, sym), day), _today(bot_trade, day))
    notes = ([_note("bot_unreadable", f"The bot session could not be read, so whether Nova trades {sym} is "
                                      "unknown.")] if loaded is None else [])
    if store.load_error():
        notes.append(_note("trades_unreadable", str(store.load_error())))
    if unread and mode != "signal":
        notes.append(_note("scanner_unreadable", f"The setup scanner's lanes for {sym} could not be read: Nova cannot "
                                                 "say which setup it would act on, or what size."))
    notes += _notes(sym, mode, venue, replay, loaded, lane, daily) + _sim_waits(sym, venue, replay, loaded)
    from hot_list.stock_tie import notes as hot_list_notes

    notes += hot_list_notes(sym, mode, venue, replay)   # ADR 044: not listed, unreadable, a default locked here
    mine = [e for e in (daily or {}).get("entries") or [] if e.get("symbol") == sym and e.get("outcome") != "missed"]
    return {
        "schema_version": STOCK_MODE_SCHEMA_VERSION,
        "symbol": sym,
        "generated_at": now,
        "venue": venue,
        "mode": mode,
        "buy": buy,
        "sell": sell,
        # The venue sleeve's risk per trade (ADR 042 E): read-only here, set on the Bots page / plan card.
        "risk_usd": (caps or {}).get("risk_usd"),
        "set_at": (sw or {}).get("set_at"),
        "locks": model.locks(venue, replay),
        "notes": notes,
        "size": _size(mode, row, lane, venue) if loaded is not None else None,
        "approval": store.approval(sym),
        "trade": _public_trade(trade),
        "entries_today": {"count": (daily or {}).get("count"), "cap": (daily or {}).get("cap")},
        "nova_entries_today": len(mine),            # LEGACY (one release): Nova's entries of this stock today
        "last_event": store.event(sym),
        "bot": bot if (loaded is None or bot["on_list"] or mode == STOCK_MODE_BOT
                       or trade and trade.get("kind") == STOCK_MODE_BOT) else None,
    }


def all_stocks(*, now: float | None = None) -> list[dict[str, Any]]:
    """Every stock that is not at Signal only: the switches in memory and this venue's bot list."""
    from bot.eligibility import normalize_symbols

    now = time.time() if now is None else now
    syms = set(store.switches()) | set(normalize_symbols((_bot_row() or {}).get("symbol_allowlist")))
    return [build(s, now=now) for s in sorted(syms)]
