"""Open in Nova: strict arguments, the install token, and a separate Sim window during regular hours.

The request queues the existing ``show`` command. The desk's show landing calls ``jump_to_day`` and
``scrub_to_second``. This route does not. It does not call the order path or ``leave_safely``.
``POST /api/agent/show`` stays on the API key.
"""
from __future__ import annotations

import json
import os
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
    keeps_the_main_desk,
    parse_payload,
    park_before_setup,
    perform,
    second_from_open,
    switch_main_view_to_sim,
    this_pc_host,
)
from agent_desk.open_token import (
    TokenError,
    acl_is_current_user_only,
    load_or_create,
    token_file_private,
    token_path,
)
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
    monkeypatch.setattr(
        "agent_desk.open_in_nova._stake",
        lambda venue: {"venue": venue, "safe": True, "items": [], "unknown": []},
    )
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
    assert close["separate_sim"] is True
    assert calls["switched"] == [["direct"]]
    saturday = datetime(2026, 10, 17, 10, 0, tzinfo=ET)
    assert in_rth(saturday, _weekday) is False
    assert keeps_the_main_desk(saturday, _weekday) is False


def _exchange(day: date) -> bool:
    from sim.trading_day import is_trading_day

    return bool(is_trading_day(day))


def _at(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=ET)


@pytest.mark.parametrize(
    ("moment", "keeps"),
    [
        (_at(2026, 10, 20, 8, 0), True),    # premarket
        (_at(2026, 10, 20, 4, 0), True),    # session open, inclusive
        (_at(2026, 10, 20, 3, 59), False),  # overnight
        (_at(2026, 10, 20, 16, 30), True),  # after-hours
        (_at(2026, 10, 20, 19, 59), True),
        (_at(2026, 10, 20, 20, 0), False),  # session end, exclusive
    ],
)
def test_extended_hours_keep_the_main_desk(moment, keeps, calls):
    asked = []

    def stake(_venue):
        asked.append("stake")
        return {"safe": False, "items": [{"text": "a working order"}], "unknown": []}

    if keeps:
        result = _open(
            {"symbol": "IMCC", "date": DAY, "as_of": "10:00"}, now=moment, stake_for=stake,
        )
        assert result["separate_sim"] is True
        assert asked == []
        assert calls["switched"] == []
        assert "stayed on its own view" in result["chat_message"]
    else:
        with pytest.raises(OpenError) as refused:
            _open({"symbol": "IMCC", "date": DAY, "as_of": "10:00"}, now=moment, stake_for=stake)
        assert refused.value.reason == "AGENT_AT_STAKE"
        assert asked == ["stake"]
        assert calls["switched"] == []


def test_a_half_day_ends_at_13_00_and_after_hours_at_17_00(calls):
    """2026-11-27 is the day after Thanksgiving: RTH ends 13:00, after-hours 17:00."""
    day = date(2026, 11, 27)
    assert _exchange(day) is True
    for moment in (_at(2026, 11, 27, 12, 59), _at(2026, 11, 27, 13, 0), _at(2026, 11, 27, 16, 59)):
        assert keeps_the_main_desk(moment, _exchange) is True
        assert calls["switched"] == []
        opened = _open({"symbol": "IMCC", "date": DAY, "as_of": "10:00"}, now=moment, trading_day=_exchange)
        assert opened["separate_sim"] is True
    assert in_rth(_at(2026, 11, 27, 12, 59), _exchange) is True
    assert in_rth(_at(2026, 11, 27, 13, 0), _exchange) is False
    closed = _at(2026, 11, 27, 17, 0)
    assert keeps_the_main_desk(closed, _exchange) is False
    switched = _open({"symbol": "IMCC", "date": DAY, "as_of": "10:00"}, now=closed, trading_day=_exchange)
    assert switched["separate_sim"] is False
    assert calls["switched"] == [["direct"]]


def test_a_holiday_does_not_keep_the_desk(calls):
    """2026-11-26 is Thanksgiving. A weekday callback would wrongly call it open."""
    holiday = _at(2026, 11, 26, 10, 0)
    assert _exchange(holiday.date()) is False
    assert keeps_the_main_desk(holiday, _weekday) is True
    assert keeps_the_main_desk(holiday, _exchange) is False
    assert in_rth(holiday, _exchange) is False
    # 2026-07-03 is the observed Independence Day, not a 13:00 early close.
    july = _at(2026, 7, 3, 10, 0)
    assert _exchange(july.date()) is False
    assert keeps_the_main_desk(july, _exchange) is False
    opened = _open({"symbol": "IMCC", "date": DAY, "as_of": "10:00"}, now=holiday, trading_day=_exchange)
    assert opened["separate_sim"] is False
    assert calls["switched"] == [["direct"]]


@pytest.mark.parametrize(
    "text",
    [
        "a working order on AAPL",
        "an open position in AAPL",
        "the padlock is armed",
        "a live bot entry",
    ],
)
def test_each_stake_refuses_the_switch_and_does_not_queue(text, calls):
    order = []
    queued = []

    def stake(_venue):
        order.append("stake")
        return {"safe": False, "items": [{"kind": "order", "text": text}], "unknown": []}

    def switch():
        order.append("switch")

    def queue(args, plan):
        queued.append(plan)
        return {"kind": "show", "plan": plan}

    with pytest.raises(OpenError) as refused:
        _open(
            {"symbol": "IMCC", "date": DAY, "as_of": "10:00"},
            now=WEEKDAY,
            stake_for=stake,
            switch_view=switch,
            queue=queue,
        )
    assert refused.value.reason == "AGENT_AT_STAKE"
    assert text in refused.value.error
    assert "The main desk was not switched." in refused.value.error
    assert "The desk is on Live" in refused.value.error
    assert order == ["stake"]
    assert queued == []
    assert calls["switched"] == []


