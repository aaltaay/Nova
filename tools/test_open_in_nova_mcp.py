"""open_in_nova on the unified MCP server, and the review page's same-origin forwarder."""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nova_data_mcp as data  # noqa: E402
import nova_mcp  # noqa: E402
import nova_open_client as open_client  # noqa: E402
import nova_review_http as review_http  # noqa: E402

DAY = "2026-09-18"
CHAT = "Opened IMCC in Nova Sim on 2026-09-18 at 10:00:00 ET, paused."


def test_open_in_nova_returns_the_server_message_and_rejects_unknown_arguments():
    seen = []

    def transport(payload):
        seen.append(dict(payload))
        if payload.get("symbol") == "BAD":
            return {"ok": False, "reason": "BAD_REQUEST", "error": "symbol must be a ticker"}
        return {
            "ok": True, "chat_message": CHAT, "symbol": "IMCC", "date": DAY,
            "as_of": "10:00:00", "paused": True, "separate_sim": False,
        }

    server = nova_mcp.create_server(data.DataService(), http=False, warm=False, open_transport=transport)
    result = asyncio.run(server.call_tool("open_in_nova", {"symbol": "IMCC", "date": DAY, "as_of": "10:00"}))
    assert result.isError is False
    assert result.content[0].text == CHAT
    assert result.structuredContent["chat_message"] == CHAT
    assert seen == [{"symbol": "IMCC", "date": DAY, "as_of": "10:00"}]

    unknown = asyncio.run(server.call_tool("open_in_nova", {"symbol": "IMCC", "date": DAY, "tf": "1m"}))
    assert unknown.isError is True
    assert unknown.content[0].text.startswith("UNKNOWN_ARGUMENT tf")
    assert seen == [{"symbol": "IMCC", "date": DAY, "as_of": "10:00"}]

    bad = asyncio.run(server.call_tool("open_in_nova", {"symbol": "BAD", "date": DAY}))
    assert bad.isError is True
    assert bad.content[0].text.startswith("BAD_REQUEST")

    def down(_payload):
        raise OSError("connection refused")

    closed = nova_mcp.create_server(data.DataService(), http=False, warm=False, open_transport=down)
    failed = asyncio.run(closed.call_tool("open_in_nova", {"symbol": "IMCC", "date": DAY}))
    assert failed.isError is True
    assert failed.content[0].text == open_client.DESK_NOT_RUNNING_TEXT
    assert failed.structuredContent["error"]["code"] == "DESK_NOT_RUNNING"


class _Api(BaseHTTPRequestHandler):
    def log_message(self, _fmt, *_args):
        return

    def do_GET(self):  # noqa: N802
        if self.path.split("?", 1)[0] != "/api/agent/open-token":
            self.send_response(404)
            self.end_headers()
            return
        self._json(200, {"schema_version": 1, "token": "tok"})

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length)
        if self.headers.get("X-Nova-Open-Token") != "tok":
            self._json(401, {"detail": {"reason": "BAD_TOKEN", "error": "missing or wrong open token"}})
            return
        body = json.loads(raw.decode())
        assert body["symbol"] == "IMCC"
        self._json(200, {"ok": True, "chat_message": CHAT, "symbol": "IMCC", "date": DAY, "as_of": "10:00:00", "paused": True})

    def _json(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture
def review_and_api(monkeypatch):
    api = ThreadingHTTPServer(("127.0.0.1", 0), _Api)
    api_thread = threading.Thread(target=api.serve_forever, daemon=True)
    api_thread.start()
    monkeypatch.setenv("NOVA_API_BASE", f"http://127.0.0.1:{api.server_address[1]}")
    review = review_http.serve(0, bars_reader=lambda *_a: [], daily_reader=lambda *_a: [],
                               allowed_origins=("http://127.0.0.1:5173",))
    review_thread = threading.Thread(target=review.serve_forever, daemon=True)
    review_thread.start()
    yield review.server_address[1]
    review.shutdown()
    api.shutdown()


def _request(port, path, *, method="GET", body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def test_review_open_forwards_the_token_and_hides_it_from_other_origins(review_and_api):
    port = review_and_api
    status, headers, raw = _request(port, "/api/review/open-token")
    assert status == 200
    assert headers.get("Access-Control-Allow-Origin") is None
    assert json.loads(raw)["token"] == "tok"
    evil, evil_headers, evil_body = _request(port, "/api/review/open-token", headers={"Origin": "https://evil.example"})
    assert evil == 403
    assert evil_headers.get("Access-Control-Allow-Origin") is None
    assert b"tok" not in evil_body
    opened, opened_headers, opened_body = _request(
        port, "/api/review/open-in-nova", method="POST",
        body={"symbol": "IMCC", "date": DAY, "as_of": "10:00"},
        headers={"Content-Type": "application/json", "X-Nova-Open-Token": "tok", "Origin": "http://127.0.0.1:5173"},
    )
    assert opened == 200
    assert opened_headers.get("Access-Control-Allow-Origin") is None
    assert json.loads(opened_body)["chat_message"] == CHAT
    plain, _, _ = _request(
        port, "/api/review/open-in-nova", method="POST", body={"symbol": "IMCC"},
        headers={"Content-Type": "text/plain", "X-Nova-Open-Token": "tok"},
    )
    assert plain == 415


def test_review_open_says_when_the_desk_is_not_running(monkeypatch):
    monkeypatch.setenv("NOVA_API_BASE", "http://127.0.0.1:9")
    review = review_http.serve(0, bars_reader=lambda *_a: [], daily_reader=lambda *_a: [])
    thread = threading.Thread(target=review.serve_forever, daemon=True)
    thread.start()
    try:
        status, headers, raw = _request(review.server_address[1], "/api/review/open-token")
    finally:
        review.shutdown()
    assert status == 409
    assert headers.get("Access-Control-Allow-Origin") is None
    assert b"Run Nova Desktop.bat" in raw
