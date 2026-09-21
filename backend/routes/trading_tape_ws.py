"""Time & Sales WebSocket -- extracted so trading.py stays under the line limit.

A Sim desk off the live edge skips IBKR subscribe and reads the same viewer
queues the feed injects; at the live edge (ADR 020 live-edge amendment) it
opens the real tape line exactly as a Paper or Live desk does.
"""
from __future__ import annotations

import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from ibkr import tape_stream as _tape
from sim.mode import desk_connected, is_replay_desk

logger = logging.getLogger(__name__)


async def run_ws_tape(websocket: WebSocket, symbol: str) -> None:
    symbol = symbol.upper()
    await websocket.accept()

    if not desk_connected():
        await websocket.send_text(json.dumps({"type": "error", "message": "IBKR not connected"}))
        await websocket.close()
        return

    if not is_replay_desk() and not _tape.is_subscribed(symbol):
        result = await _tape.subscribe_async(symbol)
        if not result["ok"]:
            await websocket.send_text(json.dumps({"type": "error", "message": result["error"]}))
            await websocket.close()
            return

    viewer_opened = False
    queue = None
    try:
        _tape.ws_viewer_opened(symbol)
        viewer_opened = True

        if not is_replay_desk() and not _tape.is_subscribed(symbol):
            result = await _tape.subscribe_async(symbol)
            if not result["ok"]:
                await websocket.send_text(json.dumps({"type": "error", "message": result["error"]}))
                return

        queue = _tape.open_viewer_queue(symbol)
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
                continue
            if print_data.get("symbol") != symbol:
                continue
            msg_type = print_data.get("type") or "print"
            if msg_type == "error":
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "symbol": symbol,
                            "message": print_data.get("message") or "Tape error",
                        }
                    )
                )
                if print_data.get("released"):
                    await websocket.close()
                    break
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
        if viewer_opened and _tape.ws_viewer_closed(symbol):
            # The last viewer left: release the real line if one is open (a Sim
            # tab holds one at the live edge). With no line this is a no-op, so
            # a replay desk is unchanged.
            _tape.unsubscribe(symbol)
