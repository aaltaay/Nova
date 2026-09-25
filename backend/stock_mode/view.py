"""One stock's switch as the desk reads it (ADR 037): the mode, the locks, the notes, the approval, the
trade and the last event. Reads memory and the bot session only: no network, no order read."""
from __future__ import annotations

import logging
import time
from typing import Any

from constants_stock_mode import (
    STOCK_MODE_AUTO_ENTRY,
    STOCK_MODE_BOT,
    STOCK_MODE_NOTE_ENTRY_USED,
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


def _bot_row() -> dict[str, Any]:
    from bot.persist import load_session

    try:
        return load_session()
    except Exception:
        logger.warning("stock mode: the bot session could not be read", exc_info=True)
        return {}


def _bot_part(sym: str, row: dict[str, Any]) -> dict[str, Any]:
    from bot.eligibility import normalize_symbols
    from bot.first_pullback import runner as bot_runner

    on_list = sym in set(normalize_symbols(row.get("symbol_allowlist")))
    status = bot_runner.status(row) if row else {"playing": False, "reason": "the bot session could not be read"}
    return {"on_list": on_list, "playing": bool(status.get("playing")), "reason": status.get("reason"),
            "setup": bot_runner.chosen(row) if row else None}


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
        "target_order_id": t.get("target_order_id"), "stop_order_id": None, "fill_price": t.get("entry_fill_price"),
        "filled_at": t.get("entry_filled_ts"), "exit_price": t.get("exit_price"), "exit_reason": t.get("exit_reason"),
        "exits": exits, "sent_at": t.get("entry_sent_ts"), "closed_at": t.get("closed_ts"), "note": t.get("note"),
        "exiting": t.get("state") == "exiting",
    }


def _public_trade(t: dict[str, Any] | None) -> dict[str, Any] | None:
    if not t:
        return None
    keys = ("kind", "state", "venue", "venue_day", "setup_id", "setup_type", "qty", "entry", "stop", "target",
            "entry_order_id", "target_order_id", "stop_order_id", "fill_price", "filled_at", "exit_price",
            "exit_reason", "exits", "sent_at", "closed_at", "note")
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


def _notes(sym: str, mode: str, venue: str | None, day: str, bot: dict[str, Any]) -> list[dict[str, Any]]:
    if mode == STOCK_MODE_SIGNAL:
        return []
    out: list[dict[str, Any]] = []
    blocked = gates.desk_block()
    if blocked:
        out.append({"id": blocked[0].lower(), "tone": "warn", "text": blocked[1]})
    if gates.followed(sym) is False:
        out.append({"id": "not_followed", "tone": "warn", "text": STOCK_MODE_NOTE_NOT_FOLLOWED.format(sym=sym)})
    if mode == STOCK_MODE_BOT and not bot.get("playing"):
        out.append({"id": "bot_not_playing", "tone": "warn",
                    "text": f"The bot will not trade {sym} yet: {bot.get('reason') or 'it is not playing'}."})
    if mode == STOCK_MODE_BOT and bot.get("setup"):
        out.append({"id": "bot_setup", "tone": "info",
                    "text": f"The bot trades its chosen setup only: the {str(bot['setup']).replace('_', ' ')}."})
    if mode == STOCK_MODE_AUTO_ENTRY and store.entries_today(venue, day, sym) >= 1:
        out.append({"id": "entry_used", "tone": "info", "text": STOCK_MODE_NOTE_ENTRY_USED.format(sym=sym)})
    return out


def build(symbol: str, *, now: float | None = None) -> dict[str, Any]:
    from stock_mode.runner import venue_day

    now = time.time() if now is None else now
    sym = model.symbol(symbol)
    venue, replay = gates.venue_state()
    store.sync_venue(venue)
    row = _bot_row()
    bot = _bot_part(sym, row)
    sw = store.switch(sym)
    if bot["on_list"]:
        buy, sell = STOCK_MODE_SIDE_NOVA, STOCK_MODE_SIDE_NOVA
    elif sw:
        buy, sell = sw["buy"], sw["sell"]
    else:
        buy, sell = STOCK_MODE_SIDE_YOU, STOCK_MODE_SIDE_YOU
    mode = model.mode_of(buy, sell)
    day = venue_day(now)
    bot_trade = _bot_trade(sym, row)
    if bot_trade and bot_trade.get("venue") not in (None, venue):
        bot_trade = None                    # the bot's trade on another venue is not this desk's
    trade = _latest(_today(store.trade(venue, sym), day), _today(bot_trade, day))
    return {
        "schema_version": STOCK_MODE_SCHEMA_VERSION,
        "symbol": sym,
        "generated_at": now,
        "venue": venue,
        "mode": mode,
        "buy": buy,
        "sell": sell,
        "risk_usd": (sw or {}).get("risk_usd"),
        "set_at": (sw or {}).get("set_at"),
        "locks": model.locks(venue, replay),
        "notes": _notes(sym, mode, venue, day, bot),
        "approval": store.approval(sym),
        "trade": _public_trade(trade),
        "nova_entries_today": store.entries_today(venue, day, sym),
        "last_event": store.event(sym),
        "bot": bot if (bot["on_list"] or mode == STOCK_MODE_BOT or trade and trade.get("kind") == STOCK_MODE_BOT)
        else None,
    }


def all_stocks(*, now: float | None = None) -> list[dict[str, Any]]:
    """Every stock that is not at Signal only: the switches in memory and the bot's list."""
    from bot.eligibility import normalize_symbols

    now = time.time() if now is None else now
    syms = set(store.switches()) | set(normalize_symbols(_bot_row().get("symbol_allowlist")))
    return [build(s, now=now) for s in sorted(syms)]
