"""Open in Nova: strict arguments, the install token, and a separate Sim window during regular hours.

The request queues the existing ``show`` command. The desk's show landing calls ``jump_to_day`` and
``scrub_to_second``. This route does not. It does not call the order path or ``leave_safely``.
``POST /api/agent/show`` stays on the API key.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from agent_desk import commands
from agent_desk.open_in_nova import (
    DESK_NOT_RUNNING_TEXT,
    OpenError,
    chat_message,
    foreign_origin,
    in_rth,
    parse_payload,
    park_before_setup,
    perform,
    second_from_open,
    switch_main_view_to_sim,
)
from agent_desk.open_token import TokenError, load_or_create, token_path
from main import app

ET = ZoneInfo("America/New_York")
client = TestClient(app)
DAY = "2026-09-18"
HEADER = "X-Nova-Open-Token"
WEEKDAY = datetime(2026, 10, 20, 20, 0, tzinfo=ET)  # Tuesday 20:00 ET, after the close
RTH = datetime(2026, 10, 20, 10, 0, tzinfo=ET)
OPEN_BELL = datetime(2026, 10, 20, 9, 30, tzinfo=ET)
CLOSE_BELL = datetime(2026, 10, 20, 16, 0, tzinfo=ET)


def _weekday(day: date) -> bool:
    return day.weekday() < 5


def _boom(*_args, **_kwargs):
    raise AssertionError("an order path was called")


@pytest.fixture
def calls(monkeypatch):
    jumped: list[str] = []
    scrubbed: list[float] = []
    switched: list[list] = []
    monkeypatch.setattr("sim.day_jump.jump_to_day", lambda day: jumped.append(day))
    monkeypatch.setattr("sim.session_clock.scrub_to_second", lambda second, notify=True: scrubbed.append(second))
    monkeypatch.setattr("agent_desk.open_in_nova._venue", lambda: "live")
    monkeypatch.setattr("agent_desk.open_in_nova.switch_main_view_to_sim", lambda: switched.append(["direct"]))
    return {"jumped": jumped, "scrubbed": scrubbed, "switched": switched}


@pytest.fixture
def board(monkeypatch):
    fresh = commands.CommandBoard(now=lambda: 1_000_000.0)
    fresh._last_poll = 1_000_000.0
    monkeypatch.setattr(commands, "BOARD", fresh)
    return fresh


def _open(body, now=WEEKDAY, **kwargs):
    return perform(
        body,
        now=now,
        listening=kwargs.pop("listening", lambda: True),
        trading_day=kwargs.pop("trading_day", _weekday),
        setups_for=kwargs.pop("setups_for", lambda *_a: []),
        row_for=kwargs.pop("row_for", lambda *_a: None),
        on_file=kwargs.pop("on_file", lambda _day: True),
        **kwargs,
    )


def test_arguments_reject_unknown_keys_and_bad_values():
    with pytest.raises(OpenError) as unknown:
        parse_payload({"symbol": "IMCC", "date": DAY, "nope": 1})
    assert unknown.value.reason == "UNKNOWN_ARGUMENT" and unknown.value.error == "nope"
    for body in (
        {"date": DAY},
        {"symbol": "IMCC"},
        {"symbol": 1, "date": DAY},
        {"symbol": "1IMCC", "date": DAY},
        {"symbol": "TOOLONGNAME", "date": DAY},
        {"symbol": "IMCC", "date": "18-09-2026"},
        {"symbol": "IMCC", "date": DAY, "as_of": "25:00"},
        {"symbol": "IMCC", "date": DAY, "as_of": "03:59:00"},
        {"symbol": "IMCC", "date": DAY, "as_of": "20:00:01"},
        [],
    ):
        with pytest.raises(OpenError) as bad:
            parse_payload(body)
        assert bad.value.reason == "BAD_REQUEST"
    parsed = parse_payload({"symbol": "imcc", "date": DAY, "as_of": "10:00"})
    assert parsed == {"symbol": "IMCC", "date": DAY, "as_of": "10:00:00"}
    assert parse_payload({"symbol": "BRK.B", "date": DAY, "as_of": "20:00:00"})["as_of"] == "20:00:00"


def test_rth_opens_a_separate_window_and_does_not_jump(calls):
    result = _open({"symbol": "IMCC", "date": DAY, "as_of": "10:00"}, now=RTH)
    assert result["separate_sim"] is True
    assert result["chat_message"] == chat_message("IMCC", DAY, "10:00:00", separate=True)
    assert "The live desk stayed on its own view." in result["chat_message"]
    assert calls["jumped"] == [] and calls["scrubbed"] == [] and calls["switched"] == []
    assert result["command"]["plan"]["symbol"] == "IMCC"
    assert result["command"]["plan"]["switch_venue"] is False
    assert result["command"]["plan"]["separate_sim"] is True
    assert result["paused"] is True
    assert _open({"symbol": "IMCC", "date": DAY, "as_of": "10:00"}, now=OPEN_BELL)["separate_sim"] is True


def test_outside_rth_jumps_and_scrubs_without_touching_orders(calls, monkeypatch):
    monkeypatch.setattr("ibkr.orders.place_order", _boom)
    monkeypatch.setattr("ibkr.orders.cancel_order", _boom)
    monkeypatch.setattr("execution.service.execute", _boom)
    monkeypatch.setattr("stock_mode.leave.leave_safely", _boom)
    monkeypatch.setattr("stock_mode.leave.leave_sync", _boom)
    result = _open({"symbol": "IMCC", "date": DAY, "as_of": "10:00:00"}, now=WEEKDAY)
    assert result["separate_sim"] is False
    assert result["chat_message"] == "Opened IMCC in Nova Sim on 2026-09-18 at 10:00:00 ET, paused."
    # The desk's existing show landing is what calls jump_to_day and scrub_to_second.
    assert calls["jumped"] == [] and calls["scrubbed"] == []
    assert second_from_open(DAY, result["command"]["plan"]["park_ts"]) == 6 * 3600
    assert calls["switched"] == [["direct"]]
    assert result["command"]["plan"]["switch_view"] is True
    assert result["command"]["plan"]["switch_venue"] is False
    assert result["command"]["kind"] == "show"
    close = _open({"symbol": "IMCC", "date": DAY, "as_of": "10:00"}, now=CLOSE_BELL)
    assert close["separate_sim"] is False
    saturday = datetime(2026, 10, 17, 10, 0, tzinfo=ET)
    assert in_rth(saturday, _weekday) is False


def test_seconds_and_the_setup_lead(calls):
    seconds = _open({"symbol": "IMCC", "date": DAY, "as_of": "10:00:30"}, now=WEEKDAY)
    assert second_from_open(DAY, seconds["command"]["plan"]["park_ts"]) == 6 * 3600 + 30
    assert calls["jumped"] == [] and calls["scrubbed"] == []
    setups = [{"kind": "flat_top", "time": "2026-09-18T10:05:00-04:00", "price": 1, "label": "flat top"}]
    led = _open({"symbol": "IMCC", "date": DAY}, now=WEEKDAY, setups_for=lambda *_a: setups)
    assert led["as_of"] == "10:03:00"
    early = park_before_setup(DAY, [{"time": "2026-09-18T04:01:00-04:00"}])
    assert second_from_open(DAY, early) == 0


def test_a_closed_desk_does_not_jump(calls):
    with pytest.raises(OpenError) as closed:
        _open({"symbol": "IMCC", "date": DAY, "as_of": "10:00"}, listening=lambda: False)
    assert closed.value.reason == "DESK_NOT_RUNNING"
    assert closed.value.error == DESK_NOT_RUNNING_TEXT
    assert calls["jumped"] == [] and calls["switched"] == []


def test_switch_view_passes_an_empty_left_list(monkeypatch):
    seen = {}
    monkeypatch.setattr("sim.mode.venue", lambda: "live")

    def set_venue(target, persist=True, left=None):
        seen["target"] = target
        seen["left"] = left
        return {}

    monkeypatch.setattr("sim.mode.set_venue", set_venue)
    monkeypatch.setattr("stock_mode.leave.leave_sync", _boom)
    monkeypatch.setattr("stock_mode.leave.leave_safely", _boom)
    switch_main_view_to_sim()
    assert seen == {"target": "sim", "left": []}


def test_token_file_is_private_and_an_unknown_schema_refuses(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    first = load_or_create()
    assert load_or_create()["token"] == first["token"]
    assert token_path().stat().st_mode & 0o777 == 0o600
    token_path().write_text(json.dumps({"schema_version": 2, "token": "x"}), encoding="utf-8")
    with pytest.raises(TokenError, match="schema"):
        load_or_create()


def test_origin_rules():
    assert foreign_origin(None) is False
    assert foreign_origin("file://") is False
    assert foreign_origin("http://127.0.0.1:5173") is False
    assert foreign_origin("http://localhost:5173") is False
    assert foreign_origin("null") is True
    assert foreign_origin("https://evil.example") is True


@pytest.fixture
def http(monkeypatch, calls, board):
    monkeypatch.setenv("NOVA_API_KEY", "agent-test-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    monkeypatch.setattr("agent_desk.open_in_nova.wall_clock", lambda: WEEKDAY)
    monkeypatch.setattr("agent_desk.open_in_nova._trading_day", _weekday)
    monkeypatch.setattr("agent_desk.open_in_nova._setups_for", lambda *_a: [])
    monkeypatch.setattr("agent_desk.open_in_nova._row_for", lambda *_a: None)
    monkeypatch.setattr("agent_desk.open_in_nova._on_file", lambda _day: True)
    token = load_or_create()["token"]
    return {"token": token, "board": board}


def _post(body, headers):
    return client.post("/api/agent/open-in-nova", content=json.dumps(body), headers=headers)


def test_http_rejects_token_origin_and_content_type_and_accepts_the_token_without_the_api_key(http, calls):
    token = http["token"]
    missing = _post({"symbol": "IMCC", "date": DAY, "as_of": "10:00"}, {"Content-Type": "application/json"})
    assert missing.status_code == 401 and missing.json()["detail"]["reason"] == "BAD_TOKEN"
    wrong = _post({"symbol": "IMCC", "date": DAY, "as_of": "10:00"},
                  {"Content-Type": "application/json", HEADER: "nope"})
    assert wrong.status_code == 401
    foreign = _post(
        {"symbol": "IMCC", "date": DAY, "as_of": "10:00"},
        {"Content-Type": "application/json", HEADER: token, "Origin": "https://evil.example"},
    )
    assert foreign.status_code == 403 and foreign.json()["detail"]["reason"] == "FORBIDDEN"
    assert "Access-Control-Allow-Origin" not in foreign.headers or foreign.headers.get("access-control-allow-origin") != "*"
    plain = _post({"symbol": "IMCC", "date": DAY}, {"Content-Type": "text/plain", HEADER: token})
    assert plain.status_code == 415 and plain.json()["detail"]["reason"] == "BAD_REQUEST"
    bad = _post({"symbol": "IMCC", "date": DAY, "extra": 1}, {"Content-Type": "application/json", HEADER: token})
    assert bad.status_code == 400 and bad.json()["detail"]["reason"] == "UNKNOWN_ARGUMENT"
    ok = _post(
        {"symbol": "IMCC", "date": DAY, "as_of": "10:00"},
        {"Content-Type": "application/json; charset=utf-8", HEADER: token, "Origin": "http://127.0.0.1:5173"},
    )
    assert ok.status_code == 200
    assert ok.json()["chat_message"] == "Opened IMCC in Nova Sim on 2026-09-18 at 10:00:00 ET, paused."
    assert ok.json()["command"]["kind"] == "show"
    assert calls["jumped"] == [] and calls["scrubbed"] == []
    token_get = client.get("/api/agent/open-token")
    assert token_get.status_code == 200 and token_get.json()["token"] == token
    leaked = client.get("/api/agent/open-token", headers={"Origin": "https://evil.example"})
    assert leaked.status_code == 403 and "token" not in leaked.text
