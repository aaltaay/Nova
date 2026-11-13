"""Time & Sales WebSocket -- extracted so trading.py stays under the line limit.

A Sim desk off the live edge skips IBKR subscribe and reads the same viewer
queues the feed injects; at the live edge (ADR 020 live-edge amendment) it
opens the real tape line exactly as a Paper or Live desk does.

The lanes hold every live line (ADR 071, ``line_lanes``): a socket opened in front (``front=1``) puts your lane on its
stock first; for a stock no lane is on a socket reads ``{"type": "lane", symbol, message, lane}`` and closes, and the
same frame comes when the lane leaves its stock. A socket closing never ends a lane's line.

A line IBKR refuses or ends while the socket stands (10190, its tick-by-tick cap,
arrives after the request) is brought back by ``line_lanes.tape_heal`` (#698):
the socket forwards its words and ``retry_at``, then ``subscribed`` when the line
is back. It used to stay open on a dead line until the tab was reopened.

Prints waiting together go as one ``{"type": "prints", "items": [...], "sent"}`` frame (a single
print stays a ``print`` frame), so a backlog after a stall reaches the pane at once (ADR 045).

Each idle ``ping`` (no print for TAPE_STREAM_HEARTBEAT_SEC) on a live line carries ``silence``:
``ibkr.tape_silence``'s reading, or ``null`` (#722). The pane says LINE DOWN, HALTED, SILENT or QUIET
with its words instead of reading LIVE over a tape that stopped.

Each ping also carries ``gate``: the order gate's own answer for the symbol now (``market_view.gate.desk_lock``,
``{code, text}`` or ``null``), and while prints flow a ``{"type": "gate", ...}`` frame goes out whenever
that answer changes (checked every MARKET_VIEW_GATE_SEND_SEC). The ticket locks with the words the door
would refuse with (ADR 045 amendment 2026-10-14, "one funnel").
"""
from __future__ import annotations

import json
import logging
import time

from fastapi import WebSocket, WebSocketDisconnect

from constants_market_view import FEED_STALE, MARKET_VIEW_GATE_SEND_SEC, VIEW_GATE_EXEMPT_TEXT
from ibkr import tape_silence
from ibkr import tape_stream as _tape
from line_lanes import lanes as _lanes
from line_lanes import sockets as _lane
from sim.mode import desk_connected, is_replay_desk

logger = logging.getLogger(__name__)


async def run_ws_tape(websocket: WebSocket, symbol: str) -> None:
    symbol = symbol.upper()
    await websocket.accept()
    tab, front = _lane.flags(websocket.query_params)

    if not desk_connected():
        await websocket.send_text(json.dumps({"type": "error", "message": "IBKR not connected"}))
        await websocket.close()
        return

    # In front: your lane goes to this stock now -- the old stock's lines end first (ADR 071).
    await _lane.opening(symbol, front=front)

    if not is_replay_desk() and not _tape.is_subscribed(symbol):
        result = await _tape.subscribe_async(symbol)
        if not result["ok"]:
            await websocket.send_text(json.dumps(_refused(symbol, result)))
            await websocket.close()
            return

    viewer_opened = False
    socket_token: int | None = None
    queue = None
    try:
        _tape.ws_viewer_opened(symbol)
        viewer_opened = True
        # No await between: the sockets' registry and the viewer count move together.
        socket_token = _lane.opened(symbol, tab=tab, front=front, kind=_lane.TAPE)

        if not is_replay_desk() and not _tape.is_subscribed(symbol):
            result = await _tape.subscribe_async(symbol)
            if not result["ok"]:
                await websocket.send_text(json.dumps(_refused(symbol, result)))
                return

        queue = _tape.open_viewer_queue(symbol)
        no_lane = None if is_replay_desk() else _lanes.refusal(symbol)
        if no_lane is not None:
            # The lane left this stock while this socket subscribed: its frame went out before the queue existed.
            await websocket.send_text(json.dumps(_refused(symbol, {"error": no_lane, "lane": True})))
            await websocket.close()
            return
        await websocket.send_text(json.dumps({"type": "subscribed", "symbol": symbol}))

        # Capture replay: seed recent prints so T&S is not empty until the feed catches up.
        try:
            from sim import replay as _replay
            from sim import capture_player as _player
            if (is_replay_desk() and _replay.is_capture_replay()
                    and _replay.status_payload().get("replay_symbol") == symbol):
                for row in _player.recent_prints(40):
                    await websocket.send_text(json.dumps({**row, "type": "print"}))
        except Exception:
            logger.debug("SIM tape: capture seed skipped", exc_info=True)

        halt_seen_at: float | None = None  # the last ping that found the symbol halted
        gate_sent: dict | None = None      # the order gate's answer the socket last sent
        gate_at = 0.0
        async for batch in _tape.stream_batches(queue):
            if batch is None:
                silence = None
                if not is_replay_desk() and _has_silence_watch(symbol):
                    silence = _silence(symbol, halt_seen_at)
                    if silence is not None and silence.get("halted") is True:
                        halt_seen_at = time.time()
                gate_sent, gate_at = _gate(symbol), time.time()
                await websocket.send_text(json.dumps({"type": "ping", "symbol": symbol, "silence": silence,
                                                      "gate": gate_sent}))
                if not is_replay_desk():
                    _lane.line_down(symbol, silence=silence)
                continue
            if not await _send_batch(websocket, symbol, batch):
                break
            if time.time() - gate_at >= MARKET_VIEW_GATE_SEND_SEC:
                gate, gate_at = _gate(symbol), time.time()
                if gate != gate_sent:
                    gate_sent = gate
                    await websocket.send_text(json.dumps({"type": "gate", "symbol": symbol, "gate": gate}))
    except WebSocketDisconnect:
        logger.debug("IBKR tape WS disconnected: %s", symbol)
    except Exception as exc:
        from ws_close_errors import is_websocket_send_after_close

        if is_websocket_send_after_close(exc):
            logger.debug("IBKR tape WS send-after-close: %s", symbol)
        else:
            logger.exception("IBKR tape WS error for %s: %s", symbol, exc)
    finally:
        if queue is not None:
            _tape.close_viewer_queue(symbol, queue)
        _lane.closed(symbol, socket_token, _lane.TAPE)
        if viewer_opened and _tape.ws_viewer_closed(symbol) and _lane.ends_line(symbol):
            # The last viewer of a line no lane is on left. A lane's line ends only when its lane leaves (ADR 071);
            # with no line this is a no-op, so a replay desk is unchanged.
            _tape.unsubscribe(symbol)


