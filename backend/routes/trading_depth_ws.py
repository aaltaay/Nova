"""Level 2 depth WebSocket handler (split from ``routes.trading`` for the 400-line rule).

``/ws/ibkr/depth/{symbol}`` stays registered on ``routes.trading.ws_router``;
this module holds its body and the auto-record yield (ADR 023): the operator
never loses Level 2 to auto-record, which gives back a line before the
subscribe runs.

A hidden Trader tab lends its line (ADR 044 decision 6, ``line_lending``): the
Trader tab's Level 2 opens with ``?tab=1`` and ``front=1`` while it is the tab in
front. While a loan stands, a socket for the lender gets ``{"type": "lent", ...}``
and closes; one from the tab in front recalls the loan first. A standing socket
whose line is lent reads the same frame from its queue and closes
(``line_lending.socket_gate``; the Time & Sales socket does the same).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from book_watch.constants_book_watch import BOOK_WATCH_PUSH_SEC
from book_watch.ladder import LadderPush
from ibkr import depth as _depth
from ibkr.depth.stream import DEPTH_STREAM_HEARTBEAT_SEC
from line_lending import socket_gate

logger = logging.getLogger(__name__)


async def make_room(symbol: str) -> None:
    """Auto-record yields its lowest-ranked line when every line is in use."""
    try:
        from leaderboard import auto_record

        await auto_record.make_room_for(symbol)
    except Exception:
        logger.exception("AUTO-RECORD: could not yield a line for %s", symbol)


class _WatchFrames:
    """The book watcher's verdicts for one depth socket (ADR 033 amendment): asked at most
    every ``BOOK_WATCH_PUSH_SEC``, and only while the ladder shows the live line."""

    def __init__(self, symbol: str) -> None:
        self.push = LadderPush(symbol)
        self.next_check = 0.0
        self.failed = False

    def due(self, mono: float) -> dict[str, Any] | None:
        if mono < self.next_check:
            return None
        self.next_check = mono + BOOK_WATCH_PUSH_SEC
        try:
            from sim.mode import is_replay_desk

            return self.push.frame(live_line=not is_replay_desk())
        except Exception:
            # Once per socket: a verdict that cannot be built never costs the ladder its books.
            if not self.failed:
                self.failed = True
                logger.exception("book watch: no ladder frame for %s", self.push.symbol)
            return None


async def run_ws_depth(websocket: WebSocket, symbol: str) -> None:
    symbol = symbol.upper()
    await websocket.accept()
    tab, front = socket_gate.flags(websocket.query_params)

    # The line is lent (ADR 044): say so and close -- unless this is the tab in front, which recalled it.
    lent = await socket_gate.gate(symbol, front=front)
    if lent is not None:
        await websocket.send_text(json.dumps(lent))
        await websocket.close()
        return

    from l2 import continuous as _l2_continuous

    # Auto-subscribe if not already (a Sim tab at the live edge needs the real line, not its replay slot)
    if _depth.needs_subscribe(symbol):
        await make_room(symbol)
        result = await _depth.subscribe_async(symbol)
        if not result["ok"]:
            await websocket.send_text(json.dumps({"type": "error", "message": result["error"]}))
            await websocket.close()
            return

    try:
        _l2_continuous.start(symbol)
    except Exception:
        logger.exception("l2.continuous: failed to start for WS %s", symbol)

    # Everything from here on must be inside the try/finally: if the client
    # disconnects before the first send_text() completes (React effect
    # double-invoke, rapid symbol switching), send_text() itself raises
    # WebSocketDisconnect. That used to happen *before* ws_viewer_opened() was
    # paired with a matching close, permanently inflating the viewer count and
    # defeating cleanup (see PROBLEM_LOG 2026-07-13, "Level 2 depth line leak").
    viewer_opened = False
    socket_token: int | None = None
    queue: asyncio.Queue | None = None
    try:
        _depth.ws_viewer_opened(symbol)
        viewer_opened = True
        # No await between: the lending registry and the viewer count move together.
        socket_token = socket_gate.opened(symbol, tab=tab, front=front)

        # Remount race: a previous viewer's cleanup may have dropped the line
        # between our initial subscribe check and viewer_opened. Re-subscribe
        # before streaming so the line actually exists to hold a viewer queue.
        if _depth.needs_subscribe(symbol):
            result = await _depth.subscribe_async(symbol)
            if not result["ok"]:
                await websocket.send_text(json.dumps({"type": "error", "message": result["error"]}))
                return
            try:
                _l2_continuous.start(symbol)
            except Exception:
                logger.exception("l2.continuous: failed to restart for WS %s", symbol)

        # Own queue per viewer -- a shared per-symbol queue makes concurrent
        # viewers (StrictMode double-mount, or a second Trader tab on the
        # same symbol) competing consumers instead of both seeing every book
        # update (same defect class as tape_stream.py -- PROBLEM_LOG 2026-08-25).
        queue = _depth.open_viewer_queue(symbol)
        # A loan of this line that began while this socket subscribed pushed its frame before the queue existed.
        lent = socket_gate.lent_now(symbol, front=front)
        if lent is not None:
            await websocket.send_text(json.dumps(lent))
            await websocket.close()
            return
        await websocket.send_text(json.dumps({"type": "subscribed", "symbol": symbol}))

        # A symbol already subscribed by another viewer (or a fresh page
        # reload re-attaching to a still-open depth line) needs today's
        # snapshot right away — see should_send_current_book().
        current = _depth.current_book(symbol)
        if _depth.should_send_current_book(current):
            await websocket.send_text(json.dumps({"type": "book", "symbol": symbol, "data": current}))

        watch = _WatchFrames(symbol)
        last_sent = time.monotonic()
        async for item in _depth.stream(queue, timeout=BOOK_WATCH_PUSH_SEC):
            mono = time.monotonic()
            verdicts = watch.due(mono)
            if verdicts is not None:
                await websocket.send_text(json.dumps({"type": "book_watch", "symbol": symbol, "data": verdicts}))
                last_sent = mono
            if item is None:
                if mono - last_sent >= DEPTH_STREAM_HEARTBEAT_SEC:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                    last_sent = mono
                continue
            if item.get("type") == "lent":
                # Lent to a setup (ADR 044): the tab waits for it to come back, never by its backoff.
                await websocket.send_text(json.dumps(item))
                await websocket.close()
                break
            if item.get("type") == "error":
                # Line torn down out from under this viewer -- tell the
                # client, then close so its onclose backoff reconnects
                # (PROBLEM_LOG 2026-08-25). Live 4th-symbol refuses never
                # evict, so this path is unsubscribe / idle reclaim.
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "symbol": symbol,
                            "message": item.get("message") or "Depth error",
                        }
                    )
                )
                if item.get("evicted"):
                    await websocket.close()
                    break
            else:
                await websocket.send_text(json.dumps({"type": "book", "symbol": symbol, "data": item}))
                last_sent = mono
    except WebSocketDisconnect:
        logger.debug("IBKR depth WS disconnected: %s", symbol)
    except Exception as exc:
        from ws_close_errors import is_websocket_send_after_close

        if is_websocket_send_after_close(exc):
            logger.debug("IBKR depth WS send-after-close: %s", symbol)
        else:
            logger.exception("IBKR depth WS error for %s: %s", symbol, exc)
    finally:
        if queue is not None:
            _depth.close_viewer_queue(symbol, queue)
        socket_gate.closed(symbol, socket_token)
        # Release only once the LAST viewer is gone — and only after a short
        # grace window so React StrictMode / DepthLadder reconnects can
        # reattach without tearing down reqMktDepth (Connecting-depth flicker).
        # continuous.stop belongs here too: stopping it on every viewer close
        # killed recording for any remaining viewers of the same symbol.
        if viewer_opened and _depth.ws_viewer_closed(symbol):
            idle = await _depth.release_when_idle(symbol)
            if idle:
                try:
                    await _l2_continuous.stop(symbol)
                except Exception:
                    logger.exception("l2.continuous: failed to stop for WS %s", symbol)
                from l2 import recorder as _l2_recorder
                if not _l2_recorder.is_recording(symbol):
                    _depth.unsubscribe(symbol)
