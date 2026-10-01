"""The per-stock switch, the approvals and Nova's trades (ADR 037, ADR 042 F).

Owner: this module.

- **The switch and the approvals** are in memory (ADR 037 decision 3): a process start
  returns every stock to Signal only, and a venue change (``sim.mode.set_venue`` ->
  ``venue_changed``) clears them -- a practice switch never carries into another venue,
  like arming (ADR 018). Each read also passes the desk's venue (``sync_venue``), which
  catches a venue that changed without that call. The bot's stocks are not here: Bot is
  the bot session's per-venue ``symbol_allowlist``, written through ``stock_mode.actions``.
- **Nova's trades are persisted** -- ``stock-mode-trades.json`` in the operator cache,
  ``{schema_version: 1, trades: [trade]}`` (one per venue and stock, the latest) -- so a
  restart resumes managing them (the entry's TTL cancel, the fill and close notices). An
  order Nova sent stays managed until it fills, misses or closes, whichever venue the
  desk shows now. A file of another version, or one that cannot be read, is refused
  loudly: it is never overwritten, its trades are not managed, and every stock's view says
  so (``load_error``). Done trades older than ``STOCK_MODE_TRADES_KEEP_DAYS`` are dropped
  on save.
- **The last event per stock** is in memory: what Nova (the bot included) last did or
  skipped on it.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from constants_stock_mode import (
    STOCK_MODE_TRADES_FILENAME,
    STOCK_MODE_TRADES_KEEP_DAYS,
    STOCK_MODE_TRADES_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_venue: str | None = None
_venue_seen = False
_switches: dict[str, dict[str, Any]] = {}
_approvals: dict[str, dict[str, Any]] = {}
_trades: dict[tuple[str, str], dict[str, Any]] = {}
_events: dict[str, dict[str, Any]] = {}
_loaded = False
_load_error: str | None = None
_LIVE = ("entering", "holding")


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


# -- trades (persisted) -------------------------------------------------------------
def _path() -> Path:
    from paths import cache_dir

    return cache_dir() / STOCK_MODE_TRADES_FILENAME


def _load() -> None:
    """Read the trades file once per process; refuse an unknown version loudly."""
    global _loaded, _load_error
    if _loaded:
        return
    _loaded = True
    path = _path()
    if not path.exists():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        version = raw.get("schema_version") if isinstance(raw, dict) else None
        if version != STOCK_MODE_TRADES_SCHEMA_VERSION:
            raise ValueError(f"schema_version={version!r} (expected {STOCK_MODE_TRADES_SCHEMA_VERSION})")
        rows = raw.get("trades")
        if not isinstance(rows, list):
            raise ValueError("no trades list")
    except Exception as exc:
        _load_error = (f"Nova's stock-mode trades file {path.name} could not be read ({exc}): the trades it sent "
                       "before the restart are not managed -- check its orders on the Trader, and the file is "
                       "left as it is")
        logger.exception("stock mode: %s", _load_error)
        return
    for row in rows:
        if isinstance(row, dict) and row.get("venue") and row.get("symbol"):
            _trades[(str(row["venue"]), str(row["symbol"]))] = dict(row)
    logger.info("stock mode: %d trade(s) restored from %s", len(_trades), path.name)


def _keep(row: dict[str, Any], now: float) -> bool:
    if row.get("state") in _LIVE:
        return True
    done = float(row.get("closed_at") or row.get("sent_at") or now)
    return now - done <= STOCK_MODE_TRADES_KEEP_DAYS * 86_400


def _save() -> None:
    if _load_error is not None:
        logger.error("stock mode: the trades file was not written -- %s", _load_error)
        return
    now = time.time()
    rows = [t for t in _trades.values() if _keep(t, now)]
    path = _path()
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps({"schema_version": STOCK_MODE_TRADES_SCHEMA_VERSION, "trades": rows}, indent=2,
                                    default=str))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError:
        logger.exception("stock mode: the trades file could not be written -- a restart would not resume them")


def load_error() -> str | None:
    with _lock:
        _load()
        return _load_error


def trade(venue: str | None, symbol: str) -> dict[str, Any] | None:
    with _lock:
        _load()
        row = _trades.get((str(venue), symbol))
        return copy.deepcopy(row) if row else None


def set_trade(trade_row: dict[str, Any]) -> None:
    with _lock:
        _load()
        _trades[(str(trade_row["venue"]), str(trade_row["symbol"]))] = copy.deepcopy(trade_row)
        _save()


def trades() -> list[dict[str, Any]]:
    with _lock:
        _load()
        return [copy.deepcopy(t) for t in _trades.values()]


# -- the last event per stock -------------------------------------------------------
def event(symbol: str) -> dict[str, Any] | None:
    with _lock:
        row = _events.get(symbol)
        return dict(row) if row else None


def note_event(symbol: str, ts: float, tone: str, text: str) -> None:
    with _lock:
        _events[symbol] = {"ts": float(ts), "tone": tone, "text": text}


def reset_for_tests() -> None:
    global _venue, _venue_seen, _loaded, _load_error
    with _lock:
        _venue, _venue_seen = None, False
        _switches.clear()
        _approvals.clear()
        _trades.clear()
        _events.clear()
        _loaded, _load_error = False, None


def forget_for_tests() -> None:
    """A restart in a test: memory goes, the file stays."""
    global _loaded, _load_error, _venue, _venue_seen
    with _lock:
        _switches.clear()
        _approvals.clear()
        _trades.clear()
        _events.clear()
        _loaded, _load_error = False, None
        _venue, _venue_seen = None, False
