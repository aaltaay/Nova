"""
Background scan loop + WS broadcaster for setup signals (Gap and Go, Bull
Flag, ABCD). Signal-only — this module never places, modifies, or cancels
orders; it only evaluates setups.py against the current watchlist and pushes
newly-eligible signals to connected clients.

Mirrors the WS-client pattern used by hod_momo.py, simplified: no per-strategy
config, just a global cooldown per (symbol, setup) pair to avoid spamming the
same signal every scan cycle.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from constants import (
    SETUPS_ALERT_COOLDOWN_SEC,
    SETUPS_MAX_HISTORY,
    SETUPS_SCAN_INTERVAL_SEC,
    SETUPS_SCAN_TOP_N,
)
from journal.store import record_signal
from l2 import recorder as _l2_recorder
from strategy import executor as _executor
from strategy.setups import evaluate_setups
from strategy.watchlist import build_watchlist

logger = logging.getLogger(__name__)

_ws_clients: set[Any] = set()
_last_alert_ts: dict[tuple[str, str], float] = {}
_signal_history: list[dict] = []


def add_ws_client(ws: Any) -> None:
    _ws_clients.add(ws)


def remove_ws_client(ws: Any) -> None:
    _ws_clients.discard(ws)


def get_signal_history() -> list[dict]:
    return list(_signal_history)


def _watchlist_universe() -> list[dict]:
    # Lazy import — main.py imports routes that import this module, so
    # importing main at module load time would be circular.
    import main as _main
    seen: dict[str, dict] = {g["symbol"]: g for g in _main._gainer_cache if g.get("symbol")}
    for g in _main._gapper_cache:
        if g.get("symbol"):
            seen[g["symbol"]] = g
    return list(seen.values())


async def _broadcast(payload: dict) -> None:
    if not _ws_clients:
        return
    text = json.dumps(payload)
    dead = []
    for ws in list(_ws_clients):
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)


def _record_signal(symbol: str, setup_name: str, signal_dict: dict) -> dict:
    record = {"setup": setup_name, "timestamp": time.time(), **signal_dict}
    _signal_history.append(record)
    del _signal_history[:-SETUPS_MAX_HISTORY]
    try:
        record_signal(
            symbol=symbol,
            setup=setup_name,
            entry_price=signal_dict.get("entry_price"),
            stop_price=signal_dict.get("stop_price"),
            target_price=signal_dict.get("target_price"),
            payload=signal_dict,
        )
    except Exception:
        logger.exception("setups_stream: failed to journal signal for %s/%s", symbol, setup_name)
    return record


async def _scan_once() -> None:
    from bars import fetch_bars

    loop = asyncio.get_event_loop()
    universe = _watchlist_universe()
    by_symbol = {c["symbol"]: c for c in universe if c.get("symbol")}
    candidates = build_watchlist(universe, limit=SETUPS_SCAN_TOP_N)
    now = time.time()

    for entry in candidates:
        symbol = entry.symbol
        row = by_symbol.get(symbol, {"symbol": symbol})
        try:
            bars_payload = await loop.run_in_executor(None, fetch_bars, symbol, "1Min", 60)
        except Exception as exc:
            logger.warning("setups_stream: bars fetch failed for %s: %s", symbol, exc)
            continue

        result = evaluate_setups(row, bars_payload.get("bars", []))
        for setup_name in result["eligible_setups"]:
            key = (symbol, setup_name)
            last = _last_alert_ts.get(key, 0.0)
            if now - last < SETUPS_ALERT_COOLDOWN_SEC:
                continue
            _last_alert_ts[key] = now
            record = _record_signal(symbol, setup_name, result[setup_name])
            await _broadcast({"type": "signal", **record})
            try:
                await _executor.on_signal(symbol, setup_name, result[setup_name])
            except Exception:
                logger.exception("setups_stream: executor.on_signal failed for %s/%s", symbol, setup_name)
            try:
                await _l2_recorder.on_signal(symbol, setup_name, record["timestamp"])
            except Exception:
                logger.exception("setups_stream: l2 recorder failed for %s/%s", symbol, setup_name)


async def scan_loop() -> None:
    """Background asyncio task — call once from the app lifespan."""
    while True:
        try:
            await _scan_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("setups_stream: scan cycle failed")
        await asyncio.sleep(SETUPS_SCAN_INTERVAL_SEC)
