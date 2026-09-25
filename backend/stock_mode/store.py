"""The per-stock switch, the approvals and Nova's trades, in memory (ADR 037).

Owner: this module. Nothing here is persisted.
Invalidation:
- a process start: every stock is Signal only again;
- a venue change: ``sim.mode.set_venue`` calls ``venue_changed``, which clears every switch and every
  approval -- a practice switch never carries into another venue, like arming (ADR 018). Each read
  also passes the desk's venue (``sync_venue``), which catches a venue that changed without that call.
Trades and the day's entry counts are kept per venue: an order Nova sent stays managed until it fills,
misses or closes, whichever venue the desk shows now.
The bot's list is not here: Bot at Strategy is the bot session's ``symbol_allowlist`` (ADR 030).
"""
from __future__ import annotations

import copy
import threading
from typing import Any

_lock = threading.RLock()
_venue: str | None = None
_venue_seen = False
_switches: dict[str, dict[str, Any]] = {}
_approvals: dict[str, dict[str, Any]] = {}
_trades: dict[tuple[str, str], dict[str, Any]] = {}
_entries: dict[tuple[str, str, str], int] = {}
_events: dict[str, dict[str, Any]] = {}


def sync_venue(venue: str | None) -> bool:
    """Clear the switches and the approvals when the desk's venue changed. True when it changed."""
    global _venue, _venue_seen
    with _lock:
        if _venue_seen and venue == _venue:
            return False
        changed = _venue_seen
        _venue, _venue_seen = venue, True
        if changed:
            _switches.clear()
            _approvals.clear()
        return changed


def venue_changed(venue: str) -> None:
    """The desk moved venue (``sim.mode.set_venue``): every switch and approval is cleared, like arming."""
    global _venue, _venue_seen
    with _lock:
        _venue, _venue_seen = venue, True
        _switches.clear()
        _approvals.clear()


# -- the switch -------------------------------------------------------------------
def switch(symbol: str) -> dict[str, Any] | None:
    with _lock:
        row = _switches.get(symbol)
        return dict(row) if row else None


def set_switch(symbol: str, row: dict[str, Any]) -> None:
    with _lock:
        _switches[symbol] = dict(row)


def clear_switch(symbol: str) -> None:
    with _lock:
        _switches.pop(symbol, None)


def switches() -> dict[str, dict[str, Any]]:
    with _lock:
        return {k: dict(v) for k, v in _switches.items()}


# -- approvals --------------------------------------------------------------------
def approval(symbol: str) -> dict[str, Any] | None:
    with _lock:
        row = _approvals.get(symbol)
        return dict(row) if row else None


def set_approval(symbol: str, row: dict[str, Any]) -> None:
    with _lock:
        _approvals[symbol] = dict(row)


def clear_approval(symbol: str) -> None:
    with _lock:
        _approvals.pop(symbol, None)


def approvals() -> dict[str, dict[str, Any]]:
    with _lock:
        return {k: dict(v) for k, v in _approvals.items()}


# -- trades -----------------------------------------------------------------------
def trade(venue: str | None, symbol: str) -> dict[str, Any] | None:
    with _lock:
        row = _trades.get((str(venue), symbol))
        return copy.deepcopy(row) if row else None


def set_trade(trade_row: dict[str, Any]) -> None:
    with _lock:
        _trades[(str(trade_row["venue"]), str(trade_row["symbol"]))] = copy.deepcopy(trade_row)


def trades() -> list[dict[str, Any]]:
    with _lock:
        return [copy.deepcopy(t) for t in _trades.values()]


# -- the day's Nova entries (Auto-entry buys once per stock per venue day) ---------------
def entries_today(venue: str | None, day: str, symbol: str) -> int:
    with _lock:
        return int(_entries.get((str(venue), day, symbol), 0))


def add_entry(venue: str | None, day: str, symbol: str) -> None:
    with _lock:
        key = (str(venue), day, symbol)
        _entries[key] = _entries.get(key, 0) + 1


# -- the last event per stock -------------------------------------------------------
def event(symbol: str) -> dict[str, Any] | None:
    with _lock:
        row = _events.get(symbol)
        return dict(row) if row else None


def note_event(symbol: str, ts: float, tone: str, text: str) -> None:
    with _lock:
        _events[symbol] = {"ts": float(ts), "tone": tone, "text": text}


def reset_for_tests() -> None:
    global _venue, _venue_seen
    with _lock:
        _venue, _venue_seen = None, False
        _switches.clear()
        _approvals.clear()
        _trades.clear()
        _entries.clear()
        _events.clear()
