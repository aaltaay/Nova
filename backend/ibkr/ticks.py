"""Shared owner-aware IBKR Level-1 (reqMktData) streams.

One underlying subscription per symbol. Owners (detail / scanner / hod) share
the stream via owner sets — tab switches must never cancel a selected ticker's
detail owner. Quote listeners receive every price change for scanner/HOD paths;
detail broadcasts keep the open quote panel on trade_update.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Optional

from constants import (
    IBKR_L1_MAX_SUBSCRIBE_PER_RECONCILE,
    IBKR_L1_QUALIFY_TIMEOUT_SEC,
)
from ibkr import client as _client
from ibkr.ticks_handler import get_last_event_ts, on_ticker_update

logger = logging.getLogger(__name__)

OWNER_DETAIL = "detail"
OWNER_SCANNER = "scanner"
OWNER_HOD = "hod"

BroadcastFn = Callable[..., Awaitable[None]]
FindCacheRowFn = Callable[[str], Optional[dict]]
# symbol, price, volume, prev_close, ts_unix; optional keyword-only quote_quality
QuoteListenerFn = Callable[..., None]

_Stock = None
_subs: dict[str, dict[str, Any]] = {}
_broadcast: BroadcastFn | None = None
_find_cache_row: FindCacheRowFn | None = None
_quote_listeners: list[QuoteListenerFn] = []
_subscribe_lock: asyncio.Lock | None = None


def configure(
    broadcast: BroadcastFn,
    find_cache_row: FindCacheRowFn,
    *,
    on_quote: QuoteListenerFn | None = None,
) -> None:
    global _broadcast, _find_cache_row
    _broadcast = broadcast
    _find_cache_row = find_cache_row
    if on_quote is not None and on_quote not in _quote_listeners:
        _quote_listeners.append(on_quote)


def add_quote_listener(listener: QuoteListenerFn) -> None:
    if listener not in _quote_listeners:
        _quote_listeners.append(listener)


def remove_quote_listener(listener: QuoteListenerFn) -> None:
    try:
        _quote_listeners.remove(listener)
    except ValueError:
        pass


def _get_lock() -> asyncio.Lock:
    global _subscribe_lock
    if _subscribe_lock is None:
        _subscribe_lock = asyncio.Lock()
    return _subscribe_lock


def _load_ib_types() -> bool:
    global _Stock
    if _Stock is not None:
        return True
    try:
        from ib_async import Stock
        _Stock = Stock
        return True
    except ImportError:
        return False


def _on_ticker_update(ticker: Any, symbol: str) -> None:
    on_ticker_update(
        ticker,
        symbol,
        subs=_subs,
        quote_listeners=_quote_listeners,
        find_cache_row=_find_cache_row,
        broadcast=_broadcast,
        owner_detail=OWNER_DETAIL,
    )


async def subscribe(symbol: str, owner: str = OWNER_DETAIL) -> bool:
    """Start or attach ``owner`` to a last-price stream. Returns True if live."""
    symbol = (symbol or "").strip().upper()
    owner = (owner or OWNER_DETAIL).strip().lower()
    if not symbol:
        return False
    async with _get_lock():
        if symbol in _subs:
            _subs[symbol]["owners"].add(owner)
            return True
        if not _load_ib_types():
            return False
        ib = _client.get_ib()
        if ib is None:
            return False

        contract = _Stock(symbol, "SMART", "USD")
        try:
            # Unbounded qualify stalls the subscribe lock → whole API wedges
            # (HTTP timeouts → CLOSE_WAIT on :8000). Always bound it.
            qualified = await asyncio.wait_for(
                ib.qualifyContractsAsync(contract),
                timeout=float(IBKR_L1_QUALIFY_TIMEOUT_SEC),
            )
            if not qualified:
                logger.warning("IBKR ticks: qualify failed for %s", symbol)
                return False
            contract = qualified[0]
        except asyncio.TimeoutError:
            logger.warning(
                "IBKR ticks: qualify timeout (%.1fs) for %s",
                float(IBKR_L1_QUALIFY_TIMEOUT_SEC),
                symbol,
            )
            return False
        except Exception as exc:
            logger.warning("IBKR ticks: qualify error for %s: %s", symbol, exc)
            return False

        try:
            ticker = ib.reqMktData(contract, "", False, False)
        except Exception as exc:
            logger.warning("IBKR ticks: reqMktData failed for %s: %s", symbol, exc)
            return False

        def handler(t, sym=symbol):
            _on_ticker_update(t, sym)

        ticker.updateEvent += handler
        _subs[symbol] = {
            "ticker": ticker,
            "contract": contract,
            "handler": handler,
            "owners": {owner},
            "last_price": None,
            "last_update_ts": None,
        }
        logger.info(
            "IBKR ticks: subscribed last-price for %s (conId=%s, owner=%s)",
            symbol, contract.conId, owner,
        )
        return True


async def unsubscribe(symbol: str, owner: str = OWNER_DETAIL) -> None:
    symbol = (symbol or "").strip().upper()
    owner = (owner or OWNER_DETAIL).strip().lower()
    if not symbol:
        return
    async with _get_lock():
        sub = _subs.get(symbol)
        if not sub:
            return
        owners = sub.get("owners") or set()
        owners.discard(owner)
        if owners:
            return
        ib = _client.get_ib()
        ticker = sub.get("ticker")
        handler = sub.get("handler")
        contract = sub.get("contract")
        if ticker is not None and handler is not None:
            try:
                ticker.updateEvent -= handler
            except (ValueError, AttributeError, KeyError) as exc:
                logger.debug("IBKR ticks: handler detach failed for %s: %s", symbol, exc)
        if ib is not None and contract is not None:
            try:
                ib.cancelMktData(contract)
            except Exception:
                logger.debug("IBKR ticks: cancelMktData failed for %s", symbol, exc_info=True)
        _subs.pop(symbol, None)
        logger.info("IBKR ticks: unsubscribed %s (last owner=%s)", symbol, owner)


async def set_owner_symbols(owner: str, symbols: list[str]) -> dict[str, Any]:
    """Reconcile subscriptions for ``owner`` to exactly ``symbols``.

    New subscribes are capped per call so explore rotation cannot queue dozens
    of qualifyContractsAsync calls under the subscribe lock in one tick.
    Deferred adds are retried on the next reconcile (~1s).
    """
    owner = (owner or "").strip().lower()
    desired = {(s or "").strip().upper() for s in symbols if s and str(s).strip()}
    current = {sym for sym, sub in _subs.items() if owner in (sub.get("owners") or set())}
    to_add = sorted(desired - current)
    to_drop = sorted(current - desired)
    # Only drop symbols that are not still desired — never drop deferred adds.
    max_add = max(1, int(IBKR_L1_MAX_SUBSCRIBE_PER_RECONCILE))
    add_now = to_add[:max_add]
    deferred = to_add[max_add:]
    ok = 0
    failed: list[str] = []
    for sym in add_now:
        if await subscribe(sym, owner):
            ok += 1
        else:
            failed.append(sym)
    for sym in to_drop:
        await unsubscribe(sym, owner)
    return {
        "owner": owner,
        "desired": len(desired),
        "subscribed": ok,
        "dropped": len(to_drop),
        "deferred": len(deferred),
        "failed": failed,
        "active": sorted(
            sym for sym, sub in _subs.items() if owner in (sub.get("owners") or set())
        ),
    }


def subscribed_symbols() -> list[str]:
    return list(_subs.keys())


def get_ticker(symbol: str) -> Any | None:
    """Raw ib_async Ticker for an already-subscribed symbol, or None.

    Lets other L1 consumers (e.g. depth's no-entitlement fallback) attach a
    read-only listener to the existing stream instead of opening a second
    ``reqMktData`` line for the same contract.
    """
    sub = _subs.get((symbol or "").strip().upper())
    return sub.get("ticker") if sub else None


def owners_for(symbol: str) -> set[str]:
    sub = _subs.get((symbol or "").strip().upper())
    if not sub:
        return set()
    return set(sub.get("owners") or set())


def last_quotes(symbols: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Return last known L1 price/ts for subscribed symbols (heartbeat use)."""
    wanted = None
    if symbols is not None:
        wanted = {(s or "").strip().upper() for s in symbols if s and str(s).strip()}
    out: dict[str, dict[str, Any]] = {}
    for sym, sub in _subs.items():
        if wanted is not None and sym not in wanted:
            continue
        price = sub.get("last_price")
        if price is None:
            continue
        try:
            px = float(price)
        except (TypeError, ValueError):
            continue
        row = {
            "price": px,
            "last_update_ts": sub.get("last_update_ts"),
            "owners": set(sub.get("owners") or set()),
        }
        dh = sub.get("day_high")
        if dh is not None:
            try:
                row["day_high"] = float(dh)
            except (TypeError, ValueError):
                pass
        out[sym] = row
    return out


def get_day_high(symbol: str) -> float | None:
    """IBKR L1 tick-6 day High for a subscribed symbol, if known."""
    sub = _subs.get((symbol or "").strip().upper())
    if not sub:
        return None
    dh = sub.get("day_high")
    if dh is None:
        return None
    try:
        h = float(dh)
    except (TypeError, ValueError):
        return None
    return h if h > 0 else None


def is_fresh(symbol: str, max_age_sec: float) -> bool:
    """True if ``symbol`` has a live stream that ticked within ``max_age_sec``."""
    sub = _subs.get(symbol.upper())
    if sub is None:
        return False
    last_ts = sub.get("last_update_ts")
    if last_ts is None:
        return False
    return (time.time() - last_ts) <= max_age_sec


async def clear_all_subscriptions(*, reason: str = "") -> int:
    """Drop every L1 ownership map entry after a reconnect / READY bump.

    The Gateway socket is gone, so we detach local handlers and clear
    ``_subs`` without calling ``cancelMktData``. Without this, ``subscribe``
    short-circuits on zombie entries and never re-issues ``reqMktData``
    (audit finding G1).
    """
    async with _get_lock():
        symbols = list(_subs.keys())
        for symbol in symbols:
            sub = _subs.get(symbol) or {}
            ticker = sub.get("ticker")
            handler = sub.get("handler")
            if ticker is not None and handler is not None:
                try:
                    ticker.updateEvent -= handler
                except (ValueError, AttributeError, KeyError, TypeError) as exc:
                    logger.debug(
                        "IBKR ticks: handler detach during clear for %s: %s",
                        symbol, exc,
                    )
            _subs.pop(symbol, None)
        if symbols:
            logger.warning(
                "IBKR ticks: cleared %d zombie L1 subscription(s) (%s)",
                len(symbols),
                reason or "unspecified",
            )
        return len(symbols)
