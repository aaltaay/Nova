"""Time & Sales WebSocket -- extracted so trading.py stays under the line limit.

A Sim desk off the live edge skips IBKR subscribe and reads the same viewer
queues the feed injects; at the live edge (ADR 020 live-edge amendment) it
opens the real tape line exactly as a Paper or Live desk does.

A hidden Trader tab lends its AllLast line with its Level 2 line (ADR 044
decision 6, ``line_lending``): the Trader tab's Time & Sales opens with
``?tab=1`` and ``front=1`` while it is the tab in front. While a loan stands, a
socket for the lender gets ``{"type": "lent", ...}`` and closes; one from the tab
in front recalls the loan first. A standing socket whose line is lent reads the
same frame from its queue and closes.

A line IBKR refuses or ends while the socket stands (10190, its tick-by-tick cap,
arrives after the request) is brought back by ``line_lending.tape_heal`` (#698):
the socket forwards its words and ``retry_at``, then ``subscribed`` when the line
is back. It used to stay open on a dead line until the tab was reopened.
"""
from __future__ import annotations

import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from ibkr import tape_stream as _tape
from line_lending import socket_gate
from line_lending.sockets import TAPE
from sim.mode import desk_connected, is_replay_desk

logger = logging.getLogger(__name__)


async def run_ws_tape(websocket: WebSocket, symbol: str) -> None:
    symbol = symbol.upper()
    await websocket.accept()
    tab, front = socket_gate.flags(websocket.query_params)

    if not desk_connected():
        await websocket.send_text(json.dumps({"type": "error", "message": "IBKR not connected"}))
        await websocket.close()
        return

    # The line is lent (ADR 044): say so and close -- unless this is the tab in front, which recalled it.
    lent = await socket_gate.gate(symbol, front=front)
    if lent is not None:
        await websocket.send_text(json.dumps(lent))
        await websocket.close()
        return

    if not is_replay_desk() and not _tape.is_subscribed(symbol):
        result = await _tape.subscribe_async(symbol)
        if not result["ok"]:
            await websocket.send_text(json.dumps({"type": "error", "message": result["error"]}))
            await websocket.close()
            return

    viewer_opened = False
    socket_token: int | None = None
    queue = None
    try:
        _tape.ws_viewer_opened(symbol)
        viewer_opened = True
        # No await between: the lending registry and the viewer count move together.
        socket_token = socket_gate.opened(symbol, tab=tab, front=front, kind=TAPE)

        if not is_replay_desk() and not _tape.is_subscribed(symbol):
            result = await _tape.subscribe_async(symbol)
            if not result["ok"]:
                await websocket.send_text(json.dumps({"type": "error", "message": result["error"]}))
                return

        queue = _tape.open_viewer_queue(symbol)
        # A loan of this line that began while this socket subscribed pushed its frame before the queue existed.
        lent = socket_gate.lent_now(symbol, front=front)
        if lent is not None:
            await websocket.send_text(json.dumps(lent))
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

        async for print_data in _tape.stream(queue):
            if print_data is None:
                await websocket.send_text(json.dumps({"type": "ping", "symbol": symbol}))
                if not is_replay_desk() and not _tape.is_subscribed(symbol):
                    socket_gate.line_down(symbol)  # down with no word from IBKR: ask again all the same
                continue
            if print_data.get("symbol") != symbol:
                continue
            msg_type = print_data.get("type") or "print"
            if msg_type == "lent":
                # Lent to a setup (ADR 044): the tab waits for it to come back, never by its backoff.
                await websocket.send_text(json.dumps(print_data))
                await websocket.close()
                break
            if msg_type == "subscribed":
                # The line is back (``tape_heal``): the pane drops its error.
                await websocket.send_text(json.dumps({"type": "subscribed", "symbol": symbol}))
                continue
            if msg_type == "error":
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "symbol": symbol,
                            "message": print_data.get("message") or "Tape error",
                            "retry_at": print_data.get("retry_at"),
                        }
                    )
                )
                if print_data.get("released"):
                    await websocket.close()
                    break
                if not print_data.get("healing"):
                    socket_gate.line_down(symbol)  # IBKR refused or ended it: ask again, never wait on a dead line
            elif msg_type == "scrub_reset":
                await websocket.send_text(json.dumps({"type": "scrub_reset", "symbol": symbol}))
            else:
                await websocket.send_text(json.dumps({**print_data, "type": "print"}))
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
        socket_gate.closed(symbol, socket_token, TAPE)
        if viewer_opened and _tape.ws_viewer_closed(symbol):
            # The last viewer left: release the real line if one is open (a Sim
            # tab holds one at the live edge). With no line this is a no-op, so
            # a replay desk is unchanged.
            _tape.unsubscribe(symbol)
