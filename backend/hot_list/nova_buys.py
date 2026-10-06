"""The 04:00 ET reset of the bot's buys (ADR 044, amended 2026-10-06): every venue's bot list and the in-memory
Auto-entry / Approve switches, cleared at the hot list's rollover (``clear_all``), so yesterday's choices never
buy today. It cancels no order: a trade the bot holds keeps its exits -- the bot and stock mode manage those
from the trade, not from a list. The hot list itself never sets or clears who trades a stock.

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
        store.note_event(sym, now, "info", f"{STOCK_MODE_NAMES.get(mode, mode)} was reset at 04:00 ET: who buys "
                                           "starts fresh every day")
    for sym, approval in store.approvals().items():
        if approval.get("state") != "sent":          # a sent one belongs to a trade Nova still manages
            store.clear_approval(sym)
    return out


def clear_lists() -> tuple[list[dict[str, Any]], str | None]:
    """Every venue's bot list emptied: ``(cleared, error)``. ``error`` says why they could not be (an unreadable
    bot session), never read as "nothing to clear"; the hot list keeps it until a retry succeeds."""
    try:
        return _clear_bot_lists(), None
    except Exception as exc:
        logger.exception("hot list: the bot's stock lists could not be cleared at the rollover")
        return [], f"the bot's stock lists could not be cleared ({type(exc).__name__}: {exc})"


def clear_all(now: float) -> tuple[list[dict[str, Any]], str | None]:
    """Reset every bot buy: ``(cleared, error)``. ``cleared`` is ``[{venue, symbol, was}]``; ``error`` is
    ``clear_lists``'s. The switches live in memory and always clear."""
    cleared, error = clear_lists()
    return cleared + _clear_switches(now), error

