"""The setup scanner's HTTP and socket surface (ADR 022, AGENTS.md section 3):
read-only routes over one engine, a 503 that names why the scoreboard is
closed, and a socket that opens with the board."""
from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

import setup_scanner.routes as routes
from setup_scanner.engine import SetupEngine
from setup_scanner.store import SetupStore
from tests.setup_scanner_fixtures import add, base_morning, leg_up
from tests.test_setup_scanner_engine import EYES, FP_ONLY, SYM, FakeTape


def _client(monkeypatch, tmp_path, *, store: bool = True):
    bars = add(leg_up(base_morning(), [4.08, 4.18, 4.28, 4.38]), 4.38, 4.37, 4.30, 4.32, 30_000)
    clock = {"t": bars[-1].t + 30}
    eng = SetupEngine(store=SetupStore(tmp_path / "setups.db") if store else None, tape=FakeTape(),
                      universe=lambda: [SYM], seed=lambda sym, since: list(bars),
                      replay_desk=lambda: False, audit=lambda **kw: None, clock=lambda: clock["t"],
                      levels=EYES, setups=FP_ONLY)
    asyncio.run(eng.tick(clock["t"]))
    monkeypatch.setattr(routes, "get_engine", lambda: eng)
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app), eng


def test_board_route_serves_the_armed_setup(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    body = client.get("/api/setups/board").json()
    assert body["schema_version"] == 2 and body["universe"] == 1
    row = body["rows"][0]
    assert row["symbol"] == SYM and row["state"] == "armed"
    assert row["setup"]["trigger"] == 4.37 and row["setup"]["stop"] == 4.30


def test_scoreboard_and_rows_read_the_store(monkeypatch, tmp_path):
    client, eng = _client(monkeypatch, tmp_path)
    body = client.get("/api/setups/scoreboard", params={"days": 0}).json()
    assert body["days"] == 0 and body["date_from"] is None
    assert body["row_count"] == 1 and body["summary"]["all"]["armed"] == 1
    assert set(body["summary"]["by"]) == {"tape_at_trigger", "flow_at_trigger", "grade", "session", "kind"}
    day = body["rows"][0]["session_date"]
    rows = client.get("/api/setups/rows", params={"date": day, "symbol": SYM.lower()}).json()["rows"]
    assert len(rows) == 1 and rows[0]["symbol"] == SYM
    assert client.get("/api/setups/rows", params={"date": "22-09-2026"}).status_code == 422


def test_scoreboard_says_why_it_is_closed(monkeypatch, tmp_path):
    client, eng = _client(monkeypatch, tmp_path, store=False)
    eng.store_error = "setups.db has user_version 9; this build reads 1"
    res = client.get("/api/setups/scoreboard")
    assert res.status_code == 503 and "user_version 9" in res.json()["detail"]
    assert client.get("/api/setups/board").json()["scoreboard_error"].startswith("setups.db")


def test_socket_opens_with_the_board(monkeypatch, tmp_path):
    client, eng = _client(monkeypatch, tmp_path)
    with client.websocket_connect("/ws/setups") as ws:
        frame = ws.receive_json()
        assert frame["type"] == "board" and frame["rows"][0]["symbol"] == SYM
        assert len(eng.clients) == 1
    assert len(eng.clients) == 0
