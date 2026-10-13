"""The frames a Level 2 socket sends when IBKR refuses the line, shared with the desk's tests (2026-10-13).

The desk's test of exactly this case passed while the desk asked IBKR every 1.2 s: its fake socket sent
``error`` then a close, and the backend sends ``subscribed`` first (captured live, VLO 17:41 ET). This test
drives the real socket route and keeps its frames in ``frontend/src/ibkr/__fixtures__/depth_refused_frames.json``,
which ``useIbkrDepth.test.tsx`` replays. A change to what the backend sends fails here until the file is
written again (``NOVA_WRITE_WIRE_FIXTURES=1``), and then the desk's test runs on the new frames.
"""
from __future__ import annotations

import json
import os
import pathlib

FIXTURE = pathlib.Path(__file__).resolve().parents[2] / "frontend/src/ibkr/__fixtures__/depth_refused_frames.json"
WHY = ("IBKR refused this Level 2 (IB error 309): all 3 of its Level 2 lines are in use, and Nova holds none "
       "of them. The others are held inside IB Gateway; if this stays, restarting IB Gateway frees them. "
       "Asking again shortly.")


def _frames(monkeypatch) -> list[dict]:
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    import instance_identity
    from ibkr import depth as _depth
    from ibkr.depth import state as depth_state
    from l2 import continuous
    from main import app
    from routes import trading_depth_ws

    async def not_idle(_symbol):
        return False

    _depth.reset_all()
    monkeypatch.setattr(_depth, "needs_subscribe", lambda _s: False)  # the request went out; IBKR answers next
    monkeypatch.setattr(_depth, "release_when_idle", not_idle)
    monkeypatch.setattr(continuous, "start", lambda _s: None)
    monkeypatch.setattr(instance_identity, "INSTANCE_ID", "backend-instance")
    monkeypatch.setattr(trading_depth_ws._WatchFrames, "due", lambda self, mono: None)
    monkeypatch.setattr(trading_depth_ws._LuldFrames, "due", lambda self, mono: None)
    frames: list[dict] = []
    with TestClient(app).websocket_connect("/ws/ibkr/depth/VLO?tab=1&front=0") as ws:
        frames.append(ws.receive_json())
        depth_state.push_error("VLO", WHY, evicted=True)  # IBKR's 309, after the socket said subscribed
        try:
            while True:
                frames.append(ws.receive_json())
        except WebSocketDisconnect:
            frames.append({"closed": True})
    _depth.reset_all()
    return frames


def test_a_refused_level_2_socket_sends_subscribed_then_the_refusal_then_closes(monkeypatch):
    frames = _frames(monkeypatch)
    assert [f.get("type", "close") for f in frames] == ["subscribed", "error", "close"]
    if os.environ.get("NOVA_WRITE_WIRE_FIXTURES") == "1":
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps({"captured_from": "backend/tests/test_depth_wire_fixture.py",
                                       "frames": frames}, indent=2) + "\n", encoding="utf-8")
    assert json.loads(FIXTURE.read_text(encoding="utf-8"))["frames"] == frames, (
        "The depth socket's refusal frames changed: run with NOVA_WRITE_WIRE_FIXTURES=1 so the desk's tests replay them")
