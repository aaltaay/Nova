"""The operator's auto-record switch (operator ask 2026-10-14: "i need a way to turn off the recording").

On / Off for today / Off, saved in the operator cache with a schema version; Off for today turns
back on at the next 04:00 ET; an unreadable or unknown file reads as On and says so; ``.env``'s
``NOVA_AUTO_RECORD=0`` still wins, and the route refuses to change it.
"""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from leaderboard import auto_record, auto_record_routes
from leaderboard import auto_record_switch as switch

ET = ZoneInfo("America/New_York")


def et(day: int, hh: int, mm: int = 0) -> float:
    return datetime(2026, 10, day, hh, mm, tzinfo=ET).timestamp()


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.delenv(switch.AUTO_RECORD_ENV, raising=False)
    switch.reset_for_tests()
    yield
    switch.reset_for_tests()


def test_with_no_file_it_is_on_as_it_always_was():
    assert switch.state(et(14, 10)) == {"mode": "on", "source": "default", "day": None, "until": None, "error": None}


def test_off_for_today_turns_back_on_at_the_next_0400_et():
    switch.set_mode("off_today", et(14, 15, 4))
    got = switch.state(et(14, 23))
    assert got == {"mode": "off_today", "source": "operator", "day": "2026-10-14", "until": et(15, 4), "error": None}
    assert switch.is_on(et(15, 3, 59)) is False
    assert switch.is_on(et(15, 4)) is True


def test_off_for_today_after_midnight_belongs_to_the_desk_day_before_its_0400():
    switch.set_mode("off_today", et(15, 1))
    assert switch.state(et(15, 2))["day"] == "2026-10-14"
    assert switch.is_on(et(15, 4)) is True


def test_off_stays_off_through_a_restart():
    switch.set_mode("off", et(14, 9))
    assert json.loads(switch.path().read_text(encoding="utf-8")) == {
        "schema_version": 1, "mode": "off", "day": None, "set_at": et(14, 9)}
    switch.reset_for_tests()  # a new process reads the file
    assert switch.state(et(20, 9))["mode"] == "off"
    assert switch.state(et(20, 9))["source"] == "operator"


def test_an_unknown_version_or_an_unreadable_file_reads_on_and_says_so():
    switch.path().parent.mkdir(parents=True, exist_ok=True)
    switch.path().write_text(json.dumps({"schema_version": 2, "mode": "off"}), encoding="utf-8")
    got = switch.state(et(14, 9))
    assert got["mode"] == "on" and "version 2" in got["error"]
    switch.reset_for_tests()
    switch.path().write_text("{not json", encoding="utf-8")
    got = switch.state(et(14, 9))
    assert got["mode"] == "on" and "could not read" in got["error"]


def test_env_holds_it_off_and_the_switch_cannot_change_that(monkeypatch):
    monkeypatch.setenv(switch.AUTO_RECORD_ENV, "0")
    assert switch.state(et(14, 9))["source"] == "env"
    assert switch.is_on(et(14, 9)) is False
    with pytest.raises(switch.EnvHoldsOff):
        switch.set_mode("on", et(14, 9))
    assert not switch.path().exists()


def test_an_unknown_setting_is_refused():
    with pytest.raises(ValueError):
        switch.set_mode("maybe")


def test_the_route_saves_the_switch_and_stops_its_lines(monkeypatch):
    calls: list[bool] = []

    async def turned_off():
        calls.append(True)
        return ["AXTQ", "COHQ"]

    monkeypatch.setattr(auto_record, "turned_off", turned_off)
    app = FastAPI()
    app.include_router(auto_record_routes.router)
    client = TestClient(app)
    off = client.post("/api/auto-record", json={"mode": "off_today"})
    assert off.status_code == 200
    assert off.json()["switch"]["mode"] == "off_today" and off.json()["stopped"] == ["AXTQ", "COHQ"]
    on = client.post("/api/auto-record", json={"mode": "on"})
    assert on.json()["switch"]["mode"] == "on" and on.json()["stopped"] == [] and calls == [True]
    assert client.post("/api/auto-record", json={"mode": "later"}).status_code == 422
    monkeypatch.setenv(switch.AUTO_RECORD_ENV, "0")
    refused = client.post("/api/auto-record", json={"mode": "on"})
    assert refused.status_code == 409 and "NOVA_AUTO_RECORD=0" in refused.json()["detail"]


@pytest.mark.parametrize("given, words", [
    ({"mode": "off", "source": "operator"}, "turned off on Records"),
    ({"mode": "off_today", "source": "operator"}, "off for today on Records; back on at 04:00 ET"),
    ({"mode": "off", "source": "env"}, "off: NOVA_AUTO_RECORD=0 in .env"),
])
def test_the_diagnostics_row_says_who_turned_it_off(given, words):
    from diagnostics import collect_leaderboard

    disk = {"store_bytes": 1, "free_bytes": 800 * 1024**3, "size_error": None, "free_error": None}
    recorder = {"recording": True, "ok": True, "error": None, "since": None, "run_id": "r1"}
    auto = {"active": False, "window": "its windows", "symbols": [], "switch": given}
    [_board, row] = collect_leaderboard.leaderboard_rows(recorder=recorder, auto=auto, store_path="F:/x.sqlite3",
                                                         disk=disk)
    assert row["state"] == "off" and row["detail"] == words
