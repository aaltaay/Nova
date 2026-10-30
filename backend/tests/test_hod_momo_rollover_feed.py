"""The 04:00 ET rollover reaches every open desk, in order (#800).

A desk's HOD Momo list only grows from ``alert`` frames; only an ``initial``
frame replaces it. These run the real session check, flush tick, Clear route
and connect step against fake desks and a patched session clock (no Gateway).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import hod_momo as hm
import hod_momo_alerts as alerts
import hod_momo_persist as persist
import hod_momo_session as session
from hod_momo_state import HodMomoState

ET = ZoneInfo("America/New_York")
FRIDAY, MONDAY = "2026-10-16", "2026-10-19"
FRIDAY_TS = datetime(2026, 10, 16, 19, 59, 30, tzinfo=ET).timestamp()
MONDAY_TS = datetime(2026, 10, 19, 4, 0, 5, tzinfo=ET).timestamp()
EMPTY = {"type": "initial", "alerts": [], "total": 0}


class _Desk:
    """A desk's socket: keeps each frame. ``stall`` holds its first send until set,
    after the frame went out (``before=False``) or before it did (``before=True``)."""

    def __init__(self, order: int = 0, stall: asyncio.Event | None = None, *, before: bool = False):
        self.order = order
        self.frames: list[dict] = []
        self._stall = stall
        self._before = before

    def __hash__(self) -> int:  # a set of these is walked in ``order``
        return self.order

    async def send_text(self, text: str) -> None:
        stall, self._stall = self._stall, None
        if stall is not None and self._before:
            await stall.wait()
        self.frames.append(json.loads(text))
        if stall is not None and not self._before:
            await stall.wait()

    def shown(self) -> list[str]:
        """The ids the desk lists, read from its frames the way useHodMomoStream reads them."""
        ids: list[str] = []
        for frame in self.frames:
            if frame["type"] == "initial":
                ids = [alert["id"] for alert in frame["alerts"]]
            elif frame["type"] == "alert" and frame["alert"]["id"] not in ids:
                ids.insert(0, frame["alert"]["id"])
        return ids


class _Gone(_Desk):
    async def send_text(self, text: str) -> None:
        raise RuntimeError("socket closed")


def _alert(alert_id: str, ticker: str, created_ts: float) -> hm.AlertObject:
    return hm.AlertObject(
        id=alert_id, timestamp="", ticker=ticker, strategy_id=7, strategy_name="Low Float - High Rel Vol",
        price=4.2, change_pct=12.0, rvol=8.0, float_shares=1e6, gap_pct=None, volume=200_000,
        momentum_pct=None, created_ts=created_ts,
    )


async def _quiet(_payload: dict) -> None:
    return None


def _session(monkeypatch, *, was: str, now: str) -> tuple[HodMomoState, list[tuple[str, list[str]]]]:
    """A fresh engine whose session was ``was`` and whose clock now reads ``now``; returns what gets archived."""
    state = hm.replace_state(HodMomoState())
    state.session_date = was
    archived: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(session, "session_key_et", lambda now_=None: now)
    monkeypatch.setattr(
        persist, "archive_session_alerts",
        lambda date_str: archived.append((date_str, [a.id for a in hm.get_state().today_alerts])),
    )
    monkeypatch.setattr(persist, "save_alerts", lambda *, force=False: None)
    monkeypatch.setattr(alerts, "notify_hod_alert_async", _quiet)
    return state, archived


def test_every_healthy_desk_gets_the_new_session_and_a_dead_one_stops_none(monkeypatch):
    state, archived = _session(monkeypatch, was=FRIDAY, now=MONDAY)
    state.today_alerts = [_alert("f1", "OLD", FRIDAY_TS)]
    # The first desk the restatement reaches is dead, and another sits between live ones.
    dead, live = [_Gone(0), _Gone(2)], [_Desk(1), _Desk(3), _Desk(4)]
    state.hod_ws_clients = {*dead, *live}

    assert asyncio.run(session.reset_and_tell_desks()) is True
    assert all(desk.frames == [EMPTY] for desk in live)
    assert state.hod_ws_clients == set(live)
    assert archived == [(FRIDAY, ["f1"])]
    assert state.session_date == MONDAY and state.today_alerts == []
    # Every later check inside Monday's session sends nothing.
    for _ in range(3):
        assert asyncio.run(session.reset_and_tell_desks()) is False
    assert all(desk.frames == [EMPTY] for desk in live)


def test_the_rollover_waits_for_alerts_in_flight_and_no_old_alert_follows_the_new_list(monkeypatch):
    state, archived = _session(monkeypatch, was=FRIDAY, now=MONDAY)

    async def scenario() -> tuple[list[_Desk], bool, bool, list[str]]:
        stall = asyncio.Event()
        slow, quick = _Desk(0, stall), _Desk(1)
        state.hod_ws_clients = {slow, quick}
        # Two of Friday's alerts went due in one tick, just as the clock passed 04:00.
        state.pending_consolidation = {
            "OLDA": [(0.0, _alert("w1", "OLDA", FRIDAY_TS))],
            "OLDB": [(0.0, _alert("w2", "OLDB", FRIDAY_TS))],
        }
        tick = asyncio.create_task(alerts.emit_due_alerts())
        await asyncio.sleep(0)                      # the tick took both and stalls sending w1
        roll = asyncio.create_task(session.reset_and_tell_desks())
        await asyncio.sleep(0)
        waited = not roll.done()                    # the rollover waits for the tick
        stall.set()
        sent = [a.id for a in await tick]
        rolled = await roll
        # Monday's first alert comes after the new list, once.
        state.pending_consolidation = {"NEW": [(0.0, _alert("m1", "NEW", MONDAY_TS))]}
        await alerts.emit_due_alerts()
        return [slow, quick], waited, rolled, sent

    desks, waited, rolled, sent = asyncio.run(scenario())
    for desk in desks:
        assert desk.shown() == ["m1"]
        assert [frame["type"] for frame in desk.frames] == ["alert", "alert", "initial", "alert"]
        assert desk.frames[2] == EMPTY
    assert archived == [(FRIDAY, ["w2", "w1"])]
    assert [a.id for a in state.today_alerts] == ["m1"]
    assert rolled is True and sent == ["w1", "w2"] and waited


def test_a_new_desk_gets_its_list_before_any_alert(monkeypatch):
    state, _ = _session(monkeypatch, was=MONDAY, now=MONDAY)
    state.today_alerts = [_alert("m0", "NOW", MONDAY_TS)]

    async def scenario() -> tuple[_Desk, bool]:
        stall = asyncio.Event()
        late = _Desk(0, stall, before=True)         # its first frame is slow to go out
        join = asyncio.create_task(alerts.add_desk(late))
        await asyncio.sleep(0)
        state.pending_consolidation = {"NEW": [(0.0, _alert("m1", "NEW", MONDAY_TS + 1))]}
        tick = asyncio.create_task(alerts.emit_due_alerts())
        await asyncio.sleep(0)
        waited = not tick.done()                    # the alert waits for the desk's list
        stall.set()
        await join
        await tick
        return late, waited

    late, waited = asyncio.run(scenario())
    assert late.shown() == ["m1", "m0"]
    assert [frame["type"] for frame in late.frames] == ["initial", "alert"]
    assert late in state.hod_ws_clients
    assert waited


def test_a_cold_start_is_no_rollover_and_keeps_the_sessions_saved_alerts(monkeypatch):
    state, archived = _session(monkeypatch, was="", now=MONDAY)
    saved = [_alert("m1", "NOW", MONDAY_TS)]
    monkeypatch.setattr(persist, "load_persisted_state", lambda: setattr(hm.get_state(), "today_alerts", list(saved)))
    session.load_state()
    desk = _Desk()
    state.hod_ws_clients = {desk}

    assert asyncio.run(session.reset_and_tell_desks()) is False
    assert desk.frames == []
    assert [a.id for a in state.today_alerts] == ["m1"]
    assert state.session_date == MONDAY and archived == []


def test_clear_restates_the_empty_list_through_the_same_path(monkeypatch):
    state, _ = _session(monkeypatch, was=MONDAY, now=MONDAY)
    state.today_alerts = [_alert("m1", "NOW", MONDAY_TS)]
    desk, gone = _Desk(1), _Gone(0)
    state.hod_ws_clients = {desk, gone}
    from routes import hod_momo as hod_routes

    body = asyncio.run(hod_routes.hod_momo_clear_alerts())
    assert body == {"cleared": 1, "date": MONDAY, "alerts": [], "total": 0}
    assert desk.frames == [EMPTY]
    assert state.today_alerts == [] and state.hod_ws_clients == {desk}
