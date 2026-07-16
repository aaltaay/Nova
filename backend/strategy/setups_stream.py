"""
Background scan loop + WS broadcaster for setup signals (Gap and Go, Bull
Flag, ABCD). This module never places an order ITSELF — it evaluates
setups.py against the current watchlist, runs every eligible setup through
nova_os.decide() for an auditable verdict, and pushes signals to connected
clients. A BUY decision is routed to strategy.executor.on_signal(), which DOES
place paper orders when the current control mode is auto_paper (or stage a
ticket in confirm) — this loop is the trigger for that, not a signal-only path.

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
    SETUPS_IBKR_INTER_SYMBOL_DELAY_SEC,
    SETUPS_MAX_HISTORY,
    SETUPS_SCAN_INTERVAL_IBKR_SEC,
    SETUPS_SCAN_INTERVAL_SEC,
    SETUPS_SCAN_TOP_N,
    SETUPS_SCAN_TOP_N_IBKR,
)
from constants import NOVA_OS_DECISION_BUY
from journal.store import record_signal
from l2 import recorder as _l2_recorder
from nova_os import control_mode as _control_mode
from nova_os.decide import decide as nova_os_decide
from nova_os import staged_tickets as _staged
from strategy import executor as _executor
from strategy.setups import evaluate_setups
from strategy.watchlist import build_watchlist
from runtime_state import get_runtime_state

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
    state = get_runtime_state()
    seen: dict[str, dict] = {g["symbol"]: g for g in state.gainer_cache if g.get("symbol")}
    for g in state.gapper_cache:
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
    from alpaca import _get_discovery_provider
    from chart_bars import fetch_chart_bars
    from ibkr.historical_gate import interactive_busy

    loop = asyncio.get_event_loop()
    discovery_provider = _get_discovery_provider()
    universe = _watchlist_universe()
    by_symbol = {c["symbol"]: c for c in universe if c.get("symbol")}
    top_n = SETUPS_SCAN_TOP_N_IBKR if discovery_provider == "ibkr" else SETUPS_SCAN_TOP_N
    candidates = build_watchlist(universe, limit=top_n)
    now = time.time()

    for rank_idx, entry in enumerate(candidates):
        # Never starve the open ticker chart — skip this symbol this cycle.
        if discovery_provider == "ibkr" and interactive_busy():
            logger.debug("setups_stream: skip %s — interactive chart has historical slot", entry.symbol)
            continue

        symbol = entry.symbol
        row = by_symbol.get(symbol, {"symbol": symbol})
        try:
            bars_payload = await loop.run_in_executor(
                None,
                lambda sym=symbol: fetch_chart_bars(
                    sym, "1Min", 60, discovery_provider=discovery_provider, interactive=False,
                ),
            )
        except Exception as exc:
            logger.warning(
                "setups_stream: bars unavailable for %s (provider=%s): %s",
                symbol, discovery_provider, exc,
            )
            continue

        bars = bars_payload.get("bars", [])
        result = evaluate_setups(row, bars)
        watchlist_rank = rank_idx + 1
        for setup_name in result["eligible_setups"]:
            key = (symbol, setup_name)
            last = _last_alert_ts.get(key, 0.0)
            if now - last < SETUPS_ALERT_COOLDOWN_SEC:
                continue
            _last_alert_ts[key] = now

            # Nova OS decide() is the audit brain: journals a receipt for every
            # eligible setup. Pass the REAL current control mode — hardcoding
            # `signal` here made every receipt claim "mode": "signal" and
            # would_execute=False even while auto_paper/confirm was actually
            # armed and executor.on_signal() below went on to stage/place.
            # That split-brain is exactly what the audit trail must never do.
            decision = nova_os_decide(
                row,
                bars,
                watchlist_rank=watchlist_rank,
                mode=_control_mode.get_mode(),
                preferred_setup=setup_name,
            )
            signal_dict = result[setup_name]
            if decision.ticket:
                signal_dict = {
                    **signal_dict,
                    "entry_price": decision.ticket.get("entry", signal_dict.get("entry_price")),
                    "stop_price": decision.ticket.get("stop", signal_dict.get("stop_price")),
                    "target_price": decision.ticket.get("target", signal_dict.get("target_price")),
                    "shares": decision.ticket.get("shares"),
                    "nova_os": {
                        "decision": decision.decision,
                        "reason_codes": decision.reason_codes,
                        "mode": decision.mode,
                        "would_execute": decision.would_execute,
                        "receipt_id": decision.receipt.get("id"),
                    },
                }
            record = _record_signal(symbol, setup_name, signal_dict)
            await _broadcast({
                "type": "decision",
                "decision": decision.decision,
                "reason_codes": decision.reason_codes,
                "mode": decision.mode,
                "would_execute": decision.would_execute,
                "receipt_id": decision.receipt.get("id"),
                **record,
            })
            if decision.decision == NOVA_OS_DECISION_BUY:
                try:
                    await _executor.on_signal(symbol, setup_name, signal_dict)
                except Exception:
                    logger.exception(
                        "setups_stream: executor.on_signal failed for %s/%s", symbol, setup_name
                    )
            try:
                await _l2_recorder.on_signal(symbol, setup_name, record["timestamp"])
            except Exception:
                logger.exception("setups_stream: l2 recorder failed for %s/%s", symbol, setup_name)

        if discovery_provider == "ibkr":
            await asyncio.sleep(SETUPS_IBKR_INTER_SYMBOL_DELAY_SEC)


async def scan_loop() -> None:
    """Background asyncio task — call once from the app lifespan."""
    while True:
        try:
            _staged.expire_due()
            await _scan_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("setups_stream: scan cycle failed")
        from alpaca import _get_discovery_provider
        interval = (
            SETUPS_SCAN_INTERVAL_IBKR_SEC
            if _get_discovery_provider() == "ibkr"
            else SETUPS_SCAN_INTERVAL_SEC
        )
        await asyncio.sleep(interval)
