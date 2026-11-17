"""What the brain holds and has working on Paper, read from the owners' books (ADR 072 decision 2).

The brain's shares are the lots booked to holder ``brain``; a position handed to the operator (its switch went Off
while it held it) is no longer the brain's to trade and is left out. Every read that fails raises ``ReadError``: an
unknown is never read as flat.
"""
from __future__ import annotations

from typing import Any

from brain.constants_brain import BRAIN_ORIGIN, BRAIN_VENUE

_EPS = 1e-9


class ReadError(Exception):
    """Paper's ledger could not be read; the caller must not guess."""


def paper() -> Any:
    from practice.broker import for_venue

    return for_venue(BRAIN_VENUE)


def _owners(broker: Any) -> Any:
    owners = getattr(broker.ledger, "owners", None)
    if owners is None:
        raise ReadError("Paper keeps no books for the three traders")
    return owners


def handed() -> set[str]:
    """The stocks the brain still holds that were handed to the operator."""
    from traders import handed as _handed

    try:
        broker = paper()
        return {sym for sym, who in _handed.active(broker.venue, broker.ledger, broker.reference.now_ts()).items()
                if who == BRAIN_ORIGIN}
    except Exception as exc:
        raise ReadError(f"the handed marks could not be read: {exc}") from exc


def positions(*, with_handed: bool = False) -> dict[str, dict[str, float]]:
    """``{symbol: {qty, avg_cost}}`` of the brain's own shares on Paper (handed ones only when asked)."""
    try:
        broker = paper()
        skip = set() if with_handed else handed()
        out = {}
        for symbol, lots in _owners(broker).lots.items():
            lot = lots.get(BRAIN_ORIGIN)
            if lot is not None and abs(lot.qty) > _EPS and symbol not in skip:
                out[symbol] = {"qty": float(lot.qty), "avg_cost": float(lot.avg)}
        return out
    except ReadError:
        raise
    except Exception as exc:
        raise ReadError(f"Paper's positions could not be read: {exc}") from exc


def working() -> list[dict[str, Any]]:
    """The brain's working orders on Paper (a bracket's waiting exits too)."""
    try:
        return [r for r in paper().ledger.working_orders() if r.get("order_origin") == BRAIN_ORIGIN]
    except Exception as exc:
        raise ReadError(f"Paper's orders could not be read: {exc}") from exc


def entries(rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Its working entries: a buy that is not an exit leg."""
    live = working() if rows is None else rows
    return [r for r in live if str(r.get("side") or "").upper() == "BUY" and r.get("leg_role") in (None, "parent")]


def stop_of(symbol: str, rows: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Its resting stop on ``symbol``, or None."""
    sym = (symbol or "").upper()
    for row in (working() if rows is None else rows):
        if str(row.get("symbol") or "").upper() == sym and row.get("leg_role") == "stop" and row.get("stop_price") is not None:
            return row
    return None


def day_pnl() -> float:
    """The brain's P&L today on its own book: what it closed and what it holds at Paper's mark, fees included."""
    try:
        broker = paper()
        return float(_owners(broker).today(BRAIN_ORIGIN, broker.ledger.mark_or_cost)["day_pnl"])
    except ReadError:
        raise
    except Exception as exc:
        raise ReadError(f"the brain's day could not be read: {exc}") from exc


def mark(symbol: str) -> float | None:
    try:
        value = paper().ledger.mark_or_cost(symbol)
        return None if value is None else float(value)
    except Exception as exc:
        raise ReadError(f"Paper has no mark for {symbol}: {exc}") from exc
