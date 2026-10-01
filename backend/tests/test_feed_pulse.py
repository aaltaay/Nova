"""The IBKR feed's heartbeat and its gaps (#672): what counts as a gap, and what never does."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from diagnostics.collect_feed import feed_rows
from ibkr import feed_pulse, wifi_drops

ET = ZoneInfo("America/New_York")


def et(h: int, m: int, s: float = 0.0, day: int = 1) -> float:
    """Epoch seconds of an Eastern time on 2026-10-<day> (Thursday the 1st, Saturday the 3rd)."""
    return datetime(2026, 10, day, h, m, 0, tzinfo=ET).timestamp() + s


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    feed_pulse._reset_for_tests()
    monkeypatch.setattr(feed_pulse, "_connected", lambda: True)
    monkeypatch.setattr(wifi_drops, "lookup", lambda start, end, now=None: {"state": "off", "drops": []})
    yield
    feed_pulse._reset_for_tests()


def busy(start: float, end: float, step: float = 0.2) -> None:
    """A message every ``step`` seconds, the last one at ``end``."""
    n = int(round((end - start) / step))
    for i in range(n + 1):
        feed_pulse.note(end - (n - i) * step)


def test_a_busy_feed_that_goes_silent_is_an_open_gap():
    t0 = et(9, 32, 0)
    busy(t0 - 12, t0)
    assert feed_pulse.open_gap(t0 + 2) is None  # under FEED_GAP_SEC
    gap = feed_pulse.open_gap(t0 + 9)
    assert gap == {"start": pytest.approx(t0), "end": None}
    view = feed_pulse.view(t0 + 9)
    assert view["gap"]["ongoing"] is True and view["gap"]["silent_sec"] == pytest.approx(9.0)
    assert "No IBKR data on any line for 9 s" in view["gap"]["text"]


def test_the_first_message_back_closes_it_and_tape_reads_see_it():
    t0 = et(9, 32, 6)
    busy(t0 - 12, t0)
    feed_pulse.note(t0 + 16)
    view = feed_pulse.view(t0 + 17)
    assert view["gap"] is None
    assert [(g["start"], g["end"]) for g in view["recent"]] == [(pytest.approx(t0), pytest.approx(t0 + 16))]
    assert "arrived at 09:32:22 in one burst" in view["recent"][0]["text"]
    assert feed_pulse.gaps_for_tape(t0 + 17) == [{"start": pytest.approx(t0), "end": pytest.approx(t0 + 16)}]


def test_a_thin_feed_quiet_for_seconds_is_never_a_gap():
    t0 = et(18, 30, 0)
    busy(t0 - 30, t0, step=2.5)
    assert feed_pulse.open_gap(t0 + 6) is None
    feed_pulse.note(t0 + 6)
    assert feed_pulse.view(t0 + 7)["recent"] == []


@pytest.mark.parametrize("when", [et(20, 0, 30), et(3, 59, 0), et(10, 0, 0, day=3)],
                         ids=["after 20:00", "before 04:00", "a Saturday"])
def test_outside_the_session_silence_is_the_market_closing(when):
    busy(when - 12, when)
    assert feed_pulse.open_gap(when + 30) is None
    feed_pulse.note(when + 30)
    assert feed_pulse.view(when + 31)["recent"] == []


def test_the_close_at_20_00_is_not_a_gap_that_ends_next_morning():
    t0 = et(19, 59, 50)
    busy(t0 - 12, t0)
    feed_pulse.note(et(4, 0, 5, day=2))
    assert feed_pulse.view(et(4, 0, 6, day=2))["recent"] == []


def test_seconds_inside_an_earlier_gap_do_not_make_the_feed_look_thin():
    # 2026-10-01: silent 09:31:41-44, two seconds of data, silent again 09:31:47-55.
    busy(et(9, 31, 30), et(9, 31, 40.9))
    feed_pulse.note(et(9, 31, 45.2))
    busy(et(9, 31, 45.2), et(9, 31, 46.9))
    feed_pulse.note(et(9, 31, 56))
    starts = [round(g["start"] - et(9, 31, 0), 1) for g in feed_pulse.view(et(9, 31, 57))["recent"]]
    assert starts == [46.9, 40.9]


def test_a_disconnected_gateway_is_the_headers_state_not_a_gap(monkeypatch):
    t0 = et(9, 32, 0)
    busy(t0 - 12, t0)
    monkeypatch.setattr(feed_pulse, "_connected", lambda: False)
    assert feed_pulse.open_gap(t0 + 9) is None


def test_a_wifi_drop_over_the_silence_is_named(monkeypatch):
    t0 = et(9, 32, 37)
    busy(t0 - 12, t0)
    drop = {"stopped": t0 - 0.5, "back": t0 + 4.5}
    monkeypatch.setattr(wifi_drops, "lookup", lambda start, end, now=None: {"state": "read", "drops": [drop]})
    gap = feed_pulse.view(t0 + 4)["gap"]
    assert gap["cause"] == "wifi" and gap["wifi"]["drops"] == [drop]
    assert "Windows logged the Wi-Fi reconnecting at 09:32:36 ET" in gap["text"]
    assert "(the network or the Gateway)" not in gap["text"]


def test_the_checklist_row_fails_while_silent_and_warns_after():
    t0 = et(9, 32, 6)
    busy(t0 - 12, t0)
    live = feed_rows(view=feed_pulse.view(t0 + 9), now=t0 + 9)[0]
    assert live["id"] == "ibkr_feed_gaps" and live["state"] == "fail"
    assert live["detail"] == "no IBKR data on any line for 9 s"
    feed_pulse.note(t0 + 16)
    after = feed_rows(view=feed_pulse.view(t0 + 20), now=t0 + 20)[0]
    assert after["state"] == "warn" and after["detail"].startswith("1 gap in the last 30 min, longest 16 s")
    later = feed_rows(view=feed_pulse.view(t0 + 16 + 1801), now=t0 + 16 + 1801)[0]
    assert later["state"] == "ok"
