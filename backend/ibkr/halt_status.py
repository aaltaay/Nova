"""In-memory IBKR ticker.halted observe for the L2 HaltEtaChip.

Owner: this module.
Invalidation: ticker.halted returns to 0 (trading resumed), or ``reset()``
(tests). NaN / None / -1 is unknown, not resume -- cancel+resubscribe
often delivers that before tick 49 repeats (#237). Not persisted -- a
process restart restarts ``halt_start`` from the next observed halt tick
or an RSS-open row (tooltip says observed vs Nasdaq). Incoming tick type
49 is default L1; never request generic 49.

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
    HALT_START_SOURCE_NASDAQ,
    classify_halt_code,
    classify_rss_reason_code,
    halt_chip_view,
    parse_halt_code,
)
from ibkr.nasdaq_halt_rss import sanitize_exchange_for_live_halt

logger = logging.getLogger(__name__)

# symbol -> live halt snapshot (None means not halted / cleared)
_state: dict[str, dict[str, Any]] = {}
# Symbols observed as not-halted this process -- a later halt is on-time.
_seen_clear: set[str] = set()
# RSS-open chips already logged this process (avoid snapshot spam).
_rss_announced: set[str] = set()


def reset() -> None:
    """Drop all observed halt rows (tests / reconnect hygiene)."""
    _state.clear()
    _seen_clear.clear()
    _rss_announced.clear()


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
    observed = row.get("halt_start")
    start_late = bool(row.get("start_late"))
    exchange = sanitize_exchange_for_live_halt(
        _exchange_overlay(symbol),
        start_late=start_late,
        now=now,
    )
    official = exchange.get("official_halt_start")
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
    ts = time.time() if now is None else now
    sym = (symbol or "").strip().upper()
    row = _state.get(sym)
    if row:
        return _payload(sym, row, ts)
    return _rss_open_payload(sym, ts)


def live_symbols() -> list[str]:
    return sorted(_state.keys())


def watch_symbols() -> list[str]:
    """IBKR-observed plus RSS-open names that snapshot() can chip."""
    names = set(_state)
    try:
        from ibkr import nasdaq_halt_feed
        names.update(nasdaq_halt_feed.open_symbols())
    except Exception:
        logger.debug("IBKR halt: RSS open-symbol list failed", exc_info=True)
    return sorted(names)


def _rss_open_payload(symbol: str, now: float) -> dict[str, Any] | None:
    """Seed a chip from an RSS open row when ticker.halted never arrived (#237)."""
    if not symbol or symbol in _seen_clear:
        return None
    exchange = _exchange_overlay(symbol)
    if not exchange.get("matched"):
        return None
    if exchange.get("trade_resume") is not None:
        return None
    kind = classify_rss_reason_code(exchange.get("reason_code"))
    official = exchange.get("official_halt_start")
    official_ts = official if isinstance(official, (int, float)) else None
    start_late = official_ts is None
    view = halt_chip_view(
        kind=kind,
        halt_start=official_ts if official_ts is not None else now,
        now=now,
        halted=True,
        start_late=start_late,
        official_halt_start=official_ts,
    )
    if view is None:
        return None
    if symbol not in _rss_announced:
        _rss_announced.add(symbol)
        logger.info(
            "Nasdaq halt: %s kind=%s reason=%s (RSS open row)",
            symbol, kind, exchange.get("reason_code"),
        )
    return {
        "halted": True,
        "kind": kind,
        "halt_code": None,
        "halt_start": official_ts if official_ts is not None else now,
        "halt_start_source": (
            HALT_START_SOURCE_NASDAQ if official_ts is not None else HALT_START_SOURCE
        ),
        "start_late": start_late,
        "reason": view["reason"],
        "rule": view["rule"],
        "source": "nasdaq_trade_halt_rss",
        "exchange": exchange,
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
    prev = _state.get(sym)
    # Missing / NaN / -1 is "unknown", not resume. cancel+resubscribe often
    # delivers NaN on the first price tick before tick 49 repeats (#237).
    if code is None or code == -1:
        if prev is not None:
            return snapshot(sym, now=ts), False
        return _rss_open_payload(sym, ts), False

    kind = classify_halt_code(code)

    if kind is None:
        _seen_clear.add(sym)
        _rss_announced.discard(sym)
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
    for sym in watch_symbols():
        snap = snapshot(sym, now=now)
        try:
            await broadcast_halt_update(sym, snap)
        except Exception:
            logger.debug("IBKR halt: overlay broadcast failed for %s", sym, exc_info=True)
