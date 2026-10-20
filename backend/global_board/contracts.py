"""The Global page's IBKR contracts (ADR 060): each market's index, index future and US-listed country ETF, and the
forex pairs that turn their money into dollars.

An instrument is ``(kind, spec)``: ``index`` (an ``Index``), ``future`` (IBKR's continuous future, which reads the
contract that leads in volume, so a roll does not lose the bars), ``etf`` (a SMART-routed ``Stock``) or ``fx`` (a
``Forex`` pair). A qualified contract is kept for the ET trading date. Must run on the IB connect-loop.
"""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from constants_global_board import GLOBAL_FX_PAIRS, GLOBAL_IBKR_TIMEOUT_SEC

_resolved: dict[tuple[str, str], Any] = {}   # (instrument key, ET date) -> qualified contract


def etf_spec(symbol: str) -> dict:
    return {"symbol": symbol, "exchange": "SMART", "currency": "USD", "label": f"{symbol} (US-listed ETF)"}


def fx_spec(currency: str) -> dict:
    pair, _usd_per_unit = GLOBAL_FX_PAIRS[currency]
    return {"symbol": pair, "exchange": "IDEALPRO", "currency": currency, "label": f"{pair[:3]}.{pair[3:]}"}


def key(kind: str, spec: Mapping) -> str:
    """``future:DAX:EUREX`` -- names the instrument in the store, the refusals and the pacing book."""
    return f"{kind}:{spec['symbol']}:{spec['exchange']}"


def instrument(kind: str, spec: Mapping, contract: Any = None) -> dict:
    """The wire's ``instrument`` block."""
    local = getattr(contract, "localSymbol", None) if kind == "future" else None
    return {"kind": kind, "symbol": spec["symbol"], "label": spec.get("label") or spec["symbol"],
            "exchange": spec["exchange"], "currency": spec["currency"], "contract": local or None,
            "multiplier": multiplier(kind, contract)}


def multiplier(kind: str, contract: Any) -> float | None:
    if kind != "future":
        return 1.0 if kind == "etf" else None
    try:
        value = float(getattr(contract, "multiplier", "") or "nan")
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _build(kind: str, spec: Mapping) -> Any:
    from ib_async import ContFuture, Forex, Index, Stock

    if kind == "index":
        return Index(spec["symbol"], spec["exchange"], spec["currency"])
    if kind == "future":
        return ContFuture(spec["symbol"], spec["exchange"], currency=spec["currency"],
                          multiplier=spec.get("multiplier") or "")
    if kind == "etf":
        return Stock(spec["symbol"], "SMART", "USD")
    if kind == "fx":
        return Forex(spec["symbol"])
    raise ValueError(f"no IBKR contract for {kind}")


async def resolve(ib: Any, kind: str, spec: Mapping, trading_date: str) -> Any | None:
    """The qualified contract, or ``None`` when IBKR does not know it (its reason is in ``ibkr.reference_errors``)."""
    k = (key(kind, spec), trading_date)
    if k in _resolved:
        return _resolved[k]
    got = await asyncio.wait_for(ib.qualifyContractsAsync(_build(kind, spec)), timeout=GLOBAL_IBKR_TIMEOUT_SEC)
    contract = next((c for c in got or [] if c is not None and getattr(c, "conId", 0)), None)
    if contract is not None:
        for stale in [s for s in _resolved if s[0] == k[0]]:
            del _resolved[stale]
        _resolved[k] = contract
    return contract


def reset_for_tests() -> None:
    _resolved.clear()
