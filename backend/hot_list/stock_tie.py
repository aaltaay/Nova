"""Who trades the stock, tied to today's hot list (ADR 043 decision 4: ADR 037's switch is the only "who").

- **Buy to Nova stars the stock** (``star_needed`` then ``star``, called by ``stock_mode.actions.set_mode``):
  a full or unreadable list refuses (``HOT_LIST_FULL`` / ``HOT_LIST_UNREADABLE``) before anything changes.
- **A new name takes the list's default** on the desk's venue (``apply_default``) when that venue allows a
  Nova side and the stock is at Signal only with no Nova trade; otherwise it stays You · You, and the
  stock's own view says so (``notes``). A default the switch refuses is said on the stock (its last event)
  and audited.
- **Removing a stock** (``unlist``) sets it to You · You on the desk's venue through stock mode's rules and
  takes it off every venue's bot list (``nova_buys.drop``); it is refused (``HOT_LIST_NOVA_TRADE``) while Nova
  has an open trade on it, or while Nova's trades cannot be read (unknown counts as open).
"""
from __future__ import annotations

import logging
import time
from typing import Any

from constants_hot_list import (
    HOT_LIST_AUDIT_ACTION,
    HOT_LIST_BY_NOVA_BUY,
    HOT_LIST_CAP,
    HOT_LIST_EVENT_DEFAULT,
    HOT_LIST_FULL,
    HOT_LIST_NOVA_TRADE,
)
from constants_stock_mode import (
    STOCK_MODE_AUTO_ENTRY,
    STOCK_MODE_BOT,
    STOCK_MODE_SIDE_NOVA,
    STOCK_MODE_SIDE_YOU,
    STOCK_MODE_SIGNAL,
    STOCK_MODE_TRADE_ENTERING,
    STOCK_MODE_TRADE_HOLDING,
)
from hot_list import service
from hot_list.errors import HotListError
from stock_mode.errors import StockModeError

logger = logging.getLogger(__name__)

_NOTE_ID = "hot_list_default"
_UNREADABLE_ID = "hot_list_unreadable"
_NOT_LISTED_ID = "hot_list_not_listed"
_NOVA_BUY_MODES = (STOCK_MODE_AUTO_ENTRY, STOCK_MODE_BOT)


def _side_words(buy: str, sell: str) -> str:
    return f"Buy {'Nova' if buy == STOCK_MODE_SIDE_NOVA else 'You'} · Sell {'Nova' if sell == STOCK_MODE_SIDE_NOVA else 'You'}"


# -- Buy to Nova stars the stock ------------------------------------------------------------------
def star_needed(sym: str, buy: str) -> bool:
    """True when Buy goes to Nova on a stock not on today's list (``star`` it before anything changes).
    Raises ``StockModeError`` when the list cannot take it: full, or not readable."""
    if buy != STOCK_MODE_SIDE_NOVA:
        return False
    try:
        doc = service.today()
    except HotListError as exc:
        raise StockModeError(exc.reason, f"{exc.message}. Nova buys only stocks on today's hot list, so Buy stays "
                             "with you", status=exc.status, field="buy") from exc
    if sym in service.listed(doc):
        return False
    if len(doc["entries"]) >= HOT_LIST_CAP:
        raise StockModeError(HOT_LIST_FULL, f"today's hot list is full ({HOT_LIST_CAP} stocks): Nova buys only listed "
                             f"stocks -- take one off before setting Buy to Nova on {sym}", field="buy")
    return True


def star(sym: str) -> None:
    """Star ``sym`` because its Buy goes to Nova; refusals come back as stock mode's."""
    try:
        service.star(sym, by=HOT_LIST_BY_NOVA_BUY)
    except HotListError as exc:
        raise StockModeError(exc.reason, exc.message, status=exc.status, field="buy") from exc


# -- a new name's default --------------------------------------------------------------------------
def _audit_default(sym: str, buy: str, sell: str, applied: bool, why: str | None) -> None:
    try:
        from bot.audit import record

        words = _side_words(buy, sell)
        record(action=HOT_LIST_AUDIT_ACTION, outcome=HOT_LIST_EVENT_DEFAULT,
               reason=f"{sym}: {words}" if applied else f"{sym} stays You · You, not {words}: {why}",
               inputs={"event": HOT_LIST_EVENT_DEFAULT, "symbol": sym, "buy": buy, "sell": sell, "applied": applied,
                       "why": why})
    except Exception:
        logger.warning("hot list: the default line for %s was not written to the audit stream", sym, exc_info=True)


def _at_signal(sym: str) -> str | None:
    """None when the stock is at Signal only with no Nova trade on it; else why its switch is left alone."""
    from bot.eligibility import normalize_symbols
    from bot.persist import load_session
    from stock_mode import store

    if store.switch(sym):
        return f"{sym} already has its own Who trades switch"
    try:
        on_list = sym in normalize_symbols(load_session().get("symbol_allowlist"))
    except Exception:
        logger.warning("hot list: the bot session could not be read -- %s's default is not applied", sym, exc_info=True)
        return "the bot session could not be read"
    if on_list:
        return f"{sym} is already the bot's on this venue"
    return open_trade(sym)


