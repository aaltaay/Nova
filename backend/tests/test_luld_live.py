"""The LULD worker, its wire view and the Level 2 socket's frames (ADR 047)."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from luld import ladder, live, views
from luld.tracker import Facts

ET = ZoneInfo("America/New_York")
DAY = "2026-09-22"


def t(hms: str) -> float:
    return datetime.fromisoformat(f"{DAY}T{hms}").replace(tzinfo=ET).timestamp()


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    live.reset_for_tests()
    # The worker thread is the process's; tests step it by hand.
    monkeypatch.setattr(live, "_ensure_thread", lambda: None)
    monkeypatch.setattr(live, "_halted", lambda symbols, now: {})
    monkeypatch.setattr(live, "_line_held", lambda symbol: True)
    monkeypatch.setattr(live, "_feed_gaps", lambda now: [])
    monkeypatch.setattr(live, "_board_close", {})
    # A $100M company: Tier 2 for sure.
    monkeypatch.setattr("fundamentals.peek_cached", lambda symbol: {"market_cap": 100e6})
    yield
    live.reset_for_tests()


def drain() -> None:
    while not live._q.empty():
        live.process(live._q.get_nowait())


def print_payload(hms: str, price: float, cond: str = "", sets_price: bool = True) -> dict:
    return {"symbol": "xyz", "receive_ts": t(hms), "price": price, "sets_price": sets_price,
            "conditions": cond, "exchange": "NASDAQ"}


def opened(prev: float = 9.0) -> None:
    live.enqueue_print(print_payload("09:30:01", 10.0, "O X"))
    drain()
    live.note_l1("XYZ", SimpleNamespace(bid=9.98, ask=10.02, close=prev), t("09:30:02"))
    drain()
    live.tick(t("09:30:03"))     # facts: the previous close the L1 line said


def test_a_stock_is_followed_from_its_first_live_print():
    assert live.view("XYZ", t("09:30:00"))["state"] == "unknown"     # no tape line
    opened()
    v = live.view("XYZ", t("09:30:05"))
    assert (v["state"], v["lower"], v["upper"], v["exact"]) == ("bands", 9.0, 11.0, True)
    assert v["source"] == "live" and v["watching"] is True and v["text"] == "LULD 9.00 - 11.00"
    assert v["prev_close"] == 9.0 and v["reference_words"] == "the opening print"


def test_level_1_quotes_count_only_for_a_followed_stock_and_only_when_they_change():
    live.note_l1("ABC", SimpleNamespace(bid=1.0, ask=1.1, close=1.0), t("09:31:00"))
    assert live._q.empty()
    opened()
    tick = SimpleNamespace(bid=9.98, ask=10.02, close=9.0)
    live.note_l1("XYZ", tick, t("09:31:00"))
    assert live._q.empty()                                          # the same quote again
    live.note_l1("XYZ", SimpleNamespace(bid=8.95, ask=9.00, close=9.0), t("09:31:01"))
    drain()
    v = live.view("XYZ", t("09:31:05"))
    assert v["state"] == "limit" and v["limit"]["side"] == "down"
    assert v["text"].startswith("LIMIT DOWN 9.00") and "in 11 s" in v["text"]


def test_a_bad_payload_is_counted_never_raised():
    live.enqueue_print({"symbol": "XYZ"})
    assert live.status()["dropped"] == 1


def test_a_halt_from_the_halt_state_pauses_the_band(monkeypatch):
    opened()
    monkeypatch.setattr(live, "_halted", lambda symbols, now: {s: True for s in symbols})
    live.tick(t("09:40:00"))
    v = live.view("XYZ", t("09:40:01"))
    assert v["state"] == "paused" and v["lower"] is None and "Halted since" in v["reason"]


def test_losing_the_tape_line_makes_the_band_approximate(monkeypatch):
    opened()
    monkeypatch.setattr(live, "_line_held", lambda symbol: False)
    live.tick(t("09:35:00"))
    v = live.view("XYZ", t("09:35:01"))
    assert v["watching"] is False and "stopped holding" in v["text"]
    monkeypatch.setattr(live, "_line_held", lambda symbol: True)
    live.tick(t("09:36:00"))
    v = live.view("XYZ", t("09:36:01"))
    assert v["exact"] is False and "did not hold" in v["gap"]["reason"]


def test_an_ibkr_feed_gap_makes_the_band_approximate(monkeypatch):
    opened()
    monkeypatch.setattr(live, "_feed_gaps", lambda now: [{"start": t("09:34:00"), "end": t("09:34:09")}])
    live.tick(t("09:34:10"))
    assert live.view("XYZ", t("09:34:11"))["exact"] is False


def test_a_tracker_with_no_print_for_long_is_forgotten():
    opened()
    live.tick(t("10:10:00"))
    assert live.status()["symbols"] == []


def test_an_unknown_company_size_assumes_tier_2_and_says_so(monkeypatch):
    monkeypatch.setattr("fundamentals.peek_cached", lambda symbol: None)
    opened(prev=5.0)          # over $3 with no market cap known: 5% or 10%?
    v = live.view("XYZ", t("09:31:00"))
    assert (v["state"], v["tier"], v["tier_sure"], v["upper"]) == ("bands", 2, False, 11.0)
    assert "assumed" in v["tier_text"] and v["text"] == "LULD ≈9.00 - ≈11.00"


def test_off_outside_the_bands_hours():
    raw = {"day_open": t("09:30:00"), "day_close": t("16:00:00"), "halted_since": None, "await_reopen": False,
           "limit": None, "reference": None, "warm_until": None, "tape_since": t("09:00:00"), "upper": None}
    assert views.state_of(raw, Facts(prev_close=9.0, tier=2), t("09:00:00"))[0] == "off"
    assert views.state_of(raw, Facts(prev_close=9.0, tier=2), t("16:00:00"))[0] == "off"
    assert views.state_of(raw, Facts(prev_close=9.0, covered=False, covered_reason="a warrant"), t("10:00:00")) \
        == ("off", "a warrant")


def test_near_a_band_is_two_percent_or_five_cents():
    assert views._near(9.17, 9.0, 11.0) == "down"
    assert views._near(10.0, 9.0, 11.0) is None
    assert views._near(1.04, 1.0, 1.2) == "down"     # 2% of 1.04 is 2c: five cents decide


def test_the_ladder_push_sends_on_change_and_otherwise_every_few_seconds(monkeypatch):
    opened()
    monkeypatch.setattr("sim.mode.is_replay_desk", lambda: False)
    push = ladder.LuldPush("XYZ")
    first = push.frame(t("09:31:00"))
    assert first is not None and first["state"] == "bands"
    assert push.frame(t("09:31:00")) is None
    push.sent_at -= 10                                # LULD_REPEAT_SEC later
    assert push.frame(t("09:31:00")) is not None


def test_the_replay_desk_reads_the_replay(monkeypatch):
    monkeypatch.setattr("sim.mode.is_replay_desk", lambda: True)
    monkeypatch.setattr("luld.replay._capture", lambda: None)
    v = ladder.source_view("XYZ")
    assert v["source"] == "replay" and "Session Record" in v["reason"]


def test_the_depth_socket_carries_the_bands_beside_the_books(monkeypatch):
    from fastapi.testclient import TestClient

    from ibkr import depth as _depth
    from l2 import continuous
    from main import app

    async def not_idle(_symbol):
        return False

    monkeypatch.setattr(_depth, "needs_subscribe", lambda _s: False)
    monkeypatch.setattr(_depth, "current_book", lambda _s: None)
    monkeypatch.setattr(_depth, "release_when_idle", not_idle)
    monkeypatch.setattr(continuous, "start", lambda _s: None)
    monkeypatch.setattr("sim.mode.is_replay_desk", lambda: False)
    with TestClient(app).websocket_connect("/ws/ibkr/depth/XYZ") as ws:
        assert ws.receive_json()["type"] == "subscribed"
        got = ws.receive_json()
        while got["type"] == "book_watch":
            got = ws.receive_json()
        assert got["type"] == "luld" and got["symbol"] == "XYZ"
        assert got["data"]["schema_version"] == 1 and got["data"]["source"] == "live"
        # No tape line for XYZ: no band, and the reason says so.
        assert got["data"]["lower"] is None and "tape line" in got["data"]["reason"]


def test_the_route_answers_the_same_view(monkeypatch):
    from fastapi.testclient import TestClient

    from main import app

    monkeypatch.setattr("sim.mode.is_replay_desk", lambda: False)
    body = TestClient(app).get("/api/luld/xyz").json()
    assert body["symbol"] == "XYZ" and body["state"] == "unknown"
    assert TestClient(app).get("/api/luld").json()["enabled"] is True
