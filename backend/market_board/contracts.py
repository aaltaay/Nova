"""The Market page's IBKR contracts (ADR 053): the tiles' futures, indexes and crypto, and NYSE's indicators.

A ``CONTFUT`` spec is IBKR's continuous future: qualifying it names the front month, which IBKR only quotes as a
plain ``FUT`` -- so the front month is qualified again by its own conId and kept for the trading date (a new date
re-resolves, which follows the roll). Must run on the IB connect-loop.
"""
from __future__ import annotations

import asyncio
from typing import Any

from constants_market_board import MARKET_BREADTH, MARKET_IBKR_TIMEOUT_SEC

_resolved: dict[tuple[str, str], Any] = {}   # (spec id, trading date) -> qualified contract


def breadth_specs() -> list[dict]:
    """NYSE's indicators as specs: ``{id, symbol, sec_type: "IND", exchange: "NYSE"}``."""
    return [{"id": key, "symbol": sym, "sec_type": "IND", "exchange": "NYSE"} for key, sym in MARKET_BREADTH.items()]


def _build(spec: dict) -> Any:
    from ib_async import ContFuture, Crypto, Index

    sec = spec["sec_type"]
    if sec == "CONTFUT":
        return ContFuture(spec["symbol"], spec["exchange"], currency="USD")
    if sec == "IND":
        return Index(spec["symbol"], spec["exchange"], "USD")
    if sec == "CRYPTO":
        return Crypto(spec["symbol"], spec["exchange"], "USD")
    raise ValueError(f"no IBKR contract for {sec}")


async def resolve(ib: Any, spec: dict, trading_date: str) -> Any | None:
    """The quotable contract for ``spec`` on ``trading_date``, or ``None`` when IBKR does not know it."""
    key = (spec["id"], trading_date)
    if key in _resolved:
        return _resolved[key]
    from ib_async import Contract

    got = await asyncio.wait_for(ib.qualifyContractsAsync(_build(spec)), timeout=MARKET_IBKR_TIMEOUT_SEC)
    contract = next((c for c in got or [] if c is not None and getattr(c, "conId", 0)), None)
    if contract is not None and spec["sec_type"] == "CONTFUT":
        front = await asyncio.wait_for(
            ib.qualifyContractsAsync(Contract(conId=contract.conId, exchange=spec["exchange"])),
            timeout=MARKET_IBKR_TIMEOUT_SEC)
        contract = next((c for c in front or [] if c is not None and getattr(c, "conId", 0)), None)
    if contract is not None:
        for stale in [k for k in _resolved if k[0] == spec["id"]]:
            del _resolved[stale]
        _resolved[key] = contract
    return contract


def local_symbol(contract: Any) -> str | None:
    """The front month's own name ("ESZ6"), ``None`` for an index or a coin."""
    if contract is None or str(getattr(contract, "secType", "")) != "FUT":
        return None
    return getattr(contract, "localSymbol", None) or None


def reset_for_tests() -> None:
    _resolved.clear()
