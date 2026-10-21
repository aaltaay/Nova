"""The Forex page's IBKR contracts (ADR 061): each currency's IDEALPRO pair and its CME future.

An instrument is ``(kind, spec)``: ``spot`` (a ``Forex`` pair on IDEALPRO) or ``future`` (IBKR's continuous future,
which reads the contract that leads in volume, so a roll does not lose the bars). A future IBKR does not know by its
``symbol`` is asked by each name in ``also``, in order. A qualified contract is kept for the ET trading date. Must run
on the IB connect-loop.
"""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from constants_forex_board import FOREX_IBKR_TIMEOUT_SEC

_resolved: dict[tuple[str, str], Any] = {}   # (instrument key, ET date) -> qualified contract


def spot_spec(cur: Mapping) -> dict | None:
    spot = cur.get("spot")
    if not spot:
        return None
    return {"symbol": spot["pair"], "exchange": "IDEALPRO", "currency": spot["pair"][3:], "quote": spot["quote"],
            "per_usd": spot["per_usd"], "label": f"{spot['quote']} spot (IDEALPRO)"}


def future_spec(cur: Mapping) -> dict | None:
    fut = cur.get("future")
    if not fut:
        return None
    return {**fut, "label": f"{fut['label']} ({fut['code']})"}


def key(kind: str, spec: Mapping) -> str:
    """``future:EUR:CME`` / ``spot:EURUSD:IDEALPRO`` -- names the instrument in the store, the refusals and the pacing
    book."""
    return f"{kind}:{spec['symbol']}:{spec['exchange']}"


def multiplier(kind: str, contract: Any) -> float | None:
    if kind != "future":
        return None
    try:
        value = float(getattr(contract, "multiplier", "") or "nan")
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def instrument(kind: str, spec: Mapping, contract: Any = None) -> dict:
    """The wire's ``instrument`` block."""
    local = getattr(contract, "localSymbol", None) if kind == "future" else None
    mult = multiplier(kind, contract)
    if mult is None and kind == "future":
        mult = float(spec["multiplier"])
    return {"kind": kind, "symbol": spec["symbol"], "label": spec.get("label") or spec["symbol"],
            "exchange": spec["exchange"], "currency": spec["currency"], "contract": local or None, "multiplier": mult}


def _build(kind: str, spec: Mapping, symbol: str | None = None) -> Any:
    from ib_async import ContFuture, Forex

    if kind == "spot":
        return Forex(spec["symbol"])
    if kind == "future":
        return ContFuture(symbol or spec["symbol"], spec["exchange"], currency=spec["currency"],
                          multiplier=spec.get("multiplier") or "")
    raise ValueError(f"no IBKR contract for {kind}")


async def resolve(ib: Any, kind: str, spec: Mapping, trading_date: str) -> Any | None:
    """The qualified contract, or ``None`` when IBKR does not know it (its reason is in ``ibkr.reference_errors``)."""
    k = (key(kind, spec), trading_date)
    if k in _resolved:
        return _resolved[k]
    contract = None
    names = (spec["symbol"], *(spec.get("also") or ())) if kind == "future" else (None,)
    for symbol in names:
        got = await asyncio.wait_for(ib.qualifyContractsAsync(_build(kind, spec, symbol)),
                                     timeout=FOREX_IBKR_TIMEOUT_SEC)
        contract = next((c for c in got or [] if c is not None and getattr(c, "conId", 0)), None)
        if contract is not None:
            break
    if contract is not None:
        for stale in [s for s in _resolved if s[0] == k[0]]:
            del _resolved[stale]
        _resolved[k] = contract
    return contract


def reset_for_tests() -> None:
    _resolved.clear()