def test_an_unreadable_check_refuses_and_a_safe_closed_desk_switches(calls):
    unknown_order = []

    def unknown(_venue):
        unknown_order.append("stake")
        return {"safe": False, "items": [], "unknown": [{"kind": "orders"}]}

    with pytest.raises(OpenError) as refused:
        _open({"symbol": "IMCC", "date": DAY, "as_of": "10:00"}, now=WEEKDAY, stake_for=unknown)
    assert "a check could not be read (orders)" in refused.value.error
    assert unknown_order == ["stake"]
    assert calls["switched"] == []

    order = []

    def safe(_venue):
        order.append("stake")
        return {"safe": True, "items": [], "unknown": []}

    def switch():
        order.append("switch")
        calls["switched"].append(["direct"])

    opened = _open(
        {"symbol": "IMCC", "date": DAY, "as_of": "10:00"},
        now=WEEKDAY,
        stake_for=safe,
        switch_view=switch,
    )
    assert order == ["stake", "switch"]
    assert opened["separate_sim"] is False
    assert opened["command"]["plan"]["switch_view"] is True


def test_a_desk_already_on_sim_is_not_checked_or_switched(calls):
    def stake(_venue):
        raise AssertionError("already on Sim")

    opened = _open(
        {"symbol": "IMCC", "date": DAY, "as_of": "10:00"},
        now=WEEKDAY,
        venue=lambda: "sim",
        stake_for=stake,
    )
    assert opened["separate_sim"] is False
    assert calls["switched"] == []
    assert "Nova Sim" in opened["chat_message"]


def test_paper_stake_names_the_venue(calls):
    def stake(_venue):
        return {"safe": False, "items": [{"text": "a working order"}], "unknown": []}

    with pytest.raises(OpenError) as refused:
        _open(
            {"symbol": "IMCC", "date": DAY, "as_of": "10:00"},
            now=WEEKDAY,
            venue=lambda: "paper",
            stake_for=stake,
        )
    assert refused.value.reason == "AGENT_AT_STAKE"
    assert "The desk is on Paper" in refused.value.error
    assert calls["switched"] == []


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
    # chmod 0o600 is a no-op on Windows, so that platform asserts the DACL instead.
    if os.name == "nt":
        assert token_file_private(token_path()) is True
    else:
        assert token_path().stat().st_mode & 0o777 == 0o600
        assert token_file_private(token_path()) is True
    token_path().write_text(json.dumps({"schema_version": 2, "token": "x"}), encoding="utf-8")
    with pytest.raises(TokenError, match="schema"):
        load_or_create()


def test_an_acl_is_private_only_when_every_ace_is_the_current_user():
    user = "S-1-5-21-1"
    assert acl_is_current_user_only(user, [("allow", user)]) is True
    assert acl_is_current_user_only(user, [("allow", user), ("allow", user)]) is True
    assert acl_is_current_user_only(user, []) is False
    assert acl_is_current_user_only("", [("allow", user)]) is False
    assert acl_is_current_user_only(user, [("allow", "S-1-1-0")]) is False
    assert acl_is_current_user_only(user, [("allow", user), ("allow", "S-1-5-32-545")]) is False
    assert acl_is_current_user_only(user, [("deny", user)]) is False


def test_origin_rules():
    assert foreign_origin(None) is False
    assert foreign_origin("file://") is False
    assert foreign_origin("http://127.0.0.1:5173") is False
    assert foreign_origin("http://localhost:5173") is False
    assert foreign_origin("http://[::1]:18765") is False
    assert foreign_origin("http://127.1") is True  # not the exact host 127.0.0.1
    assert this_pc_host("127.0.0.1") is True
    assert foreign_origin("null") is True
    assert foreign_origin("https://evil.example") is True
    assert foreign_origin("http://127.0.0.1.evil.example") is True
    assert foreign_origin("http://127.0.0.1.evil.example:18765") is True
    assert foreign_origin("http://127.0.0.2") is True
    assert foreign_origin("http://[::ffff:127.0.0.1]") is True
    assert foreign_origin("http://user@127.0.0.1") is True
    assert foreign_origin("ftp://127.0.0.1") is True
    assert foreign_origin("http://127.0.0.1\r\n") is True


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
    prefixed = client.get("/api/agent/open-token", headers={"Origin": "http://127.0.0.1.evil.example"})
    assert prefixed.status_code == 403 and "token" not in prefixed.text
    posted = _post(
        {"symbol": "IMCC", "date": DAY, "as_of": "10:00"},
        {"Content-Type": "application/json", HEADER: token, "Origin": "http://127.0.0.1.evil.example"},
    )
    assert posted.status_code == 403 and "token" not in posted.text


def test_http_refuses_a_switch_when_something_is_at_stake(http, calls, monkeypatch):
    monkeypatch.setattr(
        "agent_desk.open_in_nova._stake",
        lambda venue: {
            "venue": venue,
            "safe": False,
            "items": [{"kind": "order", "text": "a working order on AAPL"}],
            "unknown": [],
        },
    )
    refused = _post(
        {"symbol": "IMCC", "date": DAY, "as_of": "10:00"},
        {"Content-Type": "application/json", HEADER: http["token"]},
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["reason"] == "AGENT_AT_STAKE"
    assert "was not switched" in refused.json()["detail"]["error"]
    assert calls["switched"] == []
    assert http["board"].recent() == []