def _refused(symbol: str, result: dict) -> dict:
    """The frame for a subscribe that failed: the lanes' ``lane`` frame when no lane is on the stock (ADR 071)."""
    if result.get("lane"):
        return {"type": "lane", "symbol": symbol, "message": result.get("error"), "lane": _lanes.wire()}
    return {"type": "error", "message": result.get("error")}


async def _send_prints(websocket: WebSocket, symbol: str, prints: list[dict]) -> None:
    if len(prints) == 1:
        await websocket.send_text(json.dumps({**prints[0], "type": "print"}))
    elif prints:
        items = [{**p, "type": "print"} for p in prints]
        await websocket.send_text(json.dumps({"type": "prints", "symbol": symbol, "items": items, "sent": time.time()}))
    prints.clear()


async def _send_batch(websocket: WebSocket, symbol: str, batch: list[dict]) -> bool:
    """Send one batch in order: prints together, each control frame where it fell. False when the
    socket must close (the line was lent or released)."""
    prints: list[dict] = []
    for item in batch:
        if item.get("symbol") != symbol:
            continue
        msg_type = item.get("type") or "print"
        if msg_type == "print":
            prints.append(item)
            continue
        await _send_prints(websocket, symbol, prints)
        if msg_type == "lane":
            # Its lane left the stock (ADR 071): the pane waits for the operator, never by its backoff.
            await websocket.send_text(json.dumps(item))
            await websocket.close()
            return False
        if msg_type == "subscribed":
            # The line is back (``tape_heal``): the pane drops its error.
            await websocket.send_text(json.dumps({"type": "subscribed", "symbol": symbol}))
        elif msg_type == "error":
            frame = {
                "type": "error",
                "symbol": symbol,
                "message": item.get("message") or "Tape error",
                "retry_at": item.get("retry_at"),
            }
            if item.get("silent_recovery") is not None:
                frame["silent_recovery"] = item.get("silent_recovery")
            if item.get("silence_since") is not None:
                frame["silence_since"] = item.get("silence_since")
            await websocket.send_text(json.dumps(frame))
            if item.get("released"):
                await websocket.close()
                return False
            if not item.get("healing"):
                _lane.line_down(symbol)  # IBKR refused or ended it: ask again, never wait on a dead line
        elif msg_type == "scrub_reset":
            await websocket.send_text(json.dumps({"type": "scrub_reset", "symbol": symbol}))
        else:
            prints.append(item)
    await _send_prints(websocket, symbol, prints)
    return True


def _gate(symbol: str) -> dict | None:
    """The order gate's answer for the symbol now (``{code, text}``), or None while orders may go."""
    try:
        from market_view.gate import desk_lock

        return desk_lock(symbol)
    except Exception:
        logger.exception("IBKR tape WS: the order gate could not be read for %s", symbol)
        return {"code": FEED_STALE, "text": f"Nova could not check this stock's market right now. {VIEW_GATE_EXEMPT_TEXT}"}


def _has_silence_watch(symbol: str) -> bool:
    if _tape.is_subscribed(symbol):
        return True
    from line_lanes import tape_heal

    return tape_heal.unverified_reask(symbol) is not None


def _silence(symbol: str, halt_seen_at: float | None) -> dict | None:
    """The line's silence for the ping (memory only); None when it cannot be read."""
    try:
        from line_lanes import tape_heal

        reading = tape_silence.reading(symbol, halt_seen_at=halt_seen_at)
        recovery = tape_heal.silent_status(symbol)
        if reading is not None and recovery is not None:
            return {**reading, "recovery": recovery, "text": f"{reading['text']} {recovery['text']}"}
        return reading
    except Exception:
        logger.exception("IBKR tape WS: silence reading failed for %s", symbol)
        return None
