"""In-memory IBKR ticker.halted observe for the L2 HaltEtaChip.

Owner: this module.
Invalidation: ticker.halted returns to 0 / -1 / NaN (trading resumed), or
``reset()`` (tests). Not persisted -- a process restart restarts
``halt_start`` from the next observed halt tick (tooltip says observed,
not SIP). Incoming tick type 49 is default L1; never request generic 49.

A first halt without a prior not-halted tick is ``start_late`` (reconnect
or opened mid-halt). Nasdaq Trade Halt RSS may overlay official start /
resume when matched; missing RSS never invents those times.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from constants import HALT_LATE_START_SKEW_SEC
from ibkr.halt_eta import (
    HALT_START_SOURCE,
    classify_halt_code,
    halt_chip_view,
    parse_halt_code,
)

logger = logging.getLogger(__name__)

# symbol -> live halt snapshot (None means not halted / cleared)
_state: dict[str, dict[str, Any]] = {}
# Symbols observed as not-halted this process -- a later halt is on-time.
_seen_clear: set[str] = set()


def reset() -> None:
    """Drop all observed halt rows (tests / reconnect hygiene)."""
    _state.clear()
    _seen_clear.clear()


def _exchange_overlay(symbol: str) -> dict[str, Any]:
    try:
        from ibkr import nasdaq_halt_feed
    except Exception:
        logger.debug("IBKR halt: Nasdaq overlay import failed", exc_info=True)
        return {
            "status": "pending",
            "matched": False,
            "reason_code": None,
            "pause_threshold": None,
            "official_halt_start": None,
            "quote_resume": None,
            "trade_resume": None,
        }
    return nasdaq_halt_feed.overlay_for(symbol)


def _payload(symbol: str, row: dict[str, Any], now: float) -> dict[str, Any] | None:
    exchange = _exchange_overlay(symbol)
    official = exchange.get("official_halt_start")
    observed = row.get("halt_start")
    start_late = bool(row.get("start_late"))
    if (
        official is not None
        and observed is not None
        and float(observed) - float(official) > float(HALT_LATE_START_SKEW_SEC)
    ):
        start_late = True
    view = halt_chip_view(
        kind=row.get("kind"),
        halt_start=observed,
        now=now,
        halted=True,
        start_late=start_late,
        official_halt_start=official if isinstance(official, (int, float)) else None,
    )
    if view is None:
        return None
    return {
        "halted": True,
        "kind": row["kind"],
        "halt_code": row.get("halt_code"),
        "halt_start": observed,
        "halt_start_source": HALT_START_SOURCE,
        "start_late": start_late,
        "reason": view["reason"],
        "rule": view["rule"],
        "source": "ibkr_ticker_halted",
        "exchange": exchange,
    }


def snapshot(symbol: str, *, now: float | None = None) -> dict[str, Any] | None:
    """Current halt payload for ticker REST / WS, or None when not halted."""
    row = _state.get((symbol or "").strip().upper())
    if not row:
        return None
    return _payload(
        (symbol or "").strip().upper(),
        row,
        time.time() if now is None else now,
    )


def live_symbols() -> list[str]:
    return sorted(_state.keys())


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
        _seen_clear.add(sym)
        if prev is None:
            return None, False
        _state.pop(sym, None)
        logger.info("IBKR halt: %s cleared (ticker.halted=%s)", sym, code)
        return None, True

    if prev is not None and prev.get("kind") == kind and prev.get("halt_code") == code:
        return snapshot(sym, now=ts), False

    if prev is not None:
        halt_start = prev["halt_start"]
        start_late = bool(prev.get("start_late"))
    else:
        halt_start = ts
        start_late = sym not in _seen_clear

    _state[sym] = {
        "kind": kind,
        "halt_code": code,
        "halt_start": halt_start,
        "start_late": start_late,
    }
    if prev is None:
        logger.info(
            "IBKR halt: %s kind=%s code=%s start_observed=%.0f late=%s",
            sym, kind, code, halt_start, start_late,
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


async def broadcast_live_halts() -> None:
    """Re-push current overlays after an RSS refresh (display only)."""
    try:
        from websocket import broadcast_halt_update
    except Exception:
        logger.debug("IBKR halt: broadcast import failed", exc_info=True)
        return
    now = time.time()
    for sym in live_symbols():
        snap = snapshot(sym, now=now)
        try:
            await broadcast_halt_update(sym, snap)
        except Exception:
            logger.debug("IBKR halt: overlay broadcast failed for %s", sym, exc_info=True)
