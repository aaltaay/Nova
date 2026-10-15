"""The Live Trader bot's Level 1 lines: one on every stock it holds, is entering or waits to enter (ADR 055).

The operator's "keep space": the lines are the desk's shared ones (``ibkr.ticks``), owned by ``LT_LINE_OWNER``, so
a stock the scanner or a Trader tab already streams costs no extra line, and the scanner plans its rows around the
bot's. Never a Level 2 line. ``want`` reconciles the owner's lines on the IB loop (``spawn_ib``) and never waits;
a line still missing is asked for again on a later pass. Owner: this module's record of the lines it asked for,
in process memory (schema_version n/a).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from bot.live_trader.constants_live_trader import LT_LINE_OWNER

logger = logging.getLogger(__name__)
RECONCILE_SEC = 5.0
Spawn = Callable[[str, Callable[[], Any]], None]

_lock = threading.Lock()
_holding: tuple[str, ...] = ()
_sent_at = 0.0
_in_flight = False


def reset_for_tests() -> None:
    global _holding, _sent_at, _in_flight
    with _lock:
        _holding, _sent_at, _in_flight = (), 0.0, False


def holding() -> tuple[str, ...]:
    with _lock:
        return _holding


def want(symbols: set[str] | list[str], now: float | None = None, *, spawn: Spawn | None = None) -> None:
    """Hold lines on exactly ``symbols`` (asked again every ``RECONCILE_SEC`` while one is missing)."""
    global _holding, _sent_at, _in_flight
    now = time.time() if now is None else now
    desired = tuple(sorted({(s or "").strip().upper() for s in symbols if s}))
    missing = any(LT_LINE_OWNER not in _owners(sym) for sym in desired)
    with _lock:
        changed = desired != _holding
        if _in_flight or not (changed or (missing and now - _sent_at >= RECONCILE_SEC)):
            return
        _holding, _sent_at, _in_flight = desired, now, True
    try:
        (spawn or _spawn_ib)("live_trader.lines", lambda: _reconcile(desired))
    except RuntimeError as exc:               # the IB loop is not running: asked again on a later pass
        logger.info("Live Trader bot: lines not asked for (%s)", exc)
        with _lock:
            _in_flight = False


async def _reconcile(symbols: tuple[str, ...]) -> None:
    global _in_flight
    from ibkr import ticks

    try:
        await ticks.set_owner_symbols(LT_LINE_OWNER, list(symbols))
    except Exception:
        logger.warning("Live Trader bot: reconciling its lines failed", exc_info=True)
    finally:
        with _lock:
            _in_flight = False


def _spawn_ib(name: str, factory: Callable[[], Any]) -> None:
    from ibkr.loop_supervisor import spawn_ib

    spawn_ib(name, factory)


def _owners(symbol: str) -> set[str]:
    from ibkr import ticks

    try:
        return ticks.owners_for(symbol)
    except Exception:  # maintainer: allow-swallow an unreadable owner set reads "not held": the line is asked again
        logger.warning("Live Trader bot: %s's line owners could not be read", symbol, exc_info=True)
        return set()
