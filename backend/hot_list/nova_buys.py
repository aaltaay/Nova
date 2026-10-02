"""The Nova Buy sides the hot list takes back (ADR 044): every venue's bot list and the in-memory switches.

The 04:00 ET rollover clears every Nova Buy left from the day before (``clear_all``); removing a stock
from the list takes it off every venue's bot list (``drop``). Neither cancels an order: a trade Nova
holds keeps its exits -- the bot and stock mode manage those from the trade, not from a list.

The bot's lists are written here directly, beside stock mode (their owner for the desk's own venue,
ADR 042): taking a stock off a list needs none of stock mode's checks (the Live lock, "you hold it",
the cap all guard a Nova side being added), and another venue's list is out of stock mode's reach.
"""
from __future__ import annotations

import logging
from typing import Any

from constants_bot import BOT_BREAKER_VENUES
from constants_stock_mode import STOCK_MODE_BOT, STOCK_MODE_NAMES

logger = logging.getLogger(__name__)


def _lists(row: dict[str, Any]) -> list[tuple[str | None, list[str]]]:
    """Every venue's bot list in the session: the desk's own (the session's fields), then the stored dials."""
    from bot.eligibility import normalize_symbols
    from bot.venue_levels import stored_raw

    own = row.get("level_venue")
    out: list[tuple[str | None, list[str]]] = [(own, normalize_symbols(row.get("symbol_allowlist")))]
    for venue in BOT_BREAKER_VENUES:
        if venue != own:
            out.append((venue, normalize_symbols((stored_raw(row, venue) or {}).get("symbol_allowlist"))))
    return out


def _set_list(row: dict[str, Any], venue: str | None, names: list[str]) -> None:
    from bot.venue_levels import put

    if venue == row.get("level_venue"):
        row["symbol_allowlist"] = names
    else:
        put(row, str(venue), "symbol_allowlist", names)


def _clear_bot_lists() -> list[dict[str, Any]]:
    from bot.persist import load_session, save_session

    row = load_session()
    out: list[dict[str, Any]] = []
    for venue, names in _lists(row):
        if names:
            _set_list(row, venue, [])
            out += [{"venue": venue, "symbol": sym, "was": STOCK_MODE_BOT} for sym in names]
    if out:
        save_session(row)
    return out


def _clear_switches(now: float) -> list[dict[str, Any]]:
    """Every Auto-entry and Approve switch (memory, the desk's venue) and every approval not yet sent."""
    from stock_mode import gates, model, store

    venue, _replay = gates.venue_state()
    out: list[dict[str, Any]] = []
    for sym, switch in store.switches().items():
        mode = model.mode_of(switch.get("buy"), switch.get("sell"))
        store.clear_switch(sym)
        out.append({"venue": venue, "symbol": sym, "was": mode})
        store.note_event(sym, now, "info", f"{STOCK_MODE_NAMES.get(mode, mode)} was cleared at 04:00 ET: today's hot "
                                           "list starts fresh, and so does who buys")
    for sym, approval in store.approvals().items():
        if approval.get("state") != "sent":          # a sent one belongs to a trade Nova still manages
            store.clear_approval(sym)
    return out


def clear_all(now: float) -> tuple[list[dict[str, Any]], str | None]:
    """Clear every Nova Buy: ``(cleared, error)``. ``cleared`` is ``[{venue, symbol, was}]``; ``error`` says
    what could not be cleared (an unreadable bot session), never read as "nothing to clear"."""
    error = None
    try:
        cleared = _clear_bot_lists()
    except Exception as exc:
        logger.exception("hot list: the bot's stock lists could not be cleared at the rollover")
        cleared = []
        error = (f"the bot's stock lists could not be cleared ({type(exc).__name__}: {exc}); a stock still on one "
                 "is not bought until it is on today's hot list")
    return cleared + _clear_switches(now), error


def drop(sym: str) -> list[str]:
    """Take ``sym`` off every venue's bot list: the venues it was on. Raises when the session cannot be read."""
    from bot.persist import load_session, save_session

    row = load_session()
    venues: list[str] = []
    for venue, names in _lists(row):
        if sym in names:
            _set_list(row, venue, [s for s in names if s != sym])
            venues.append(str(venue))
    if venues:
        save_session(row)
    return venues
