"""Level 2 depth WebSocket handler (split from ``routes.trading`` for the 400-line rule).

``/ws/ibkr/depth/{symbol}`` stays registered on ``routes.trading.ws_router``; this module holds its body.

The lanes hold every live line (ADR 071, ``line_lanes``). A socket opened in front (``front=1``) puts your lane on
its stock before it asks for its line; any other socket joins a stock a lane is on, and for a stock no lane is on it
reads the lanes' refusal (``lane``: who is on what) and closes. A socket closing never ends a lane's line; when the
lane leaves its stock, the socket reads ``{"type": "error", message, evicted: true, lane}`` and closes, and its pane
waits for the operator instead of asking again.

Every book frame carries its version (``seq``, ``at``) and ``sent``; with nothing new for
``MARKET_VIEW_BEAT_SEC`` the socket says the newest version is still current (``beat``), so the
desk can tell a quiet book from a stalled socket and lock orders on the latter (ADR 045).

IBKR refusing the line (309) reaches the socket as an ``error`` frame with ``evicted``, and the
socket closes so the ladder asks again on its backoff. A refusal that lands before this socket's
queue exists is read from ``depth.refusal`` instead, so a refused ladder never streams beats as if
a book were coming (operator report 2026-10-13: "Waiting for book data..." for good).

"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

import instance_identity
from book_watch.constants_book_watch import BOOK_WATCH_PUSH_SEC
from book_watch.ladder import LadderPush
from constants_market_view import MARKET_VIEW_BEAT_SEC
from ibkr import depth as _depth
from ibkr.depth.state import book_version
from ibkr.depth.stream import beat_frame, book_frame
from line_lanes import lanes as _lanes
from line_lanes import sockets as _lane
from market_view.viewer_queues import BookVersion

logger = logging.getLogger(__name__)


def refusal_frame(symbol: str, result: dict) -> dict:
    """The ladder's error frame for a subscribe that failed; with ``lane`` (who is on what) when no lane is on the
    stock (ADR 071), so the pane waits for the operator instead of asking again."""
    frame = {"type": "error", "symbol": symbol, "message": result.get("error") or "Depth error"}
    if result.get("lane"):
        frame.update(evicted=True, lane=_lanes.wire())
    return frame


async def send_refusal(websocket: WebSocket, symbol: str) -> bool:
    """IBKR refused this symbol's line (309) since it was asked for: say why and end the socket."""
    message = _depth.refusal(symbol)
    if message is None:
        return False
    await websocket.send_text(json.dumps({"type": "error", "symbol": symbol, "message": message, "evicted": True}))
    await websocket.close()
    return True


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


class _LuldFrames:
    """The LULD bands for one depth socket (ADR 047): asked at most every ``LULD_PUSH_SEC``, sent
    when they change (``luld/ladder.py``). Memory reads only, safe on the socket loop."""

    def __init__(self, symbol: str) -> None:
        from luld.ladder import LuldPush

        self.push = LuldPush(symbol)
        self.next_check = 0.0
        self.failed = False

    def due(self, mono: float) -> dict[str, Any] | None:
        if mono < self.next_check:
            return None
        from luld.constants_luld import LULD_PUSH_SEC

        self.next_check = mono + LULD_PUSH_SEC
        try:
            return self.push.frame()
        except Exception:
            # Once per socket: a band that cannot be read never costs the ladder its books.
            if not self.failed:
                self.failed = True
                logger.exception("LULD: no ladder frame for %s", self.push.symbol)
            return None


