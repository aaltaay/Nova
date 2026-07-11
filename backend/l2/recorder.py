"""
Level 2 recorder (Phase F + continuous/tape extensions).

When a setup signal fires, auto-subscribes IBKR depth for that symbol and
snapshots the order book on an interval for a fixed window, writing every
snapshot to SQLite via l2/store (batched). Also opens a record_session and
watches the symbol for Alpaca time & sales during the window.

Read-only with respect to trading -- this module never places, modifies, or
cancels an order, and nothing here feeds backend/strategy/executor.py.

Known limitation: IBKR market depth has no historical API -- only a live
subscription -- so a recording only ever covers the window AFTER a signal
fires, never before it.

Respects the existing IBKR_MAX_DEPTH_SYMBOLS cap: if a manual DepthLadder
subscription (or another recording) already holds the last slot, this
module skips recording rather than displacing it. If the symbol was already
subscribed by something else, this module records but does NOT unsubscribe
it when done -- it only releases subscriptions it created itself.
"""
from __future__ import annotations

import asyncio
import logging
import time

from constants import (
    L2_RECORD_WINDOW_SEC,
    L2_SESSION_REASON_SIGNAL,
    L2_SNAPSHOT_INTERVAL_SEC,
)
from ibkr import client as _ibkr_client
from ibkr import depth as _depth
from l2 import batch as _batch
from l2 import sessions as _sessions
from l2 import tape as _tape
from l2.store import record_snapshot

logger = logging.getLogger(__name__)

_active_recordings: set[str] = set()


def is_recording(symbol: str) -> bool:
    return symbol in _active_recordings


async def _record_window(
    symbol: str,
    setup: str,
    signal_ts: float,
    release_subscription: bool,
    session_id: str,
) -> None:
    recording_id = f"{symbol}:{signal_ts}"
    snapshots_written = 0
    elapsed = 0.0
    try:
        while elapsed < L2_RECORD_WINDOW_SEC:
            await asyncio.sleep(L2_SNAPSHOT_INTERVAL_SEC)
            elapsed += L2_SNAPSHOT_INTERVAL_SEC
            book = _depth.current_book(symbol)
            if book is None:
                continue
            record_snapshot(
                recording_id, symbol, setup, signal_ts, time.time(), book,
                session_id=session_id, flush=False,
            )
            snapshots_written += 1
        _batch.flush()
        logger.info(
            "l2.recorder: finished recording %s (%s snapshots) for %s/%s",
            recording_id, snapshots_written, symbol, setup,
        )
    except Exception:
        logger.exception("l2.recorder: recording %s failed", recording_id)
    finally:
        _active_recordings.discard(symbol)
        _tape.unwatch_symbol(symbol)
        _sessions.end_session(session_id)
        _batch.flush()
        if release_subscription:
            _depth.unsubscribe(symbol)


async def on_signal(symbol: str, setup: str, signal_ts: float) -> None:
    """Fire-and-forget: starts a background recording if IBKR is connected
    and a depth slot is available. Never raises -- a recorder failure must
    never affect the signal pipeline it was called from."""
    if symbol in _active_recordings:
        return
    if not _ibkr_client.is_connected():
        return

    was_already_subscribed = symbol in _depth.subscribed_symbols()
    result = _depth.subscribe(symbol)
    if not result["ok"]:
        logger.info("l2.recorder: skipping recording for %s (%s)", symbol, result["error"])
        return

    session_id = _sessions.start_session(
        symbol, L2_SESSION_REASON_SIGNAL, setup=setup, signal_ts=signal_ts, started_ts=signal_ts,
    )
    _tape.watch_symbol(symbol, session_id)
    _active_recordings.add(symbol)
    asyncio.create_task(
        _record_window(
            symbol, setup, signal_ts,
            release_subscription=not was_already_subscribed,
            session_id=session_id,
        )
    )
