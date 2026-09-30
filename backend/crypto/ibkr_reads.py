"""The Cryptos page's IBKR reads (ADR 040), run from its refresher thread on the IB loop (``run_coro``).

- ``listing``: does IBKR list the coin (``Crypto(sym, venue, 'USD')`` contract details, Paxos then Zero Hash)?
  An empty answer is "no"; IB's "no security definition" for a crypto contract is not recorded as an error.
- ``quotes``: the bridge stocks' last trades, through the cold, droppable ``snapshot_quotes`` path. A snapshot
  with no trade yet (IBKR's prior close standing in, ``close_fallback``) is ``None``, never the close.
- ``rth_closes``: a stock's regular-hours daily closes, through the paced historical service at background
  priority (``request_rth_daily_closes``).
None of these opens a streaming line or places anything.
"""
from __future__ import annotations

import asyncio

from constants import IBKR_QUOTE_BATCH_TIMEOUT_SEC, IBKR_QUOTE_QUALITY_CLOSE_FALLBACK
from constants_crypto import CRYPTO_BRIDGE_CLOSES_DURATION, CRYPTO_IBKR_TIMEOUT_SEC, CRYPTO_LISTING_VENUES
from crypto.web import SourceError

SOURCE = "ibkr"


def ready() -> bool:
    from ibkr import client

    return client.is_ready()


def _run(coro, timeout: float, label: str):
    from ibkr.client_bridge import run_coro

    return run_coro(coro, timeout, label=label)


def listing(symbol: str) -> dict:
    """``{listed, venue}``: the first IBKR crypto venue that knows the coin, or ``listed: False``."""
    async def _ask() -> dict:
        from ib_async import Crypto

        from ibkr import client

        ib = client.get_ib()
        if ib is None:
            raise SourceError("IBKR is not connected")
        for venue in CRYPTO_LISTING_VENUES:
            details = await asyncio.wait_for(ib.reqContractDetailsAsync(Crypto(symbol, venue, "USD")),
                                             timeout=CRYPTO_IBKR_TIMEOUT_SEC)
            if details:
                return {"listed": True, "venue": venue}
        return {"listed": False, "venue": None}

    return _run(_ask(), CRYPTO_IBKR_TIMEOUT_SEC * len(CRYPTO_LISTING_VENUES) + 5, "crypto.listing")


def quotes(symbols: list[str]) -> dict[str, float | None]:
    """``{symbol: last trade}`` for the symbols IBKR answered; ``None`` where it has no trade yet."""
    from ibkr.discovery import snapshot_quotes

    got = _run(snapshot_quotes(list(symbols)), IBKR_QUOTE_BATCH_TIMEOUT_SEC * 2 + 10, "crypto.quotes") or {}
    out: dict[str, float | None] = {}
    for sym, q in got.items():
        if not isinstance(q, dict):
            continue
        no_trade = q.get("quote_quality") == IBKR_QUOTE_QUALITY_CLOSE_FALLBACK
        price = q.get("price")
        out[str(sym).upper()] = None if no_trade or not isinstance(price, (int, float)) else float(price)
    return out


def rth_closes(symbol: str) -> dict[str, float]:
    """``{session date: regular-hours close}``; raises ``HistoricalShed`` when IBKR's budget says later."""
    from ibkr import historical_service

    rows = _run(historical_service.request_rth_daily_closes(symbol, CRYPTO_BRIDGE_CLOSES_DURATION),
                CRYPTO_IBKR_TIMEOUT_SEC * 2, "crypto.rth_closes")
    return {day: close for day, close in rows}
