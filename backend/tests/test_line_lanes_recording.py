"""Nova records what a lane watches, and nothing else (ADR 071 decision 8; amendment 2026-11-13).

The bots' and Claude's lane stocks are recorded while on their lane; your lane's stock while a Trader tab you can see
shows it, and five minutes after. A recording holds no line: Record by hand needs a lane on the stock, the keepalive
resumes only what a lane holds, and a resting Paper order keeps only a Level 1 line.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from line_lanes import focus, lanes, recording, sockets
from line_lanes.constants_lanes import LANES_RECORD_RETRY_SEC, LANES_YOU_RECORD_TAIL_SEC
from line_lanes.focus import FocusRead
from line_lanes.table import Lanes

NOW = 1_800_000_000.0
REAL_START = recording._start
NOBODY = {"tab": False, "other": False}


@pytest.fixture
def rec(monkeypatch):
    """The recorder faked: what started, what stopped and why; the focus sensor and the sockets as set."""
    from capture import mode

    calls: dict = {"started": [], "stopped": [], "recording": [], "on": True}
    seen: dict = {"focus": FocusRead(known=False)}

    async def start(sym, now):
        calls["started"].append(sym)
        recording._mine[sym] = now
        return True

    async def stop(sym, why):
        calls["stopped"].append((sym, why))
        recording._mine.pop(sym, None)

    monkeypatch.setattr(recording, "_start", start)
    monkeypatch.setattr(recording, "_stop", stop)
    monkeypatch.setattr(recording, "switch_on", lambda now=None: calls["on"])
    monkeypatch.setattr(mode, "capture_symbols", lambda: list(calls["recording"]))
    monkeypatch.setattr(focus, "read", lambda now=None: seen["focus"])
    monkeypatch.setattr(sockets, "shown_by_socket", lambda s: seen.get(s, NOBODY))
    recording.reset_for_tests()
    yield calls, seen
    recording.reset_for_tests()


def _sync(at: float) -> None:
    asyncio.run(recording.sync(at))


def test_the_bots_and_claudes_stocks_record_while_on_their_lane_and_stop_when_they_leave(rec):
    calls, _seen = rec
    lanes._lanes = Lanes(you="XLAB", claude="RUNR", bots="AISP")
    _sync(NOW)
    assert sorted(calls["started"]) == ["AISP", "RUNR"]            # XLAB: no tab you can see shows it
    lanes._lanes = Lanes(you="XLAB", claude="RUNR")
    _sync(NOW + 15)
    assert calls["stopped"] == [("AISP", "no lane watches it")]
    assert recording.recorded() == ["RUNR"]


def test_your_stock_records_while_a_window_shows_it_and_five_minutes_after(rec):
    calls, seen = rec
    lanes._lanes = Lanes(you="XLAB")
    seen["focus"] = FocusRead(known=True, front=frozenset({"XLAB"}), tabs=frozenset({"XLAB"}))
    _sync(NOW)
    assert calls["started"] == ["XLAB"]
    seen["focus"] = FocusRead(known=True, tabs=frozenset({"XLAB"}))          # the window went behind another app
    _sync(NOW + LANES_YOU_RECORD_TAIL_SEC - 1)
    assert calls["stopped"] == []
    _sync(NOW + LANES_YOU_RECORD_TAIL_SEC + 1)
    assert calls["stopped"] == [("XLAB", "no lane watches it")]
    assert lanes.table().you == "XLAB"                                       # the lane stays; only the recording ends


def test_the_phone_in_front_counts_and_a_hidden_desk_tab_does_not(rec):
    calls, seen = rec
    lanes._lanes = Lanes(you="XLAB")
    seen["focus"] = FocusRead(known=True, front=frozenset({"TGHL"}), tabs=frozenset({"TGHL", "XLAB"}))
    seen["XLAB"] = {"tab": True, "other": False}         # a desk tab's socket, behind TGHL's tab
    _sync(NOW)
    assert calls["started"] == []
    seen["XLAB"] = {"tab": False, "other": True}         # the phone's page, in front
    _sync(NOW + 1)
    assert calls["started"] == ["XLAB"]


def test_with_no_desk_window_a_tab_socket_opened_in_front_counts(rec):
    calls, seen = rec
    lanes._lanes = Lanes(you="XLAB")
    seen["XLAB"] = {"tab": True, "other": False}         # a browser desk: the focus sensor reports nothing
    _sync(NOW)
    assert calls["started"] == ["XLAB"]


def test_switched_off_the_lanes_record_nothing(rec):
    calls, _seen = rec
    lanes._lanes = Lanes(bots="AISP")
    _sync(NOW)
    calls["on"] = False
    _sync(NOW + 15)
    _sync(NOW + 30)
    assert calls["started"] == ["AISP"] and calls["stopped"] == [("AISP", "recording is switched off")]
    calls["on"] = True
    _sync(NOW + 45)
    assert calls["started"] == ["AISP", "AISP"]


def test_turning_the_switch_off_stops_only_the_lanes_recordings(rec):
    calls, _seen = rec
    lanes._lanes = Lanes(bots="AISP", claude="RUNR")
    calls["recording"] = ["RUNR"]
    recording.operator_took("RUNR")                       # you pressed Record on RUNR yourself
    _sync(NOW)
    assert calls["started"] == ["AISP"]
    assert asyncio.run(recording.turned_off()) == ["AISP"]
    assert calls["stopped"] == [("AISP", "recording is switched off")]


def test_a_stock_you_stopped_by_hand_is_not_started_again_that_day(rec):
    calls, _seen = rec
    lanes._lanes = Lanes(bots="AISP")
    recording.operator_stopped("AISP", now=NOW)
    _sync(NOW + 60)
    assert calls["started"] == []


def test_a_stock_leaving_every_lane_ends_its_recordings_first_yours_included(rec):
    calls, _seen = rec
    calls["recording"] = ["XLAB"]
    recording.operator_took("XLAB")
    asyncio.run(recording.stop_for("xlab"))
    assert calls["stopped"] == [("XLAB", "its lane left it")]


def test_a_start_that_fails_says_why_and_is_tried_again_a_minute_later(rec, monkeypatch):
    from capture import feed_hold

    _calls, _seen = rec
    asked: list[str] = []

    async def acquire(sym):
        asked.append(sym)
        return "IBKR refused AISP's Time & Sales line"

    monkeypatch.setattr(feed_hold, "acquire", acquire)
    monkeypatch.setattr(recording, "_start", REAL_START)
    lanes._lanes = Lanes(bots="AISP")
    _sync(NOW)
    _sync(NOW + LANES_RECORD_RETRY_SEC - 1)
    assert asked == ["AISP"]
    assert recording.status(NOW)["last_error"] == "AISP: IBKR refused AISP's Time & Sales line"
    _sync(NOW + LANES_RECORD_RETRY_SEC)
    assert asked == ["AISP", "AISP"]


def test_the_runner_hooks_the_recording_into_every_lane_move_once():
    from line_lanes import runner

    try:
        runner.install()
        runner.install()                                  # a restarted task never doubles a hook
        assert lanes._before_close.count(recording.stop_for) == 1
        assert lanes._after_move.count(recording.sync) == 1
    finally:
        if recording.stop_for in lanes._before_close:
            lanes._before_close.remove(recording.stop_for)
        if recording.sync in lanes._after_move:
            lanes._after_move.remove(recording.sync)


# -- on the wire --------------------------------------------------------------------------------------------
def test_the_lanes_route_says_who_holds_each_line(monkeypatch):
    from capture import mode
    from line_lanes import routes

    lanes._lanes = Lanes(you="XLAB", bots="AISP")
    monkeypatch.setattr(lanes, "lines_up", lambda s: {lanes.DEPTH: s == "XLAB", lanes.TAPE: s == "XLAB"})
    monkeypatch.setattr(mode, "capture_symbols", lambda: ["XLAB"])
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/ibkr")
    got = TestClient(app).get("/api/ibkr/lanes").json()
    assert got["schema_version"] == 1
    assert {k: got["you"][k] for k in ("symbol", "depth", "tape", "recording")} == {
        "symbol": "XLAB", "depth": True, "tape": True, "recording": True}
    assert got["claude"]["symbol"] is None and got["claude"]["recording"] is False
    assert got["bots"]["symbol"] == "AISP" and got["bots"]["depth"] is False and got["bots"]["recording"] is False
    assert {"setup", "why", "waiting", "error"} <= set(got["bots"])


def test_record_by_hand_refuses_a_stock_no_lane_is_on(monkeypatch):
    from capture import feed_hold
    from capture import routes as capture_routes

    asked: list[str] = []

    async def acquire(sym):
        asked.append(sym)
        return None

    monkeypatch.setattr(feed_hold, "acquire", acquire)
    lanes.enforce(True)
    app = FastAPI()
    app.include_router(capture_routes.router)
    refused = TestClient(app).post("/api/capture", json={"enabled": True, "symbol": "RUNR"})
    assert refused.status_code == 409
    assert refused.json()["detail"] == "RUNR is on no lane: open it in front to record it"
    assert asked == []                                    # no line was touched


def test_the_keepalive_gives_up_a_resume_no_lane_holds_and_says_why():
    from capture import keepalive
    from capture.constants_capture import CAPTURE_STOP_FAILURE

    keepalive.reset_for_tests()
    try:
        resume = keepalive._new_resume("RUNR", CAPTURE_STOP_FAILURE, "the recorder stopped", None, NOW,
                                       first_delay=0.0)
        keepalive._resume["RUNR"] = resume
        lanes.enforce(True)

        async def never(*_a, **_k):
            raise AssertionError("no line is asked for a stock no lane is on")

        asyncio.run(keepalive._attempt("RUNR", now=NOW + 1, ready=lambda: True, acquire=never, start=never,
                                       release=never, recording=[]))
        assert resume["gave_up"] is True
        assert resume["gave_up_reason"] == ("no lane is on RUNR: Nova records it again once you, Claude or a bot "
                                            "watch it")
    finally:
        keepalive.reset_for_tests()


# -- a resting Paper order keeps a Level 1 line, never a lane's ---------------------------------------------
@pytest.fixture
def level_1(monkeypatch):
    import ibkr.depth as depth
    from ibkr import tape_stream, ticks
    from l2 import tape
    from practice import resting_watch

    seen: dict = {"subs": [], "unsubs": [], "watched": set(), "session": None, "lines": [], "refuse": False}

    seen["owners"] = {}

    async def subscribe(sym, owner):
        seen["subs"].append((sym, owner))
        if seen["refuse"]:
            return False
        seen["owners"].setdefault(sym, set()).add(owner)
        return True

    async def unsubscribe(sym, owner):
        seen["unsubs"].append((sym, owner))
        seen["owners"].get(sym, set()).discard(owner)

    async def a_line(sym, **_kw):
        seen["lines"].append(sym)
        return {"ok": True}

    monkeypatch.setattr(ticks, "subscribe", subscribe)
    monkeypatch.setattr(ticks, "unsubscribe", unsubscribe)
    monkeypatch.setattr(ticks, "owners_for", lambda sym: set(seen["owners"].get(sym, set())))
    monkeypatch.setattr(depth, "subscribe_async", a_line)
    monkeypatch.setattr(tape_stream, "subscribe_async", a_line)
    monkeypatch.setattr(tape, "is_watched", lambda s: s in seen["watched"])
    monkeypatch.setattr(tape, "watch_symbol", lambda s, _sid: seen["watched"].add(s))
    monkeypatch.setattr(tape, "unwatch_symbol", lambda s: seen["watched"].discard(s))
    monkeypatch.setattr(tape, "session_id", lambda s: seen["session"])
    resting_watch.reset_for_tests()
    yield seen, resting_watch
    resting_watch.reset_for_tests()


def test_a_resting_order_keeps_a_level_1_line_and_the_archive_watch_and_no_lane_line(level_1):
    seen, watch = level_1
    assert asyncio.run(watch.reconcile(["xlab"])) == {}
    assert seen["subs"] == [("XLAB", "practice")] and seen["watched"] == {"XLAB"}
    assert asyncio.run(watch.reconcile(["XLAB"])) == {}
    assert seen["subs"] == [("XLAB", "practice")]                 # kept, never asked again
    asyncio.run(watch.reconcile([]))
    assert seen["unsubs"] == [("XLAB", "practice")] and seen["watched"] == set()
    assert seen["lines"] == []                                    # no Level 2, no Time & Sales line


def test_a_reconnect_that_cleared_the_level_1_line_opens_it_again_on_the_next_pass(level_1):
    """PR #1312 review: ``ticks.clear_all_subscriptions`` at a reconnect drops the line; the hold must not trust its
    own memory of it, or the order's ``l1_last`` fills stop."""
    seen, watch = level_1
    asyncio.run(watch.reconcile(["XLAB"]))
    seen["owners"].clear()                                        # IBKR reconnected: every Level 1 line let go
    assert asyncio.run(watch.reconcile(["XLAB"])) == {}
    assert seen["subs"] == [("XLAB", "practice"), ("XLAB", "practice")]
    assert watch.held("XLAB") == {"l1": True, "watch": True}


def test_a_watch_a_recorder_took_over_stays_and_a_refused_level_1_line_is_said(level_1):
    seen, watch = level_1
    asyncio.run(watch.reconcile(["XLAB"]))
    seen["session"] = "rec-1"                                     # a recording now owns XLAB's archive
    asyncio.run(watch.reconcile([]))
    assert seen["watched"] == {"XLAB"}
    seen["refuse"] = True
    assert asyncio.run(watch.reconcile(["TGHL"])) == {"TGHL": "IBKR did not open TGHL's Level 1 line"}


def test_a_tape_pane_whose_stock_left_every_lane_is_told_where_your_lane_is():
    from ibkr import tape_stream

    q = tape_stream.open_viewer_queue("XLAB")
    try:
        tape_stream.push_lane("xlab", "Your Level 2 moved to TGHL.", {"you": "TGHL", "claude": None, "bots": None})
        frames = q.drain_nowait()
    finally:
        tape_stream.close_viewer_queue("XLAB", q)
    assert frames == [{"type": "lane", "symbol": "XLAB", "message": "Your Level 2 moved to TGHL.",
                       "lane": {"you": "TGHL", "claude": None, "bots": None}}]
