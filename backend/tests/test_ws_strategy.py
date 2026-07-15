"""WebSocket contract test for /ws/strategy (backend/routes/hod_momo.py).

Nova OS decision broadcasts ride this socket (strategy/setups_stream.py's
_broadcast). This just pins the initial-payload contract the frontend
depends on — connect, get one `type: "initial"` message with a `signals`
list — so a refactor of the handshake can't silently drop a field.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_ws_strategy_sends_initial_payload_contract():
    with client.websocket_connect("/ws/strategy") as ws:
        msg = ws.receive_json()
    assert msg["type"] == "initial"
    assert "note" in msg
    assert isinstance(msg["signals"], list)
