"""Another device is view-only (ADR 070): the request guard refuses a write that did not
come straight from this PC, before the API key is read, and says why."""
from __future__ import annotations

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse

from request_guard import recent_refusals
from request_guard.constants_request_guard import REASON_REMOTE_LOCAL_ONLY, REASON_REMOTE_VIEW_ONLY
from request_guard.middleware import RequestGuardMiddleware
from request_guard.policy import load_policy

PHONE = "desk.tail1234.ts.net"


def _app(env: dict | None = None) -> FastAPI:
    app = FastAPI()

    @app.get("/api/read")
    def read() -> dict:
        return {"ok": True}

    @app.post("/api/ibkr/order")
    def order() -> dict:
        return {"sent": True}

    @app.delete("/api/ibkr/order/1")
    def cancel() -> dict:
        return {"sent": True}

    policy = load_policy({"NOVA_ALLOWED_HOSTS": PHONE, **(env or {})})[0]
    app.add_middleware(RequestGuardMiddleware, policy=policy)
    return app


def test_another_device_reads_but_its_writes_are_refused_with_why():
    client = TestClient(_app())
    assert client.get("/api/read", headers={"host": PHONE}).json() == {"ok": True}
    for res in (
        client.post("/api/ibkr/order", headers={"host": PHONE}),
        client.delete("/api/ibkr/order/1", headers={"host": PHONE}),
    ):
        assert res.status_code == 403
        assert res.json()["reason"] == REASON_REMOTE_VIEW_ONLY
        assert "view-only" in res.json()["detail"] and "Nothing was sent" in res.json()["detail"]


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:8000", "[::1]:8000", "127.0.0.2:8000"])
def test_the_desk_on_this_pc_still_writes(host):
    assert TestClient(_app()).post("/api/ibkr/order", headers={"host": host}).json() == {"sent": True}


@pytest.mark.parametrize("header", ["x-forwarded-for", "forwarded", "x-forwarded-host", "tailscale-user-login"])
def test_a_forwarded_write_is_another_device_even_under_a_loopback_host(header):
    # A tunnel that rewrote the Host to 127.0.0.1 must not turn a phone into the desk.
    res = TestClient(_app()).post("/api/ibkr/order", headers={"host": "127.0.0.1:8000", header: "x"})
    assert res.status_code == 403 and res.json()["reason"] == REASON_REMOTE_VIEW_ONLY


def test_a_forwarded_read_still_passes():
    res = TestClient(_app()).get("/api/read", headers={"host": PHONE, "x-forwarded-for": "100.64.0.2"})
    assert res.json() == {"ok": True}


def test_the_bind_host_is_this_pc_and_a_star_is_not():
    lan = TestClient(_app({"NOVA_API_HOST": "192.168.1.5"}))
    assert lan.post("/api/ibkr/order", headers={"host": "192.168.1.5:8000"}).json() == {"sent": True}
    star = TestClient(_app({"NOVA_ALLOWED_HOSTS": "*"}))
    assert star.post("/api/ibkr/order", headers={"host": "anything.example"}).status_code == 403


def test_a_refused_write_is_not_a_host_refusal_on_the_diagnostics_row():
    recent_refusals.reset_for_tests()
    TestClient(_app()).post("/api/ibkr/order", headers={"host": PHONE})
    assert recent_refusals.snapshot()["refusals"] == []


def _bot_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/bot/status")
    def status() -> dict:
        return {"ok": True}

    @app.get("/api/bots-are-not-a-prefix")
    def other() -> dict:
        return {"ok": True}

    @app.websocket("/ws/bot/eyes")
    async def eyes(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json({"type": "hello"})
        await websocket.close()

    app.add_middleware(RequestGuardMiddleware, policy=load_policy({"NOVA_ALLOWED_HOSTS": PHONE})[0])
    return app


def test_the_bot_and_agent_routes_answer_only_on_the_pc_reads_and_sockets_too():
    # Those routes trust a caller at 127.0.0.1, and that is where a tunnel on this PC calls from.
    client = TestClient(_bot_app())
    assert client.get("/api/bot/status", headers={"host": "127.0.0.1:8000"}).json() == {"ok": True}
    for headers in ({"host": PHONE}, {"host": "127.0.0.1:8000", "x-forwarded-for": "100.64.0.2"}):
        res = client.get("/api/bot/status", headers=headers)
        assert res.status_code == 403 and res.json()["reason"] == REASON_REMOTE_LOCAL_ONLY
        with pytest.raises(WebSocketDenialResponse) as denied:
            with client.websocket_connect("/ws/bot/eyes", headers=headers):
                pass
        assert denied.value.status_code == 403 and denied.value.json()["reason"] == REASON_REMOTE_LOCAL_ONLY
    assert client.get("/api/bots-are-not-a-prefix", headers={"host": PHONE}).json() == {"ok": True}
    with client.websocket_connect("/ws/bot/eyes", headers={"host": "127.0.0.1:8000"}) as ws:
        assert ws.receive_json() == {"type": "hello"}


def test_the_main_app_refuses_an_order_from_another_device(monkeypatch):
    from main import app

    guard = next(m for m in app.user_middleware if m.cls is RequestGuardMiddleware)
    monkeypatch.setitem(guard.kwargs, "policy", load_policy({"NOVA_ALLOWED_HOSTS": PHONE})[0])
    monkeypatch.setattr(app, "middleware_stack", None)
    try:
        res = TestClient(app).post("/api/ibkr/order", headers={"host": PHONE}, json={})
        assert res.status_code == 403 and res.json()["reason"] == REASON_REMOTE_VIEW_ONLY
    finally:
        app.middleware_stack = None  # the next test rebuilds the stack with the app's own policy
