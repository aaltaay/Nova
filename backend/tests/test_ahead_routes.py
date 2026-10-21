"""``/api/ahead/*`` (ADR 061): 422 only for a bad symbol, ``status`` is never a ticker, and a poll goes from
pending to ready on one running app."""
from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ahead import routes
from tests.test_ahead_service import desk  # noqa: F401 -- the faked desk and forecaster


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(routes.router)
    return app


def test_a_bad_symbol_is_422_with_the_reason(desk):  # noqa: F811
    with TestClient(_app()) as http:
        for bad in ("1ABC", "TOOLONGSYMBOL", "AB$C"):
            res = http.get(f"/api/ahead/forecast/{bad}")
            assert res.status_code == 422, bad
            assert res.json()["detail"]["reason"] == "AHEAD_BAD_SYMBOL"
    assert desk.forecasts == []


def test_status_is_never_read_as_a_symbol(desk):  # noqa: F811
    with TestClient(_app()) as http:
        res = http.get("/api/ahead/status")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"schema_version", "configured", "reason", "checked_at", "health"}
    assert desk.forecasts == []


def test_a_poll_goes_from_pending_to_ready(desk):  # noqa: F811
    with TestClient(_app()) as http:
        first = http.get("/api/ahead/forecast/xyz").json()
        assert first["symbol"] == "XYZ" and first["ai"]["state"] == "pending"
        deadline = time.monotonic() + 5
        while True:
            body = http.get("/api/ahead/forecast/XYZ").json()
            if body["ai"]["state"] != "pending" or time.monotonic() > deadline:
                break
            time.sleep(0.02)
    assert body["ai"]["state"] == "ready"
    assert len(desk.forecasts) == 1
    assert body["never"] == "A forecast only: nothing here places, blocks, sizes or delays an order."


def test_every_state_answers_200(desk, monkeypatch):  # noqa: F811
    with TestClient(_app()) as http:
        desk.bars = []
        assert http.get("/api/ahead/forecast/XYZ").json()["ai"]["state"] == "not_enough_bars"
        monkeypatch.delenv("NOVA_AHEAD_URL")
        res = http.get("/api/ahead/forecast/XYZ")
    assert res.status_code == 200
