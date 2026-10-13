"""Level 1 lines for the feed's open positions, and the price now each one gives.

The lines are the desk's shared ones (``ibkr.ticks``), owned by ``FOLLOWED_LINE_OWNER``: a stock the scanner or a
Trader tab already streams costs no extra line, and a ``followed`` line counts against the cap like any line no
scanner owner holds, so the scanner plans its rows around it. ``want`` reconciles the owner's lines to the open
positions on the IB loop (``spawn_ib``) and never waits; ``release_if_idle`` lets them all go once no request came
for ``FOLLOWED_WANTED_SEC``. ``now_for`` reads the price from memory. Owner: this module's record of the lines it
asked for, in process memory (schema_version n/a).
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from followed_traders import pricing
from followed_traders.constants_followed import (
    FOLLOWED_LINE_OWNER,
    FOLLOWED_LINE_RECONCILE_SEC,
    FOLLOWED_MAX_LINES,
    FOLLOWED_WANTED_SEC,
)

logger = logging.getLogger(__name__)
Spawn = Callable[[str, Callable[[], Any]], None]

_lock = threading.Lock()
_holding: tuple[str, ...] = ()       # the symbols last asked for
_sent_at = 0.0
_wanted_until = 0.0
_in_flight = False


def reset_for_tests() -> None:
    global _holding, _sent_at, _wanted_until, _in_flight
    with _lock:
        _holding, _sent_at, _wanted_until, _in_flight = (), 0.0, 0.0, False


def plan(symbols: list[str]) -> tuple[list[str], set[str]]:
    """``(lines, over_cap)``: the first ``FOLLOWED_MAX_LINES`` distinct priceable symbols in order, and the rest."""
    lines: list[str] = []
    over: set[str] = set()
    for sym in symbols:
        if not pricing.priceable(sym) or sym in lines or sym in over:
            continue
        if len(lines) < FOLLOWED_MAX_LINES:
            lines.append(sym)
        else:
            over.add(sym)
    return lines, over


def want(symbols: list[str], now: float, *, spawn: Spawn | None = None) -> None:
    """Hold lines on exactly ``symbols`` (asked again every ``FOLLOWED_LINE_RECONCILE_SEC`` while one is missing)."""
    global _holding, _sent_at, _wanted_until, _in_flight
    desired = tuple(sorted(set(symbols)))
    missing = any(FOLLOWED_LINE_OWNER not in _owners(sym) for sym in desired)
    with _lock:
        _wanted_until = now + FOLLOWED_WANTED_SEC
        changed = desired != _holding
        due = now - _sent_at >= FOLLOWED_LINE_RECONCILE_SEC
        if _in_flight or not (changed or (missing and due)):
            return
        _holding, _sent_at, _in_flight = desired, now, True
    _send(desired, spawn)


def release_if_idle(now: float, *, spawn: Spawn | None = None) -> bool:
    """Let every line go when no request came for ``FOLLOWED_WANTED_SEC``. True when nothing is held (or asked)."""
    global _holding, _sent_at, _in_flight
    with _lock:
        if not _holding:
            return True
        if now < _wanted_until or _in_flight:
            return False
        _holding, _sent_at, _in_flight = (), now, True
    _send((), spawn)
    return True


def _send(symbols: tuple[str, ...], spawn: Spawn | None) -> None:
    global _in_flight
    try:
        (spawn or _spawn_ib)("followed.lines", lambda: _reconcile(symbols))
    except RuntimeError as exc:                     # the IB loop is not running: asked again on the next request
        logger.info("followed traders: lines not asked for (%s)", exc)
        with _lock:
            _in_flight = False


async def _reconcile(symbols: tuple[str, ...]) -> None:
    global _in_flight
    from ibkr import ticks

    try:
        await ticks.set_owner_symbols(FOLLOWED_LINE_OWNER, list(symbols))
    except Exception:  # the next request asks again; the rows say waiting meanwhile
        logger.warning("followed traders: reconciling the lines failed", exc_info=True)
    finally:
        with _lock:
            _in_flight = False


def _spawn_ib(name: str, factory: Callable[[], Any]) -> None:
    from ibkr.loop_supervisor import spawn_ib

    spawn_ib(name, factory)


def _owners(symbol: str) -> set[str]:
    from ibkr import ticks

    return ticks.owners_for(symbol)


# -- the price now --------------------------------------------------------------------------------


def now_state(state: str, *, price: float | None = None, trade_ts: float | None = None,
              why: str | None = None) -> dict[str, Any]:
    return {"state": state, "price": price, "trade_ts": trade_ts, "why": why}


def quotes(lines: list[str]) -> dict[str, dict[str, Any]]:
    """The price now for each line symbol, from the lines' memory (``ibkr.ticks``)."""
    from constants import IBKR_QUOTE_QUALITY_CLOSE_FALLBACK
    from ibkr import ticks

    rows = ticks.last_quotes(list(lines)) if lines else {}
    refused = {r["symbol"]: r for r in (ticks.refused_view().get("refused") or [])}
    out: dict[str, dict[str, Any]] = {}
    for sym in lines:
        row = rows.get(sym)
        if sym in refused:
            out[sym] = now_state("no_line", why=f"IBKR refused the line ({refused[sym].get('message') or 'no reason'})")
        elif row is None or row.get("price") is None:
            out[sym] = now_state("waiting", why="opening IBKR's line")
        elif row.get("quote_quality") == IBKR_QUOTE_QUALITY_CLOSE_FALLBACK:
            out[sym] = now_state("no_trade", why="IBKR has no trade today, only the prior close")
        else:
            trade_ts = row.get("last_trade_ts")
            out[sym] = now_state("live", price=float(row["price"]),
                                 trade_ts=float(trade_ts) if isinstance(trade_ts, (int, float)) else None)
    return out
