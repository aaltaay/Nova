"""The request guard (backend/request_guard/): the API answers only to its own Host
names, and a WebSocket from a foreign web page is refused before it opens -- each
refusal saying why, and logged once per value, not once per attempt."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse

from auth import MutatingApiKeyMiddleware
from constants import CORS_ALLOWED_ORIGINS_DEFAULT
from metrics import op_metrics
from metrics.http_middleware import HttpOperationMetricsMiddleware
from request_guard import configure_request_guard
from request_guard.constants_request_guard import (
    REASON_HOST_NOT_ALLOWED,
    REASON_ORIGIN_NOT_ALLOWED,
    WS_CLOSE_REASON_HOST,
    WS_CLOSE_REASON_ORIGIN,
)
from request_guard.middleware import RefusalLog, RequestGuardMiddleware
from request_guard.policy import Refusal, check_request, cors_origins, host_allowed, host_name, load_policy

DEFAULT = load_policy({})[0]
VITE = "http://127.0.0.1:5173"


# ── host_name / host_allowed ────────────────────────────────────────────────


@pytest.mark.parametrize(("raw", "name"), [
    ("127.0.0.1:8000", "127.0.0.1"),
    ("127.0.0.1", "127.0.0.1"),
    ("LOCALHOST:8000", "localhost"),
    ("localhost.:8000", "localhost"),
    ("localhost.", "localhost"),
    ("[::1]:8000", "::1"),
    ("[::1]", "::1"),
    ("[0:0::1]:8000", "::1"),
    (" Evil.Example:8000 ", "evil.example"),
])
def test_host_name_reads_the_name_out_of_a_host_header(raw, name):
    assert host_name(raw) == name


@pytest.mark.parametrize("raw", [
    None, "", "   ", "localhost:abc", "localhost:", "localhost:123456", "::1", "a b", "user@host",
    "host/path", "[::1", "[::1]x", "[::1]:", "[localhost]:8000", "x" * 300, "localhost:8000\r\nX: y",
])
def test_host_name_refuses_what_is_not_a_host_header(raw):
    assert host_name(raw) is None


@pytest.mark.parametrize("raw", [
    "127.0.0.1:8000", "127.0.0.1", "localhost:8000", "localhost", "LOCALHOST:8000", "LocalHost.:8000",
    "localhost.", "[::1]:8000", "[::1]", "127.0.0.2:8000", "127.255.255.254",
])
def test_loopback_names_pass_with_or_without_a_port(raw):
    assert host_allowed(DEFAULT, host_name(raw))


@pytest.mark.parametrize("raw", [
    "evil.example:8000", "127.0.0.1.evil.example", "localhost.evil.example:8000", "evil-localhost",
    "0.0.0.0:8000", "192.168.1.5:8000", "[::]:8000", "testserver", "",
])
def test_other_names_are_refused(raw):
    assert not host_allowed(DEFAULT, host_name(raw))


# ── load_policy ─────────────────────────────────────────────────────────────


def test_the_default_policy_is_loopback_names_and_the_desk_origins():
    policy, warnings = load_policy({})
    assert policy.hosts == {"127.0.0.1", "localhost", "::1"}
    assert policy.ws_origins == {"http://localhost:5173", "http://127.0.0.1:5173", "file://"}
    assert not policy.any_host and warnings == []


def test_a_named_bind_host_is_allowed_and_a_wildcard_says_what_to_set():
    assert "192.168.1.5" in load_policy({"NOVA_API_HOST": "192.168.1.5"})[0].hosts
    for wildcard in ("0.0.0.0", "::", ""):
        policy, warnings = load_policy({"NOVA_API_HOST": wildcard})
        assert policy.hosts == {"127.0.0.1", "localhost", "::1"}
        assert len(warnings) == 1 and "NOVA_ALLOWED_HOSTS" in warnings[0]


def test_allowed_hosts_are_normalized_and_bad_entries_are_named():
    policy, warnings = load_policy({"NOVA_ALLOWED_HOSTS": " Desk-PC.,desk-pc.lan:8000 , fe80::5,http://x:1"})
    assert {"desk-pc", "desk-pc.lan", "fe80::5"} <= policy.hosts
    assert host_allowed(policy, host_name("DESK-PC:8000"))
    assert host_allowed(policy, host_name("[FE80::5]:8000"))
    assert warnings == ["NOVA_ALLOWED_HOSTS entry 'http://x:1' is not a host name and was ignored"]


def test_a_star_opens_every_host_name_and_warns():
    policy, warnings = load_policy({"NOVA_ALLOWED_HOSTS": "*"})
    assert policy.any_host and host_allowed(policy, host_name("evil.example:8000"))
    assert any("DNS rebinding" in w for w in warnings)


def test_sockets_read_the_cors_list_but_never_null_or_star():
    env = {"NOVA_CORS_ALLOWED_ORIGINS": "*, null ,HTTP://X:1"}
    policy, warnings = load_policy(env)
    assert "*" not in policy.ws_origins and "null" not in policy.ws_origins
    assert {"http://x:1", "file://"} <= policy.ws_origins
    assert len(warnings) == 1 and "'*'" in warnings[0] and "'null'" in warnings[0]
    assert cors_origins(env) == ["*", "null", "HTTP://X:1"]
    assert cors_origins({}) == CORS_ALLOWED_ORIGINS_DEFAULT
    policy, warnings = load_policy({"NOVA_CORS_ALLOWED_ORIGINS": "null,https://my-ui.example"})
    assert policy.ws_origins == {"https://my-ui.example", "file://"}
    assert len(warnings) == 1 and "'null'" in warnings[0] and "Vite" not in warnings[0]


def test_a_star_cors_list_keeps_the_vite_sockets_and_no_other_page():
    # CORS '*' lets the browser desk's fetches through, so its sockets must open too;
    # '*' never stands for "any page" on a socket.
    policy, warnings = load_policy({"NOVA_CORS_ALLOWED_ORIGINS": "*"})
    assert policy.ws_origins == {"http://localhost:5173", "http://127.0.0.1:5173", "file://"}
    assert len(warnings) == 1 and "local Vite origins" in warnings[0]
    ok = ["127.0.0.1:8000"]
    for desk in (VITE, "http://localhost:5173", "file://"):
        assert check_request(policy, "websocket", ok, [desk]) is None
    for bad in ("https://evil.example", "null", "*"):
        assert check_request(policy, "websocket", ok, [bad]).reason == REASON_ORIGIN_NOT_ALLOWED


# ── check_request ───────────────────────────────────────────────────────────


def test_http_needs_one_allowed_host_and_leaves_origin_to_cors():
    # The packaged desk's fetches send no Origin; a foreign page's are CORS's to stop.
    assert check_request(DEFAULT, "http", ["127.0.0.1:8000"], ["https://evil.example"]) is None
    assert check_request(DEFAULT, "http", [], []) == Refusal("Host", "", REASON_HOST_NOT_ALLOWED)
    dup = check_request(DEFAULT, "http", ["127.0.0.1:8000", "evil.example"], [])
    assert dup == Refusal("Host", "127.0.0.1:8000, evil.example", REASON_HOST_NOT_ALLOWED)


def test_a_socket_needs_an_allowed_origin_or_none():
    ok = ["127.0.0.1:8000"]
    assert check_request(DEFAULT, "websocket", ok, []) is None
    assert check_request(DEFAULT, "websocket", ok, ["file://"]) is None
    assert check_request(DEFAULT, "websocket", ok, ["HTTP://LOCALHOST:5173"]) is None
    for bad in ("null", "https://evil.example", "https://nova.altaystudio.com", "file:", "http://127.0.0.1:5173/"):
        assert check_request(DEFAULT, "websocket", ok, [bad]).reason == REASON_ORIGIN_NOT_ALLOWED
    assert check_request(DEFAULT, "websocket", ok, [VITE, VITE]).reason == REASON_ORIGIN_NOT_ALLOWED
    # A rebound socket carries the attacker's name: the Host check refuses it first.
    assert check_request(DEFAULT, "websocket", ["evil.example:8000"], [VITE]).header == "Host"


# ── the middleware on a small app ───────────────────────────────────────────


def _app(lifespan=None) -> FastAPI:
    app = FastAPI(lifespan=lifespan)

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    @app.websocket("/ws/echo")
    async def echo(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json({"type": "hello"})
        await websocket.close()

    app.add_middleware(RequestGuardMiddleware, policy=load_policy({"NOVA_ALLOWED_HOSTS": "testserver"})[0])
    return app


def test_a_foreign_host_gets_400_with_the_reason_and_no_echo():
    res = TestClient(_app()).get("/ping", headers={"host": "evil.example:8000"})
    assert res.status_code == 400
    assert res.json()["reason"] == REASON_HOST_NOT_ALLOWED
    assert "NOVA_ALLOWED_HOSTS" in res.json()["detail"] and "evil" not in res.text


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:8000", "LOCALHOST.:8000", "[::1]:8000", "[::1]"])
def test_loopback_hosts_reach_the_route(host):
    assert TestClient(_app()).get("/ping", headers={"host": host}).json() == {"ok": True}


def _denied(client: TestClient, **kwargs) -> WebSocketDenialResponse:
    with pytest.raises(WebSocketDenialResponse) as denied:
        with client.websocket_connect("/ws/echo", **kwargs):
            pass
    return denied.value


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "https://nova.altaystudio.com"])
def test_a_socket_from_a_foreign_page_is_refused_with_the_reason(origin):
    denied = _denied(TestClient(_app()), headers={"origin": origin})
    assert denied.status_code == 403
    assert denied.json()["reason"] == REASON_ORIGIN_NOT_ALLOWED
    assert "NOVA_CORS_ALLOWED_ORIGINS" in denied.json()["detail"]


@pytest.mark.parametrize("headers", [{"origin": "http://localhost:5173"}, {"origin": VITE}, {"origin": "file://"}, {}])
def test_a_socket_from_the_desk_or_a_non_browser_opens(headers):
    with TestClient(_app()).websocket_connect("/ws/echo", headers=headers) as ws:
        assert ws.receive_json() == {"type": "hello"}


def test_a_socket_with_a_foreign_host_or_two_origins_is_refused():
    client = TestClient(_app())
    assert _denied(client, headers={"host": "evil.example"}).json()["reason"] == REASON_HOST_NOT_ALLOWED
    two = _denied(client, headers=httpx.Headers([("origin", VITE), ("origin", VITE)]))
    assert two.json()["reason"] == REASON_ORIGIN_NOT_ALLOWED


@pytest.mark.parametrize(("headers", "reason"), [
    ([(b"host", b"127.0.0.1:8000"), (b"origin", b"https://evil.example")], WS_CLOSE_REASON_ORIGIN),
    ([(b"host", b"evil.example:8000")], WS_CLOSE_REASON_HOST),
])
def test_without_the_http_answer_extension_a_socket_closes_1008_with_why(headers, reason):
    sent: list[dict] = []

    async def inner(scope, receive, send):
        raise AssertionError("a refused socket never reaches the route")

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        sent.append(message)

    guard = RequestGuardMiddleware(inner, DEFAULT)
    asyncio.run(guard({"type": "websocket", "path": "/ws/x", "headers": headers}, receive, send))
    assert sent == [{"type": "websocket.close", "code": 1008, "reason": reason}]
    assert len(reason.encode()) <= 123


def test_the_lifespan_passes_through():
    ran: list[str] = []

    @asynccontextmanager
    async def lifespan(app):
        ran.append("start")
        yield
        ran.append("stop")

    with TestClient(_app(lifespan)):
        pass
    assert ran == ["start", "stop"]


# ── the refusal log ─────────────────────────────────────────────────────────


def _warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "request_guard.middleware"]


def test_one_warning_per_refused_value_through_the_middleware(caplog):
    client = TestClient(_app())
    with caplog.at_level(logging.WARNING, logger="request_guard.middleware"):
        for _ in range(3):
            assert client.get("/ping", headers={"host": "evil.example:8000"}).status_code == 400
    lines = _warnings(caplog)
    assert len(lines) == 1
    assert repr("evil.example:8000") in lines[0] and "'/ping'" in lines[0]


def test_the_next_window_counts_the_refusals_it_did_not_log(caplog):
    clock = {"t": 0.0}
    log = RefusalLog(window_sec=60, clock=lambda: clock["t"])
    refusal = Refusal("Origin", "https://evil.example", REASON_ORIGIN_NOT_ALLOWED)
    with caplog.at_level(logging.WARNING, logger="request_guard.middleware"):
        for _ in range(4):
            log.note("websocket", "/ws/setups", refusal)
        clock["t"] = 61.0
        log.note("websocket", "/ws/setups", refusal)
    lines = _warnings(caplog)
    assert len(lines) == 2
    assert "more since" not in lines[0] and "; 3 more since " in lines[1]


def test_the_log_escapes_line_breaks_and_its_memory_is_capped(caplog):
    log = RefusalLog(keys_max=2)
    with caplog.at_level(logging.WARNING, logger="request_guard.middleware"):
        for value in ("a\r\nFORGED LINE", "b", "c"):
            log.note("http", "/x", Refusal("Host", value, REASON_HOST_NOT_ALLOWED))
    lines = _warnings(caplog)
    assert len(lines) == 3 and "\n" not in lines[0] and "\\r\\n" in lines[0]
    assert len(log._seen) <= 2


def test_configure_logs_what_it_allows(caplog):
    with caplog.at_level(logging.INFO, logger="request_guard"):
        policy = configure_request_guard(FastAPI(), {"NOVA_API_HOST": "0.0.0.0"})
    assert policy == load_policy({"NOVA_API_HOST": "0.0.0.0"})[0]
    messages = [r.getMessage() for r in caplog.records if r.name == "request_guard"]
    assert any("file://" in m and "localhost" in m for m in messages)
    assert any(r.levelno == logging.WARNING and "NOVA_ALLOWED_HOSTS" in r.getMessage() for r in caplog.records)


# ── the real app (main.app) ─────────────────────────────────────────────────


@pytest.fixture
def main_app():
    from main import app

    return app


def test_the_guard_sits_inside_cors_and_timing_and_outside_the_api_key(main_app):
    assert [m.cls for m in main_app.user_middleware] == [
        CORSMiddleware, HttpOperationMetricsMiddleware, RequestGuardMiddleware, MutatingApiKeyMiddleware,
    ]


def test_main_app_answers_its_names_and_refuses_others(main_app):
    client = TestClient(main_app)
    assert client.get("/api/health").status_code == 200  # Host "testserver", allowed by conftest
    for host in ("LOCALHOST.:8000", "[::1]:8000", "127.0.0.1:8000"):
        assert client.get("/api/health", headers={"host": host}).status_code == 200
    refused = client.get("/api/health", headers={"host": "evil.example:8000"})
    assert refused.status_code == 400 and refused.json()["reason"] == REASON_HOST_NOT_ALLOWED


def test_a_refusal_carries_cors_so_the_desk_can_read_why_and_counts_as_a_failure(main_app):
    op_metrics.reset_for_tests()
    try:
        res = TestClient(main_app).get("/api/health", headers={"host": "evil.example:8000", "origin": VITE})
        assert res.status_code == 400
        assert res.headers["access-control-allow-origin"] == VITE
        assert op_metrics.snapshot()["operations"]["http.GET.unmatched"]["error_count"] == 1
    finally:
        op_metrics.reset_for_tests()


class _Engine:
    def __init__(self) -> None:
        self.clients: set = set()

    def board(self) -> dict:
        return {"rows": []}


def test_main_app_sockets_take_the_desk_and_refuse_a_foreign_page(main_app, monkeypatch):
    import setup_scanner.routes as setup_routes

    monkeypatch.setattr(setup_routes, "get_engine", lambda: _Engine())
    client = TestClient(main_app)
    for origin in ("file://", VITE):
        with client.websocket_connect("/ws/setups", headers={"origin": origin}) as ws:
            assert ws.receive_json()["type"] == "board"
    with pytest.raises(WebSocketDenialResponse) as denied:
        with client.websocket_connect("/ws/setups", headers={"origin": "https://evil.example"}):
            pass
    assert denied.value.status_code == 403
    assert denied.value.json()["reason"] == REASON_ORIGIN_NOT_ALLOWED
