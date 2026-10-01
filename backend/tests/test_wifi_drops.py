"""Reading Windows' Wi-Fi log for drops over a feed gap (#672): pairing, overlap, never blocking."""
from __future__ import annotations

import time

import pytest

from ibkr import wifi_drops
from ibkr.windows_restarts import parse_events_xml

NS = "http://schemas.microsoft.com/win/2004/08/events/event"


def event(event_id: int, when: str) -> str:
    return (f'<Event xmlns="{NS}"><System><Provider Name="Microsoft-Windows-WLAN-AutoConfig"/>'
            f'<EventID>{event_id}</EventID><TimeCreated SystemTime="{when}"/></System></Event>')


def test_drops_pair_each_stop_with_the_next_success_from_wevtutil_xml():
    xml = "".join([
        event(11005, "2026-10-01T13:31:17.100Z"),   # back from a drop that began before the window
        event(11004, "2026-10-01T13:31:40.718Z"),
        event(11005, "2026-10-01T13:31:45.576Z"),
        event(11004, "2026-10-01T13:32:37.000Z"),   # still down
    ])
    drops = wifi_drops.drops_from_events(parse_events_xml(xml))
    assert [(d["stopped"] is None, d["back"] is None) for d in drops] == [(True, False), (False, False), (False, True)]
    assert drops[1]["back"] - drops[1]["stopped"] == pytest.approx(4.858)


def test_overlapping_keeps_drops_down_during_the_stretch_or_just_before_it():
    drops = [{"stopped": 100.0, "back": 105.0}, {"stopped": 200.0, "back": 204.0}, {"stopped": 300.0, "back": None}]
    assert wifi_drops.overlapping(drops, 102.0, 110.0) == [drops[0]]
    assert wifi_drops.overlapping(drops, 210.0, 230.0) == [drops[1]]   # came back 6 s before: within the lookback
    assert wifi_drops.overlapping(drops, 250.0, 260.0) == []
    assert wifi_drops.overlapping(drops, 310.0, 320.0) == [drops[2]]


def test_off_windows_the_answer_is_off_and_nothing_runs(monkeypatch):
    monkeypatch.setattr(wifi_drops.sys, "platform", "linux")
    monkeypatch.setattr(wifi_drops, "read_drops", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
    assert wifi_drops.lookup(1.0, None) == {"state": "off", "drops": []}


def test_lookup_answers_from_memory_and_reads_on_the_worker(monkeypatch):
    wifi_drops._reset_for_tests()
    monkeypatch.setattr(wifi_drops.sys, "platform", "win32")
    drop = {"stopped": 1000.0, "back": 1004.0}
    monkeypatch.setattr(wifi_drops, "read_drops", lambda start, end, now=None: [drop])
    assert wifi_drops.lookup(1000.5, 1010.0, now=1011.0) == {"state": "pending", "drops": []}
    deadline = time.time() + 5
    while time.time() < deadline:
        got = wifi_drops.lookup(1000.5, 1010.0, now=1011.0)
        if got["state"] != "pending":
            break
        time.sleep(0.02)
    assert got == {"state": "read", "drops": [drop]}
    wifi_drops._reset_for_tests()


def test_an_unreadable_log_is_unknown_never_no_drop(monkeypatch):
    wifi_drops._reset_for_tests()
    monkeypatch.setattr(wifi_drops.sys, "platform", "win32")
    monkeypatch.setattr(wifi_drops, "read_drops", lambda start, end, now=None: None)
    wifi_drops.lookup(2000.0, 2005.0, now=2006.0)
    deadline = time.time() + 5
    got = {"state": "pending"}
    while time.time() < deadline and got["state"] == "pending":
        time.sleep(0.02)
        got = wifi_drops.lookup(2000.0, 2005.0, now=2006.0)
    assert got == {"state": "unknown", "drops": []}
    wifi_drops._reset_for_tests()
