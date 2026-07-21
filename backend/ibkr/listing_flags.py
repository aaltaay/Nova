"""IBKR per-symbol listing / short-availability snapshot (not a price feed).

Uses qualify + ContractDetails + generic tick list 236 (shortableShares).
Never falls back to Alpaca. Failures return an explicit error payload.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from ib_async import Stock

from constants import IBKR_L1_QUALIFY_TIMEOUT_SEC
from ibkr import client as _client

logger = logging.getLogger(__name__)

# Generic ticks: 236 → shortableShares (+ related shortability fields on Ticker).
_SHORTABLE_GENERIC_TICKS = "236"
_SHORTABLE_WAIT_SEC = 1.8
_FETCH_TIMEOUT_SEC = 10.0


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

    ticker = None
    try:
        ticker = ib.reqMktData(contract, _SHORTABLE_GENERIC_TICKS, False, False)
        await asyncio.sleep(_SHORTABLE_WAIT_SEC)
        shares_raw = getattr(ticker, "shortableShares", None)
        shares: float | None
        try:
            shares = float(shares_raw) if shares_raw is not None else None
            if shares is not None and (shares != shares):  # NaN
                shares = None
        except (TypeError, ValueError):
            shares = None
        out["shortable_shares"] = shares
        short_type, detail = _short_type_from_shares(shares)
        out["short_type"] = short_type
        out["short_type_detail"] = detail
    except Exception as exc:
        logger.warning("IBKR listing_flags: shortable tick failed for %s: %s", sym, exc)
        out["error"] = f"shortable tick failed: {exc}"
    finally:
        if ticker is not None and ib is not None:
            try:
                ib.cancelMktData(contract)
            except Exception:
                logger.debug(
                    "IBKR listing_flags: cancelMktData failed for %s", sym, exc_info=True
                )

    return out


def fetch_listing_flags_sync(symbol: str) -> dict[str, Any]:
    """Thread-safe bridge for ticker builders (ThreadPoolExecutor)."""
    try:
        return _client.run_coro(_fetch_async(symbol), timeout=_FETCH_TIMEOUT_SEC)
    except RuntimeError as exc:
        return _empty(error=str(exc), connected=False)
    except Exception as exc:
        logger.warning("IBKR listing_flags sync failed for %s: %s", symbol, exc)
        return _empty(error=str(exc))
