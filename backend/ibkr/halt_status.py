"""In-memory IBKR ticker.halted observe for the L2 HaltEtaChip.

Owner: this module.
Invalidation: ticker.halted returns to 0 / -1 / NaN (trading resumed), or
``reset()`` (tests). Not persisted -- a process restart restarts
``halt_start`` from the next observed halt tick (tooltip says observed,
not SIP). Incoming tick type 49 is default L1; never request generic 49.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from ibkr.halt_eta import (
    HALT_START_SOURCE,
    classify_halt_code,
    halt_chip_view,
    parse_halt_code,
)

logger = logging.getLogger(__name__)

# symbol -> live halt snapshot (None means not halted / cleared)
_state: dict[str, dict[str, Any]] = {}


def reset() -> None:
    """Drop all observed halt rows (tests / reconnect hygiene)."""
    _state.clear()


def snapshot(symbol: str, *, now: float | None = None) -> dict[str, Any] | None:
    """Current halt payload for ticker REST / WS, or None when not halted."""
    row = _state.get((symbol or "").strip().upper())
    if not row:
        return None
    view = halt_chip_view(
        kind=row.get("kind"),
        halt_start=row.get("halt_start"),
        now=time.time() if now is None else now,
        halted=True,
    )
    if view is None:
        return None
    return {
        "halted": True,
        "kind": row["kind"],
        "halt_code": row.get("halt_code"),
        "halt_start": row.get("halt_start"),
        "halt_start_source": HALT_START_SOURCE,
        "reason": view["reason"],
        "rule": view["rule"],
        "source": "ibkr_ticker_halted",
    }


def observe_code(
    symbol: str,
    raw_code: Any,
    *,
    now: float | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    """Apply one ticker.halted reading. Returns (snapshot_or_None, changed)."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return None, False
    ts = time.time() if now is None else float(now)
    code = parse_halt_code(raw_code)
    kind = classify_halt_code(code)
    prev = _state.get(sym)

    if kind is None:
        if prev is None:
            return None, False
        _state.pop(sym, None)
        logger.info("IBKR halt: %s cleared (ticker.halted=%s)", sym, code)
        return None, True

    if prev is not None and prev.get("kind") == kind and prev.get("halt_code") == code:
        return snapshot(sym, now=ts), False

    halt_start = prev["halt_start"] if prev is not None else ts
    _state[sym] = {
        "kind": kind,
        "halt_code": code,
        "halt_start": halt_start,
    }
    if prev is None:
        logger.info(
            "IBKR halt: %s kind=%s code=%s start_observed=%.0f",
            sym, kind, code, halt_start,
        )
    return snapshot(sym, now=ts), True


def observe_from_ticker(
    symbol: str,
    ticker: Any,
    *,
    now: float | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    """Read ``ticker.halted`` (incoming tick type 49). Tape quiet is ignored."""
    return observe_code(symbol, getattr(ticker, "halted", None), now=now)