async def run_ws_depth(websocket: WebSocket, symbol: str) -> None:
    symbol = symbol.upper()
    await websocket.accept()
    tab, front = _lane.flags(websocket.query_params)

    from l2 import continuous as _l2_continuous

    # In front: your lane goes to this stock now -- the old stock's lines end first (ADR 071).
    await _lane.opening(symbol, front=front)

    # Auto-subscribe if not already (a Sim tab at the live edge needs the real line, not its replay slot)
    if _depth.needs_subscribe(symbol):
        result = await _depth.subscribe_async(symbol)
        if not result["ok"]:
            await websocket.send_text(json.dumps(refusal_frame(symbol, result)))
            await websocket.close()
            return

    if _lane.ends_line(symbol):
        # A lane's Level 2 snapshots follow the lane (``line_lanes.lanes``); a replay slot's follow its sockets.
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
        # No await between: the sockets' registry and the viewer count move together.
        socket_token = _lane.opened(symbol, tab=tab, front=front, kind=_lane.DEPTH)

        # IBKR refused the line it was just asked for: no re-subscribe, the ladder's backoff asks again.
        if await send_refusal(websocket, symbol):
            return
        # Remount race: a previous viewer's cleanup may have dropped the line
        # between our initial subscribe check and viewer_opened. Re-subscribe
        # before streaming so the line actually exists to hold a viewer queue.
        if _depth.needs_subscribe(symbol):
            result = await _depth.subscribe_async(symbol)
            if not result["ok"]:
                await websocket.send_text(json.dumps(refusal_frame(symbol, result)))
                return
            if _lane.ends_line(symbol):
                try:
                    _l2_continuous.start(symbol)
                except Exception:
                    logger.exception("l2.continuous: failed to restart for WS %s", symbol)

        # Own queue per viewer -- a shared per-symbol queue makes concurrent
        # viewers (StrictMode double-mount, or a second Trader tab on the
        # same symbol) competing consumers instead of both seeing every book
        # update (same defect class as tape_stream.py -- PROBLEM_LOG 2026-08-25).
        queue = _depth.open_viewer_queue(symbol)
        if await send_refusal(websocket, symbol):  # refused before this queue could hear it
            return
        no_lane = _lanes.refusal(symbol)
        if no_lane is not None and not _depth.is_subscribed(symbol):
            # The lane left this stock while this socket subscribed: its frame went out before the queue existed.
            await websocket.send_text(json.dumps(refusal_frame(symbol, {"error": no_lane, "lane": True})))
            await websocket.close()
            return
        await websocket.send_text(json.dumps(
            {"type": "subscribed", "symbol": symbol, "instance": instance_identity.INSTANCE_ID}
        ))

        # A symbol already subscribed by another viewer (or a fresh page
        # reload re-attaching to a still-open depth line) needs today's
        # snapshot right away — see should_send_current_book().
        current = _depth.current_book(symbol)
        if _depth.should_send_current_book(current):
            version = book_version(symbol)
            await websocket.send_text(book_frame(
                symbol, BookVersion(version.seq if version else 0, version.at if version else 0.0, current)
            ))

        watch = _WatchFrames(symbol)
        luld = _LuldFrames(symbol)
        last_view = time.monotonic()  # the last book or beat: what tells the desk its book is current
        async for item in _depth.stream(queue, timeout=min(MARKET_VIEW_BEAT_SEC, BOOK_WATCH_PUSH_SEC)):
            mono = time.monotonic()
            verdicts = watch.due(mono)
            if verdicts is not None:
                await websocket.send_text(json.dumps({"type": "book_watch", "symbol": symbol, "data": verdicts}))
            bands = luld.due(mono)
            if bands is not None:
                await websocket.send_text(json.dumps({"type": "luld", "symbol": symbol, "data": bands}))
            if item is None:
                if mono - last_view >= MARKET_VIEW_BEAT_SEC:
                    await websocket.send_text(beat_frame(symbol))
                    last_view = mono
                continue
            if isinstance(item, BookVersion):
                await websocket.send_text(book_frame(symbol, item))
                last_view = mono
                continue
            if item.get("type") == "error":
                # Line torn down out from under this viewer -- tell the client, then close. ``lane``: its lane
                # left the stock (ADR 071), and the pane waits for the operator; otherwise its backoff reconnects
                # (PROBLEM_LOG 2026-08-25).
                frame = {"type": "error", "symbol": symbol, "message": item.get("message") or "Depth error"}
                if item.get("lane") is not None:
                    frame.update(evicted=True, lane=item["lane"])
                await websocket.send_text(json.dumps(frame))
                if item.get("evicted"):
                    await websocket.close()
                    break
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
        _lane.closed(symbol, socket_token, _lane.DEPTH)
        # A lane's line never ends here (ADR 071): only its lane leaving ends it. A line no lane is on (a Sim
        # replay slot) is released once the LAST viewer is gone, after a short grace so a remount can reattach.
        if viewer_opened and _depth.ws_viewer_closed(symbol) and _lane.ends_line(symbol):
            idle = await _depth.release_when_idle(symbol)
            if idle:
                try:
                    await _l2_continuous.stop(symbol)
                except Exception:
                    logger.exception("l2.continuous: failed to stop for WS %s", symbol)
                from l2 import recorder as _l2_recorder
                if not _l2_recorder.is_recording(symbol):
                    _depth.unsubscribe(symbol)
