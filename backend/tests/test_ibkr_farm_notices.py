"""IBKR's farm and line notices are kept with their farm and time, shown, and never acted on (#722).

2026-10-05: SAIQ's and VEEA's tape lines stopped at 09:35:42 ET; from 09:38 the HMDS farm flapped
(2105 / 2106). Nova recognised only 2104 / 2106 / 2108, and the day's API log has rotated away, so
nothing could tie the silence to a farm event.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from diagnostics import collect_farms
from ibkr import farm_notices
from ibkr import session_errors as se
from ibkr import session_state

ET = ZoneInfo("America/New_York")
T0 = datetime(2026, 10, 5, 9, 38, 1, tzinfo=ET).timestamp()


class _Event:
    def __init__(self) -> None:
        self.handlers: list = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self, *args) -> None:
        for handler in list(self.handlers):
            handler(*args)


class _IB:
    def __init__(self) -> None:
        self.errorEvent = _Event()


class _Contract:
    symbol = "SAIQ"
    secType = "STK"


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    se.reset_for_tests()
    farm_notices.reset_for_tests()
    session_state.reset_for_testing()
    session_state.set_ready()
    persisted: list[dict] = []
    from perf import recorder

    monkeypatch.setattr(recorder, "persist", persisted.append)
    yield persisted
    farm_notices.reset_for_tests()
    se.reset_for_tests()


@pytest.mark.parametrize("code, message, farm, notice", [
    (2103, "Market data farm connection is broken:usfarm", "usfarm", "broken"),
    (2104, "Market data farm connection is OK:usfarm.nj", "usfarm.nj", "ok"),
    (2105, "HMDS data farm connection is broken:ushmds", "ushmds", "broken"),
    (2106, "HMDS data farm connection is OK:ushmds", "ushmds", "ok"),
    (2107, "HMDS data farm connection is inactive but should be available upon demand.ushmds", "ushmds", "inactive"),
    (2108, "Market data farm connection is inactive but should be available upon demand.usfarm.nj",
     "usfarm.nj", "inactive"),
    (2157, "Sec-def data farm connection is broken:secdefil", "secdefil", "broken"),
    (2158, "Sec-def data farm connection is OK:secdefnj", "secdefnj", "ok"),
])
def test_every_farm_notice_is_kept_with_its_farm(code, message, farm, notice):
    row = farm_notices.note(code, message, now=T0)
    assert (row["farm"], row["notice"], row["code"], row["ts"]) == (farm, notice, code, T0)
    assert farm_notices.view()["farms"][0]["state"] == notice


def test_a_broken_farm_reads_broken_until_its_ok_pair():
    farm_notices.note(2105, "HMDS data farm connection is broken:ushmds", now=T0)
    assert farm_notices.view()["broken"] == ["ushmds"]
    farm_notices.note(2106, "HMDS data farm connection is OK:ushmds", now=T0 + 11)
    view = farm_notices.view()
    assert view["broken"] == [] and [n["notice"] for n in view["recent"]] == ["broken", "ok"]


def test_codes_it_does_not_keep_are_left_alone():
    assert farm_notices.note(2109, "Order Event Warning", now=T0) is None
    assert farm_notices.view()["recent"] == []


def test_notices_go_to_the_perf_day_file(fresh):
    farm_notices.note(2103, "Market data farm connection is broken:usfarm", now=T0)
    assert fresh[0]["kind"] == "ib_notice" and fresh[0]["schema_version"] == 1
    assert fresh[0]["farm"] == "usfarm" and fresh[0]["ts"] == T0


def test_trouble_since_finds_the_newest_stop_near_a_silence():
    farm_notices.note(2105, "HMDS data farm connection is broken:ushmds", now=T0)
    farm_notices.note(2106, "HMDS data farm connection is OK:ushmds", now=T0 + 11)
    found = farm_notices.trouble_since(T0 - 60, window=120)
    assert found["code"] == 2105 and found["farm"] == "ushmds"
    assert farm_notices.trouble_since(T0 + 400, window=120) is None


def test_session_errors_record_farms_316_and_10197_without_acting(monkeypatch):
    """Record and display only: a farm notice never degrades the session, reconnects or restarts."""
    acted: list[str] = []
    monkeypatch.setattr(se, "_wake_reconnect", lambda: acted.append("reconnect"))
    monkeypatch.setattr(se, "_publish_reason", lambda reason: acted.append(reason))
    monkeypatch.setattr(se, "stamp_unusable", lambda **kw: acted.append("unusable"))
    monkeypatch.setattr(session_state, "set_degraded", lambda: acted.append("degraded"))
    ib = _IB()
    se.install_error_hook(ib)
    ib.errorEvent.fire(-1, 2103, "Market data farm connection is broken:usfarm", None)
    ib.errorEvent.fire(-1, 2157, "Sec-def data farm connection is broken:secdefil", None)
    ib.errorEvent.fire(4021, 316, "Market depth data has been HALTED. Please re-subscribe.", _Contract())
    ib.errorEvent.fire(4022, 10197, "No market data during competing live session", _Contract())
    assert acted == [] and session_state.is_ready()
    recent = farm_notices.view()["recent"]
    assert [(n["code"], n["notice"]) for n in recent] == [
        (2103, "broken"), (2157, "broken"), (316, "depth_halted"), (10197, "competing_session")]
    assert recent[2]["symbol"] == "SAIQ" and recent[2]["req_id"] == 4021 and recent[2]["farm"] is None
    assert "secdefil" in se.get_data_farm_status()["status"]  # the last farm notice, as before


def _row(now, *, usable=True):
    return collect_farms.farm_rows(view=farm_notices.view(), usable=usable, now=now)[0]


def test_the_checklist_warns_while_a_farm_is_broken():
    farm_notices.note(2103, "Market data farm connection is broken:usfarm", now=T0)
    row = _row(T0 + 5)
    assert row["id"] == "market_data_farms" and row["state"] == "warn"
    assert "usfarm (market data) since" in row["detail"] and row["since"] == T0
    assert "does not reconnect" in row["fix"]


def test_a_flap_that_recovered_is_ok_with_the_notice_named():
    farm_notices.note(2105, "HMDS data farm connection is broken:ushmds", now=T0)
    farm_notices.note(2106, "HMDS data farm connection is OK:ushmds", now=T0 + 11)
    row = _row(T0 + 60)
    assert row["state"] == "ok" and "2 notices in the last 30 min" in row["detail"]
    assert "2106 ok ushmds" in row["detail"]


def test_a_depth_halt_or_a_competing_session_warns_for_half_an_hour():
    farm_notices.note(10197, "No market data during competing live session", now=T0)
    assert _row(T0 + 60)["state"] == "warn"
    assert _row(T0 + 1801)["state"] == "ok"


def test_no_session_and_no_notice_is_off():
    assert _row(T0, usable=False)["state"] == "off"
    assert _row(T0)["detail"] == "no farm notice this session"