async def apply_default(sym: str, *, now: float | None = None) -> bool:
    """Give a name just added the list's default Buy / Sell on the desk's venue (see the module). True when set."""
    from stock_mode import actions, gates, model, store

    ts = time.time() if now is None else float(now)
    doc, error = service.peek(ts)
    if error is not None:
        return False
    buy, sell = doc["default"]["buy"], doc["default"]["sell"]
    if STOCK_MODE_SIDE_NOVA not in (buy, sell):
        return False
    venue, replay = gates.venue_state()
    lock = model.locks(venue, replay)
    why = lock["buy"] if buy == STOCK_MODE_SIDE_NOVA else lock["sell"]
    why = why or _at_signal(sym)
    if why is not None:
        _audit_default(sym, buy, sell, False, why)        # the stock's view says so (``notes``) on a locked venue
        return False
    try:
        await actions.set_mode(sym, buy, sell)
    except StockModeError as exc:
        why = exc.message
    except Exception as exc:
        logger.exception("hot list: %s's default Buy / Sell could not be set", sym)
        why = f"the switch could not be set ({type(exc).__name__}; the backend log has the error)"
    else:
        _audit_default(sym, buy, sell, True, None)
        return True
    store.note_event(sym, ts, "warn", f"Today's hot list could not start {sym} as {_side_words(buy, sell)}: {why}")
    _audit_default(sym, buy, sell, False, why)
    return False


def notes(sym: str, mode: str, venue: str | None, replay: bool) -> list[dict[str, Any]]:
    """The stock's own view (``stock_mode.view``): a listed name the default would give a Nova side that this
    venue does not allow (so it stays You · You); and, for a stock whose Buy is Nova, a list that does not hold
    it or cannot be read -- Nova buys only listed stocks."""
    from stock_mode import model

    try:
        doc, error = service.peek()
    except Exception as exc:
        logger.warning("hot list: today's list could not be read for %s's view", sym, exc_info=True)
        doc, error = None, f"{type(exc).__name__}: {exc}"
    if doc is None or error is not None:
        if mode not in _NOVA_BUY_MODES:
            return []
        return [{"id": _UNREADABLE_ID, "tone": "warn",
                 "text": f"Today's hot list cannot be read ({error}): Nova buys only listed stocks, so it buys "
                         f"nothing here, {sym} included."}]
    listed = sym in service.listed(doc)
    if mode in _NOVA_BUY_MODES and not listed:
        return [{"id": _NOT_LISTED_ID, "tone": "warn",
                 "text": f"{sym} is not on today's hot list, and Nova buys only listed stocks: star it (setting Buy "
                         "to Nova again does too)."}]
    if mode != STOCK_MODE_SIGNAL or not listed:
        return []
    buy, sell = doc["default"]["buy"], doc["default"]["sell"]
    if STOCK_MODE_SIDE_NOVA not in (buy, sell):
        return []
    lock = model.locks(venue, replay)
    why = lock["buy"] if buy == STOCK_MODE_SIDE_NOVA else lock["sell"]
    if why is None:
        return []
    return [{"id": _NOTE_ID, "tone": "info",
             "text": f"{sym} is on today's hot list, which starts a new name as {_side_words(buy, sell)}; here it "
                     f"stays You · You. {why}"}]


# -- removing a stock -------------------------------------------------------------------------------
def open_trade(sym: str) -> str | None:
    """Why Nova holds an open trade on ``sym`` on any venue, or None. A trade file or bot session that cannot
    be read counts as open: unknown, never "none"."""
    from stock_mode import store

    if store.load_error():
        return f"Nova's trades could not be read ({store.load_error()}), so whether it holds {sym} is unknown"
    for trade in store.trades():
        if str(trade.get("symbol") or "").upper() == sym \
                and trade.get("state") in (STOCK_MODE_TRADE_ENTERING, STOCK_MODE_TRADE_HOLDING):
            return (f"Nova has an open {str(trade.get('kind') or 'trade').replace('_', '-')} trade on {sym} "
                    f"({trade.get('state')}, {trade.get('venue')}) and manages it until it closes")
    try:
        from bot.persist import load_session

        bot_trade = load_session().get("trade")
    except Exception as exc:
        logger.warning("hot list: the bot session could not be read for %s's open trade", sym, exc_info=True)
        return f"the bot session could not be read ({type(exc).__name__}), so whether the bot holds {sym} is unknown"
    from bot.first_pullback.admit import LIVE_STATES

    if isinstance(bot_trade, dict) and str(bot_trade.get("symbol") or "").upper() == sym \
            and bot_trade.get("state") in LIVE_STATES:
        return (f"Nova's bot has an open trade on {sym} ({bot_trade.get('state')}, {bot_trade.get('venue')}) and "
                "manages it until it closes")
    return None


async def unlist(raw: Any, *, now: float | None = None) -> None:
    """Take a stock off today's list: You · You on every venue first (see the module)."""
    from hot_list import nova_buys
    from stock_mode import actions

    sym = service.symbol(raw)
    why = open_trade(sym)
    if why is not None:
        raise HotListError(HOT_LIST_NOVA_TRADE, f"{sym} stays on today's hot list: {why}", field="symbol")
    try:
        await actions.set_mode(sym, STOCK_MODE_SIDE_YOU, STOCK_MODE_SIDE_YOU)
    except StockModeError as exc:
        raise HotListError(exc.reason, f"{sym} stays on today's hot list: {exc.message}", status=exc.status,
                           field=exc.field) from exc
    try:
        nova_buys.drop(sym)
    except Exception as exc:
        logger.exception("hot list: %s could not be taken off the bot's lists", sym)
        raise HotListError(HOT_LIST_NOVA_TRADE, f"{sym} stays on today's hot list: it could not be taken off the "
                           f"bot's lists ({type(exc).__name__}: {exc}), so Nova might still buy it",
                           field="symbol") from exc
    service.remove(sym, now=now)

