"""
Continuous L2 + tape recording while a depth subscription is open.

Started from routes/trading.py when DepthLadder / depth WS subscribes; stopped
on unsubscribe. Snapshots the live book on L2_CONTINUOUS_SNAPSHOT_INTERVAL_SEC
and registers the symbol for Alpaca tape ingest. Never places orders.
Graceful no-op when IBKR is disconnected (caller should not start; if the
book goes empty mid-session we skip writes rather than crash).
"""
from __future__ import annotations

import asyncio
import logging
import time

from constants import (
    L2_CONTINUOUS_SNAPSHOT_INTERVAL_SEC,
    L2_SESSION_REASON_DEPTH,
)
from ibkr import depth as _depth
from l2 import sessions as _sessions
from l2 import tape as _tape
from l2.store import record_snapshot

logger = logging.getLogger(__name__)

_active: dict[str, dict] = {}  # symbol -> {session_id, task, recording_id}


def is_active(symbol: str) -> bool:
    return symbol.upper() in _active


def active_symbols() -> list[str]:
    return list(_active.keys())


async def _loop(symbol: str, session_id: str, recording_id: str) -> None:
    try:
        while symbol in _active:
            await asyncio.sleep(L2_CONTINUOUS_SNAPSHOT_INTERVAL_SEC)
            if symbol not in _active:
                break
            book = _depth.current_book(symbol)
            if book is None:
                continue
            record_snapshot(
                recording_id,
                symbol,
                L2_SESSION_REASON_DEPTH,
                _active[symbol]["started_ts"],
                time.time(),
                book,
                session_id=session_id,
                flush=False,
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("l2.continuous: loop failed for %s", symbol)
    finally:
        from l2 import batch as _batch
        _batch.flush()


def start(symbol: str) -> dict:
    """Begin continuous recording for an already-subscribed depth symbol."""
    sym = symbol.upper()
    if sym in _active:
        return {"ok": True, "session_id": _active[sym]["session_id"], "already": True}

    started_ts = time.time()
    session_id = _sessions.start_session(sym, L2_SESSION_REASON_DEPTH, started_ts=started_ts)
    recording_id = f"{sym}:depth:{started_ts}"
    _tape.watch_symbol(sym, session_id)
    task = asyncio.create_task(_loop(sym, session_id, recording_id))
    _active[sym] = {
        "session_id": session_id,
        "task": task,
        "recording_id": recording_id,
        "started_ts": started_ts,
    }
    logger.info("l2.continuous: started session %s for %s", session_id, sym)
    return {"ok": True, "session_id": session_id, "already": False}


async def stop(symbol: str) -> None:
    sym = symbol.upper()
    state = _active.pop(sym, None)
    if state is None:
        return
    _tape.unwatch_symbol(sym)
    task = state["task"]
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    _sessions.end_session(state["session_id"])
    from l2 import batch as _batch
    _batch.flush()
    logger.info("l2.continuous: ended session %s for %s", state["session_id"], sym)


def clear_for_tests() -> None:
    _active.clear()
