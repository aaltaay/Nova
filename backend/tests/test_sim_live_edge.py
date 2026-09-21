"""Sim at now is live -- the live edge (ADR 020 live-edge amendment, 2026-09-21 evening).

``session_clock.live_edge`` is true while the playhead follows the wall clock
on today's date inside the session. At the edge a Sim tab reads the live
feed (every market gate keys on ``sim.mode.is_replay_desk``) and the Sim
broker fills against Paper's ``LiveReference``; off it everything is the
loaded replay, unchanged. An order placed at the edge is stamped with the
playhead (wall time) and unwinds like any other. Leaving the edge with
nothing loaded selects today's Session Record of the scrubbing tab under the
playhead, keeping the account. The conftest pins ``live_edge`` off for the
rest of the suite; this file restores it and fixes the wall clock.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from constants_practice import PRACTICE_NO_LIVE_PRINT_CODE
from ibkr import client as _client
from practice import broker as practice_broker
from practice import matcher, tape_hold
from sim import broker, feed, practice, replay, routes as sim_routes
from sim import live_edge as edge
from sim import session_clock as clock
from sim.mode import is_replay_desk, set_venue
from sim.status import overlay_ibkr_status
from tests.test_practice_broker import FakeLive
from tests.test_sim_practice import isolated  # noqa: F401 -- autouse fixture (temp capture + history dirs)

MONDAY = datetime(2026, 9, 21, 10, 0, tzinfo=clock.ET)  # a weekday, inside 04:00-20:00
TODAY = MONDAY.date().isoformat()
SESSION_OPEN_TS = datetime(2026, 9, 21, 4, 0, tzinfo=clock.ET).timestamp()


@pytest.fixture
def wall(monkeypatch):
    """The real ``live_edge`` on a fixed, movable wall clock, on the Sim venue with a live IMCC quote."""
    holder = {"now": MONDAY}
    monkeypatch.setattr(clock, "_wall_et_now", lambda: holder["now"])
    monkeypatch.setattr(clock, "live_edge", clock.live_edge_unpatched)
    live = FakeLive()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: live)
    set_venue("sim")
    yield holder, live


def at(hh: int, mm: int, day: datetime = MONDAY) -> datetime:
    return day.replace(hour=hh, minute=mm, second=0, microsecond=0)


def seconds_from_open(hh: int, mm: int) -> float:
    return (at(hh, mm).timestamp() - SESSION_OPEN_TS)


def write_capture(root, day: str, symbol: str, ts: float) -> None:
    directory = root / "capture" / day / symbol
    directory.mkdir(parents=True)
    (directory / "prints.jsonl").write_text(json.dumps(dict(ts=ts, symbol=symbol, price=10.0)) + "\n")
    (directory / "quotes.jsonl").write_text(
        json.dumps(dict(ts=ts, symbol=symbol, bid=9.9, ask=10.1, last=10.0)) + "\n")


# ── the predicate ────────────────────────────────────────────────────────────

def test_live_edge_is_the_playhead_following_the_wall_clock_on_todays_session(wall) -> None:
    assert clock.live_edge() is True
    assert clock.status_payload()["live_edge"] is True
    assert clock.now_et() == MONDAY
    assert is_replay_desk() is False


def test_scrubbing_pausing_a_past_day_and_closed_hours_are_off_the_edge(wall) -> None:
    holder, _live = wall
    clock.scrub_to_second(seconds_from_open(9, 58))
    assert clock.live_edge() is False and is_replay_desk() is True
    clock.clear_scrub()
    assert clock.live_edge() is True
    clock.set_paused(True)
    assert clock.live_edge() is False
    clock.set_paused(False)
    assert clock.live_edge() is False  # resumed where it was frozen, not at now
    clock.clear_scrub()
    clock.set_session_date("2026-09-18")  # a past day loaded re-dates the session
    assert clock.live_edge() is False
    clock.set_session_date(None)
    holder["now"] = at(21, 0)  # after the session close the playhead is clamped
    assert clock.live_edge() is False
    holder["now"] = datetime(2026, 9, 19, 10, 0, tzinfo=clock.ET)  # Saturday replays Friday
    assert clock.live_edge() is False


def test_paper_is_never_a_replay_desk(wall) -> None:
    set_venue("paper")
    assert is_replay_desk() is False
    clock.scrub_to_second(0)
    assert is_replay_desk() is False


# ── fills ────────────────────────────────────────────────────────────────────

def test_at_the_edge_the_sim_broker_fills_against_the_live_reference(wall) -> None:
    assert practice.loaded() is None
    assert broker.place("SPY", "BUY", 1, "MKT")["reason_code"] == PRACTICE_NO_LIVE_PRINT_CODE
    raw = broker.place("IMCC", "BUY", 10, "MKT")
    assert raw["ok"] and raw["broker_status"] == "Filled" and raw["mode"] == "sim"
    row = broker.closed_orders()[0]
    assert (row["avg_fill_price"], row["fill_basis"], row["fill_estimated"]) == (10.02, "live_quote", True)
    assert row["placed_ts"] == MONDAY.timestamp()  # the playhead, which at the edge is wall time
    assert row["account_id"] == "NOVA-SIM" and row["venue"] == "sim"


def test_off_the_edge_the_sim_broker_is_the_replay_again(wall) -> None:
    clock.scrub_to_second(seconds_from_open(9, 58))
    assert broker.place("IMCC", "BUY", 1, "MKT")["reason_code"] == "SIM_NO_REPLAY"
    clock.clear_scrub()
    assert broker.place("IMCC", "BUY", 1, "MKT")["broker_status"] == "Filled"


def test_scrubbing_back_past_an_edge_order_unwinds_it_like_any_other(wall) -> None:
    holder, _live = wall
    broker.place("IMCC", "BUY", 10, "MKT")
    holder["now"] = at(10, 5)
    clock.scrub_to_second(seconds_from_open(10, 2))
    assert [r["qty"] for r in broker.positions()] == [10]  # placed at 10:00, still before the playhead
    clock.scrub_to_second(seconds_from_open(9, 59))
    assert broker.positions() == [] and broker.closed_orders() == []
    clock.clear_scrub()
    assert clock.live_edge() and broker.positions() == []  # nothing is re-placed


def test_status_overlay_carries_live_edge_on_sim_only(wall) -> None:
    assert overlay_ibkr_status({})["live_edge"] is True
    clock.scrub_to_second(0)
    assert overlay_ibkr_status({})["live_edge"] is False
    set_venue("paper")
    assert "live_edge" not in overlay_ibkr_status({})


# ── the live matcher takes Sim's resting orders at the edge ─────────────────

@pytest.mark.asyncio
async def test_the_live_matcher_holds_sim_lines_at_the_edge_and_paper_always(wall, monkeypatch) -> None:
    _holder, live = wall
    held: list[list[str]] = []

    async def reconcile(wanted):
        held.append(sorted(wanted))
        return {}

    monkeypatch.setattr(tape_hold, "reconcile", reconcile)
    matcher.reset_for_tests()
    broker.place("IMCC", "BUY", 5, "LMT", limit_price=9.5)
    assert [b.venue for b in matcher.live_brokers()] == ["paper", "sim"]
    await matcher.pass_venues()
    assert held[-1] == ["IMCC"]
    live.prints = [(MONDAY.timestamp() + 1, 9.4)]
    filled = await matcher.pass_venues(now=MONDAY.timestamp() + 2)
    assert [(r["avg_fill_price"], r["fill_basis"], r["venue"]) for r in filled] == [(9.5, "print_cross", "sim")]
    clock.scrub_to_second(0)
    assert [b.venue for b in matcher.live_brokers()] == ["paper"]


# ── market-data gates ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_sim_tab_at_the_edge_asks_for_a_real_depth_line_not_a_replay_slot(wall, monkeypatch) -> None:
    from ibkr.depth import state as depth_state
    from ibkr.depth.subscribe import needs_subscribe, subscribe_async

    depth_state.reset_all()
    monkeypatch.setattr(_client, "is_ready", lambda: False)
    monkeypatch.setattr(_client, "unavailable_detail", lambda what: f"{what}: not connected")
    result = await subscribe_async("IMCC")
    assert result["ok"] is False and "not connected" in result["error"]
    assert depth_state.is_subscribed("IMCC") is False  # no slot pretending to be a line
    clock.scrub_to_second(0)
    assert (await subscribe_async("IMCC"))["ok"] is True  # off the edge: the replay slot
    assert depth_state.is_subscribed("IMCC") and not depth_state.is_live("IMCC")
    assert needs_subscribe("IMCC") is False
    clock.clear_scrub()
    assert needs_subscribe("IMCC") is True  # back at the edge the slot is not enough


def test_quotes_tape_and_sensors_take_the_live_path_at_the_edge(wall, monkeypatch) -> None:
    from ibkr import tape_events, ticks
    from sensors import feeds

    monkeypatch.setattr(ticks._status, "last_quotes", lambda subs, symbols: {"IMCC": {"price": 1.0}})
    assert ticks.last_quotes(["IMCC"]) == {"IMCC": {"price": 1.0}}
    assert tape_events._practice_desk() is False
    assert feeds._label("ibkr_tape") == "ibkr_tape"
    clock.scrub_to_second(0)
    assert ticks.last_quotes(["IMCC"]) == {}  # nothing loaded: the replay is empty, never live
    assert tape_events._practice_desk() is True
    assert feeds._label("ibkr_tape") == "replay"


def test_the_feed_leaves_todays_recording_off_the_panels_at_the_edge(wall, monkeypatch, isolated) -> None:  # noqa: F811
    write_capture(isolated, TODAY, "AAPL", at(9, 30).timestamp())
    assert replay.set_replay(TODAY, "AAPL")["replay_ok"]
    forwarded: list[str] = []
    monkeypatch.setattr(feed, "_capture_tick", lambda: forwarded.append("tick") or {})
    assert clock.live_edge() is False  # loading aligned the playhead to the first print
    feed.tick()
    assert forwarded == ["tick"]
    clock.clear_scrub()
    assert clock.live_edge() is True  # today's own recording, followed to the wall clock
    feed.tick()
    assert forwarded == ["tick"]


# ── leaving the edge selects today's recording ──────────────────────────────

@pytest.mark.parametrize("move", [{"minute_from_open": 362}, {"paused": True}])
def test_leaving_the_edge_selects_todays_recording_under_the_playhead_and_keeps_the_account(
    wall, isolated, move,  # noqa: F811
) -> None:
    holder, _live = wall
    write_capture(isolated, TODAY, "AAPL", at(9, 30).timestamp())
    broker.place("IMCC", "BUY", 10, "MKT")  # at 10:00, at the edge
    holder["now"] = at(10, 5)
    out = sim_routes.post_sim_clock({**move, "symbol": "aapl"})
    assert out["live_edge"] is False
    assert (out["replay_source"], out["replay_symbol"], out["replay_date"]) == ("capture", "AAPL", TODAY)
    expected = 6 * 3600 + 120 if "minute_from_open" in move else 6 * 3600 + 300
    assert abs(out["second_from_open"] - expected) <= 1  # where the operator put it, not the recording's start
    assert practice.loaded().source == practice.CAPTURE
    assert [r["qty"] for r in broker.positions()] == [10]  # the account traded this very tape: kept
    clock.set_paused(False)
    out = sim_routes.post_sim_clock({"follow_wall": True})
    assert out["live_edge"] is True and out["replay_source"] == "capture"  # the past stays loaded


def test_leaving_the_edge_with_no_recording_is_a_stated_absence(wall) -> None:
    out = sim_routes.post_sim_clock({"minute_from_open": 300, "symbol": "IMCC"})
    assert out["live_edge"] is False and out["replay_source"] == "none" and practice.loaded() is None
    assert edge.own_recording_today("IMCC") is None


def test_a_scrub_that_was_never_at_the_edge_selects_nothing(wall, isolated) -> None:  # noqa: F811
    write_capture(isolated, TODAY, "AAPL", at(9, 30).timestamp())
    clock.scrub_to_second(seconds_from_open(9, 40))
    out = sim_routes.post_sim_clock({"minute_from_open": 300, "symbol": "AAPL"})
    assert out["replay_source"] == "none"


def test_a_scrub_never_unwinds_the_edge_order_it_does_not_pass(wall, isolated) -> None:  # noqa: F811
    """Selecting the recording must not move the playhead the unwind already honoured."""
    holder, _live = wall
    write_capture(isolated, TODAY, "AAPL", at(9, 30).timestamp())
    broker.place("IMCC", "BUY", 10, "MKT")
    holder["now"] = at(10, 5)
    sim_routes.post_sim_clock({"minute_from_open": 300, "symbol": "AAPL"})  # 09:00, before the order
    assert broker.positions() == [] and broker.closed_orders() == []
    assert practice.loaded() is not None and clock.now_et() < at(9, 1) + timedelta(seconds=2)
