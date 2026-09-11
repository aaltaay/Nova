"""IBKR per-symbol listing / short-availability snapshot (not a price feed).

Uses qualify + ContractDetails + generic tick list 236 (shortableShares).
Never falls back to Alpaca. Failures return an explicit error payload.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from ib_async import Stock

from constants import (
    IBKR_L1_QUALIFY_TIMEOUT_SEC,
    IBKR_LISTING_FLAGS_TIMEOUT_SEC,
    IBKR_SHORTABLE_TICK_WAIT_SEC,
)
from ibkr import client as _client

logger = logging.getLogger(__name__)

# Generic ticks: 236 → shortableShares (+ related shortability fields on Ticker).
_SHORTABLE_GENERIC_TICKS = "236"


def _empty(*, error: str | None = None, connected: bool = True) -> dict[str, Any]:
    return {
        "source": "ibkr",
        "connected": connected,
        "qualified": False,
        "con_id": None,
        "long_name": None,
        "stock_type": None,
        "exchange": None,
        "shortable_shares": None,
        "short_type": None,
        "short_type_detail": None,
        "tradable_hint": None,
        "error": error,
    }


def _short_type_from_shares(shares: float | None) -> tuple[str | None, str | None]:
    """Map IB shortableShares into a careful operator-facing label."""
    if shares is None:
        return None, "No shortableShares tick yet (HTB/locate unknown)."
    if shares <= 0:
        return (
            "hard_to_borrow",
            "shortableShares≤0 — locate/HTB likely required; not Alpaca ETB.",
        )
    if shares < 10_000:
        return (
            "limited",
            f"~{shares:,.0f} shares reported shortable — thin locate; verify in TWS.",
        )
    return (
        "available",
        f"~{shares:,.0f} shares reported shortable (IB tick 236) — still confirm before shorting.",
    )


async def _fetch_async(symbol: str) -> dict[str, Any]:
    ib = _client.get_ib()
    if ib is None or not ib.isConnected():
        return _empty(error="IB Gateway not connected", connected=False)

    sym = (symbol or "").strip().upper()
    if not sym:
        return _empty(error="empty symbol")

    contract = Stock(sym, "SMART", "USD")
    try:
        qualified = await asyncio.wait_for(
            ib.qualifyContractsAsync(contract),
            timeout=float(IBKR_L1_QUALIFY_TIMEOUT_SEC),
        )
    except Exception as exc:
        logger.warning("IBKR listing_flags: qualify failed for %s: %s", sym, exc)
        return _empty(error=f"qualify failed: {exc}")

    if not qualified:
        return _empty(error="contract not qualified on IBKR")

    contract = qualified[0]
    out = _empty()
    out["qualified"] = True
    out["connected"] = True
    out["con_id"] = getattr(contract, "conId", None)
    out["exchange"] = getattr(contract, "primaryExchange", None) or getattr(
        contract, "exchange", None
    )
    out["tradable_hint"] = "qualified"
    out["error"] = None

    try:
        details = await asyncio.wait_for(
            ib.reqContractDetailsAsync(contract),
            timeout=float(IBKR_L1_QUALIFY_TIMEOUT_SEC),
        )
        if details:
            cd = details[0]
            out["long_name"] = getattr(cd, "longName", None) or getattr(
                cd, "long_name", None
            )
            out["stock_type"] = getattr(cd, "stockType", None) or getattr(
                cd, "stock_type", None
            )
    except Exception as exc:
        logger.debug("IBKR listing_flags: contractDetails %s: %s", sym, exc)

    try:
        shares = await _shortable_shares(sym)
        out["shortable_shares"] = shares
        short_type, detail = _short_type_from_shares(shares)
        out["short_type"] = short_type
        out["short_type_detail"] = detail
    except Exception as exc:
        logger.warning("IBKR listing_flags: shortable tick failed for %s: %s", sym, exc)
        out["error"] = f"shortable tick failed: {exc}"

    return out


def _shares_or_none(ticker: Any) -> float | None:
    raw = getattr(ticker, "shortableShares", None)
    if raw is None:
        return None
    try:
        shares = float(raw)
    except (TypeError, ValueError):
        return None
    return None if shares != shares else shares  # NaN


async def _shortable_shares(symbol: str) -> float | None:
    """Read tick-236 shortableShares off the shared owner-aware L1 line.

    Never opens a private ``reqMktData``: that call is idempotent per contract,
    so it would hand back the desk's pooled ticker without the extra tick, and
    the matching ``cancelMktData`` would close the scanner/detail stream. The
    wait is event-driven -- a fixed sleep parked the IB connect-loop coroutine
    for the whole window even when the tick had already landed.
    """
    from ibkr import ticks as _ticks

    if not await _ticks.subscribe(
        symbol, _ticks.OWNER_LISTING, generic_ticks=_SHORTABLE_GENERIC_TICKS,
    ):
        return None
    try:
        ticker = _ticks.get_ticker(symbol)
        if ticker is None or not _ticks.has_generic_tick(
            symbol, _SHORTABLE_GENERIC_TICKS,
        ):
            return None
        shares = _shares_or_none(ticker)
        if shares is not None:
            return shares
        return await _await_shortable_tick(ticker)
    finally:
        await _ticks.unsubscribe(symbol, _ticks.OWNER_LISTING)


async def _await_shortable_tick(ticker: Any) -> float | None:
    """Wait for the first shortableShares update, bounded by the tick budget."""
    arrived: asyncio.Future[float] = asyncio.get_running_loop().create_future()

    def _on_update(t: Any) -> None:
        shares = _shares_or_none(t)
        if shares is not None and not arrived.done():
            arrived.set_result(shares)

    ticker.updateEvent += _on_update
    try:
        return await asyncio.wait_for(
            arrived, timeout=float(IBKR_SHORTABLE_TICK_WAIT_SEC),
        )
    except asyncio.TimeoutError:
        return None
    finally:
        try:
            ticker.updateEvent -= _on_update
        except (ValueError, AttributeError, KeyError, TypeError) as exc:
            logger.debug("IBKR listing_flags: tick listener detach failed: %s", exc)


def fetch_listing_flags_sync(symbol: str) -> dict[str, Any]:
    """Thread-safe bridge for ticker builders (ThreadPoolExecutor)."""
    try:
        return _client.run_coro(
            _fetch_async(symbol), timeout=float(IBKR_LISTING_FLAGS_TIMEOUT_SEC),
        )
    except RuntimeError as exc:
        return _empty(error=str(exc), connected=False)
    except Exception as exc:
        logger.warning("IBKR listing_flags sync failed for %s: %s", symbol, exc)
        return _empty(error=str(exc))
