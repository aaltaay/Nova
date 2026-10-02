"""A symbol the setup scanner starts following mid-session is seeded from 04:00 (2026-10-02, AMOD).

The scanner followed AMOD at 07:51:22. The bar store held none of its minutes before its Level 1
line opened, so the seed came back empty and every lane warmed up from scratch: the 1-minute first
pullback wrote its first line at 08:23, 32 bars later, and the 5-minute one still read "warming up
(17/32 bars)" at 09:19, while AMOD had traded since 04:00. A short seed now keeps the symbol seeding,
asks for IBKR's 1-minute history of today (one symbol at a time, paced), then seeds from the store.
"""
from __future__ import annotations

import asyncio
import math
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from setup_scanner import hooks
from setup_scanner.bars import Bar
from setup_scanner.engine import SetupEngine
from setup_scanner.five_minute_lane import is_five_minute
from setup_scanner.seeder import (
    SEED_COVERED,
    SEED_FAILED,
    SEED_FILLED,
    SEED_SHED,
    late_start,
    send_wait,
)
from setup_scanner.store import SetupStore
from setup_templates.store import TemplateStore
from tests.test_setup_scanner_engine import EYES, FakeTape, bar_msg

ET = ZoneInfo("America/New_York")
DAY = "2026-10-02"     # a Friday: the morning of the report
SYM = "AMOD"


def at(hh: int, mm: int, ss: float = 0.0, day: str = DAY) -> float:
    y, mo, d = (int(x) for x in day.split("-"))
    return datetime(y, mo, d, hh, mm, tzinfo=ET).timestamp() + ss


def minutes(hh: int, mm: int, n: int, price: float = 2.60, v: float = 20_000) -> list[Bar]:
    """``n`` one-minute bars from ``hh:mm``, wiggling a cent around ``price``."""
    out = []
    for i in range(n):
        o, c = (price, price + 0.01) if i % 2 else (price + 0.01, price)
        out.append(Bar(at(hh, mm) + 60 * i, o, max(o, c) + 0.01, min(o, c) - 0.01, c, v))
    return out


class Store:
    """The bar store as the seed hook reads it, and a history hook that fills it."""

    def __init__(self, day: dict[str, list[Bar]], *, answer=(SEED_FILLED, None), gate: asyncio.Event | None = None):
        self.bars: dict[str, list[Bar]] = {}
        self.day, self.answer, self.gate = day, answer, gate
        self.asks: list[str] = []
        self.in_flight = 0
        self.most_in_flight = 0

    def seed(self, sym: str, since: float) -> list[Bar]:
        return [b for b in self.bars.get(sym, []) if b.t >= since]

    async def history(self, sym: str, since: float):
        self.asks.append(sym)
        self.in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self.in_flight)
        try:
            if self.gate is not None:
                await self.gate.wait()
            if self.answer[0] == SEED_FILLED:
                self.bars[sym] = list(self.day.get(sym, []))
            return self.answer
        finally:
            self.in_flight -= 1


def engine(tmp_path, store: Store, universe, clock, *, history=True, setups=("first_pullback",)):
    return SetupEngine(store=SetupStore(tmp_path / "setups.db"), tape=FakeTape(), universe=lambda: list(universe),
                       seed=store.seed, history=store.history if history else None, replay_desk=lambda: False,
                       audit=lambda **kw: None, clock=lambda: clock["t"],
                       templates=lambda: TemplateStore(tmp_path / "t.json"), journal=lambda e: None,
                       levels=EYES, setups=setups)


async def tick(eng, clock, t):
    clock["t"] = t
    await eng.tick(t)
    for _ in range(200):                       # let an ask in flight land (its store read is a thread)
        task = eng.seeder.task
        if task is None or task.done():
            break
        await asyncio.sleep(0.005)


def lanes(eng):
    one = eng.playing_lane("first_pullback")
    five = next(lane for lane in eng.lanes if is_five_minute(lane) and lane.setup == "first_pullback")
    return one, five


def test_a_name_followed_mid_morning_is_seeded_from_0400_after_its_history(tmp_path):
    """AMOD: followed at 07:51:22 with nothing stored; IBKR's history holds its minutes from 04:00."""
    day = {SYM: minutes(4, 0, 231)}            # 04:00-07:50: it had traded all morning
    store = Store(day)
    clock = {"t": at(7, 51, 22)}

    async def go():
        eng = engine(tmp_path, store, [SYM], clock)
        await eng.tick(at(7, 51, 22))          # follows AMOD: the seed is empty -> it waits on its history
        assert SYM in eng.seeding and eng.board(at(7, 51, 22))["seeding"] == 1
        await tick(eng, clock, at(7, 51, 22.25))
        await tick(eng, clock, at(7, 51, 22.5))
        return eng

    eng = asyncio.run(go())
    assert store.asks == [SYM]
    assert SYM not in eng.seeding and eng.board(at(7, 51, 22.5))["seeding"] == 0
    bars = eng.bars[SYM].completed
    assert bars[0].t == at(4, 0) and len(bars) == 231
    one, five = lanes(eng)
    assert not one.det[SYM].reason.startswith("warming up"), one.det[SYM].reason
    assert not five.det[SYM].reason.startswith("warming up"), five.det[SYM].reason


def test_without_the_history_hook_the_lanes_warm_up_from_scratch(tmp_path):
    """What AMOD got: the seed as the store had it, nothing before the line opened."""
    store = Store({SYM: minutes(4, 0, 231)})
    clock = {"t": at(7, 51, 22)}
    eng = engine(tmp_path, store, [SYM], clock, history=False)
    asyncio.run(eng.tick(at(7, 51, 22)))
    assert store.asks == [] and SYM not in eng.seeding
    one, five = lanes(eng)
    assert one.det[SYM].reason.startswith("warming up")


def test_live_minutes_since_the_follow_keep_their_place(tmp_path):
    """The Level 1 line's minutes that land while the history is asked for are kept once; IBKR's
    version of the same minutes is dropped, so no minute (and no volume) counts twice."""
    hist = minutes(4, 0, 233, v=20_000)        # 04:00-07:52: IBKR's history holds 07:51 and 07:52 too
    gate = asyncio.Event()
    store = Store({SYM: hist}, gate=gate)
    clock = {"t": at(7, 51, 22)}

    async def go():
        eng = engine(tmp_path, store, [SYM], clock)
        await tick(eng, clock, at(7, 51, 22))
        assert store.asks == [SYM] and SYM in eng.seeding
        for b in (Bar(at(7, 51), 2.61, 2.70, 2.60, 2.69, 123_456), Bar(at(7, 52), 2.69, 2.75, 2.66, 2.74, 98_765)):
            eng.on_l1_minute("bar", SYM, bar_msg(b))
        await tick(eng, clock, at(7, 53, 1))   # the line's minutes arrive; the lanes still wait
        assert SYM in eng.seeding and [b.t for b in eng.bars[SYM].completed] == [at(7, 51), at(7, 52)]
        gate.set()
        await tick(eng, clock, at(7, 53, 2))
        await tick(eng, clock, at(7, 53, 3))
        return eng

    eng = asyncio.run(go())
    bars = eng.bars[SYM].completed
    ts = [b.t for b in bars]
    assert SYM not in eng.seeding
    assert ts == sorted(set(ts)) and ts[0] == at(4, 0) and len(bars) == 233
    assert [b.v for b in bars if b.t >= at(7, 51)] == [123_456, 98_765]
    assert sum(b.v for b in bars) == 231 * 20_000 + 123_456 + 98_765


def test_several_names_at_once_are_asked_one_at_a_time(tmp_path):
    """A restart, or HOD Momo admitting a handful together, never sends a burst of history requests."""
    names = ["AIXI", "AMOD", "GOW", "SDEV", "TNMG"]
    gate = asyncio.Event()
    store = Store({s: minutes(4, 0, 231) for s in names}, gate=gate)
    clock = {"t": at(7, 51, 22)}

    async def go():
        eng = engine(tmp_path, store, names, clock)
        for i in range(8):                     # two seconds of ticks while the first ask hangs
            await eng.tick(at(7, 51, 22 + 0.25 * i))
            await asyncio.sleep(0.01)
        assert store.asks == ["AIXI"] and eng.board(clock["t"])["seeding"] == 5
        gate.set()
        for i in range(40):
            await tick(eng, clock, at(7, 51, 24 + 0.25 * i))
        return eng

    eng = asyncio.run(go())
    assert store.asks == sorted(names) and store.most_in_flight == 1
    assert not eng.seeding and all(eng.bars[s].completed[0].t == at(4, 0) for s in names)


def test_send_wait_paces_the_scanners_requests():
    assert send_wait(100.0, -math.inf, 0, False) is None
    assert "loading" in send_wait(100.0, -math.inf, 0, True)
    assert "asked 2s ago" in send_wait(100.0, 98.0, 0, False)
    assert send_wait(100.0, 95.0, 29, False) is None
    assert "the rest are the charts'" in send_wait(100.0, 95.0, 30, False)


def test_a_seed_that_covers_the_day_asks_nothing(tmp_path):
    """A name the line followed since 04:00, and every name at the 04:00 rollover, asks no history."""
    store = Store({})
    store.bars[SYM] = minutes(4, 0, 231)
    store.bars["NEW"] = []
    clock = {"t": at(4, 0, 30)}

    async def go():
        eng = engine(tmp_path, store, ["NEW"], clock)
        await tick(eng, clock, at(4, 0, 30))   # the rollover: nothing could have been missed yet
        assert not eng.seeding
        eng._universe_fn = lambda: ["NEW", SYM]
        await tick(eng, clock, at(7, 51, 22))  # AMOD's minutes run from 04:00 to now
        return eng

    eng = asyncio.run(go())
    assert store.asks == [] and not eng.seeding
    assert eng.bars[SYM].completed[0].t == at(4, 0)


def test_late_start_measures_the_missing_start_of_the_day():
    since, now = at(4, 0), at(7, 51, 22)
    assert late_start([], since, now) == now - since
    assert late_start(minutes(4, 0, 231), since, now) == 0
    assert late_start(minutes(7, 25, 26), since, now) == at(7, 25) - since        # first traded at 07:25
    assert late_start(minutes(4, 0, 60) + minutes(6, 0, 111), since, now) == 0    # a hole is not a late start


def test_a_hole_later_in_the_day_is_seeded_as_it_is(tmp_path):
    """A name whose line was closed 05:00-06:00 is seeded at once: waiting would hold warm lanes out."""
    store = Store({})
    store.bars[SYM] = minutes(4, 0, 60) + minutes(6, 0, 111)
    clock = {"t": at(7, 51, 22)}
    eng = engine(tmp_path, store, [SYM], clock)
    asyncio.run(eng.tick(at(7, 51, 22)))
    assert store.asks == [] and SYM not in eng.seeding and len(eng.bars[SYM].completed) == 171


def test_history_that_does_not_come_seeds_with_the_store(tmp_path):
    """IBKR not answering twice: the symbol is seeded with what the store has and warms up live."""
    store = Store({SYM: minutes(4, 0, 231)}, answer=(SEED_FAILED, "no answer within 30s"))
    store.bars[SYM] = minutes(7, 49, 2)        # what the line built before the follow
    clock = {"t": at(7, 51, 22)}

    async def go():
        eng = engine(tmp_path, store, [SYM], clock)
        await tick(eng, clock, at(7, 51, 22))
        await tick(eng, clock, at(7, 51, 30))  # 30 s after the first failure: not yet
        assert store.asks == [SYM] and SYM in eng.seeding
        await tick(eng, clock, at(7, 51, 53))
        await tick(eng, clock, at(7, 51, 54))
        return eng

    eng = asyncio.run(go())
    assert store.asks == [SYM, SYM] and SYM not in eng.seeding
    assert [b.t for b in eng.bars[SYM].completed] == [at(7, 49), at(7, 50)]


def test_a_shed_ask_is_asked_again_soon(tmp_path):
    store = Store({SYM: minutes(4, 0, 231)}, answer=(SEED_SHED, "pacing wait 3.0s"))
    clock = {"t": at(7, 51, 22)}

    async def go():
        eng = engine(tmp_path, store, [SYM], clock)
        await tick(eng, clock, at(7, 51, 22))
        await tick(eng, clock, at(7, 51, 25))
        assert store.asks == [SYM]
        store.answer = (SEED_FILLED, None)
        await tick(eng, clock, at(7, 51, 27.5))
        await tick(eng, clock, at(7, 51, 28))
        return eng

    eng = asyncio.run(go())
    assert store.asks == [SYM, SYM] and SYM not in eng.seeding
    assert eng.bars[SYM].completed[0].t == at(4, 0)


def test_an_answer_for_the_old_session_seeds_nothing(tmp_path):
    gate = asyncio.Event()
    store = Store({SYM: minutes(4, 0, 231)}, gate=gate)
    clock = {"t": at(19, 50)}

    async def go():
        eng = engine(tmp_path, store, [SYM], clock)
        await tick(eng, clock, at(19, 50))
        assert store.asks == [SYM]
        await tick(eng, clock, at(4, 0, 30, day="2026-10-05"))   # Monday's rollover
        gate.set()
        await asyncio.sleep(0.05)
        await tick(eng, clock, at(4, 0, 31, day="2026-10-05"))
        return eng

    eng = asyncio.run(go())
    assert eng.bars[SYM].completed == [] and not eng.seeding


def test_a_name_that_leaves_keeps_its_place_and_is_seeded_when_back(tmp_path):
    """The HOD Momo set churns at its edge: a name out for a few seconds keeps its ask."""
    store = Store({SYM: minutes(4, 0, 231), "OTHR": minutes(4, 0, 231)})
    universe = [SYM, "OTHR"]
    clock = {"t": at(7, 51, 22)}

    async def go():
        eng = engine(tmp_path, store, universe, clock)
        eng._universe_fn = lambda: list(universe)
        await eng.tick(at(7, 51, 22))          # both wait; AMOD (first) is asked
        universe.remove("OTHR")
        await tick(eng, clock, at(7, 51, 23))
        assert "OTHR" not in eng.seeding and "OTHR" in eng.seeder.waiting
        universe.append("OTHR")
        for i in range(4):
            await tick(eng, clock, at(7, 51, 30 + i))
        return eng

    eng = asyncio.run(go())
    assert store.asks == [SYM, "OTHR"] and not eng.seeding and not eng.seeder.waiting
    assert eng.bars["OTHR"].completed[0].t == at(4, 0)


# -- the live hook (hooks.live_history) and the seed read (hooks.default_seed) ---------------------------

def _stored(bars: list[Bar], fetched_ts: float) -> dict:
    return {"bars": [bar_msg(b) for b in bars], "coverage": {"fetched_ts": fetched_ts}}


@pytest.fixture
def live(monkeypatch):
    import bars_store
    from ibkr import client, historical_service

    state = SimpleNamespace(stored=None, sent=[], raise_=None, now=at(7, 51, 22))

    async def request_bars(sym, tf, limit, *, priority):
        state.sent.append((sym, tf, limit, priority))
        if state.raise_ is not None:
            raise state.raise_
        return {}

    monkeypatch.setattr(bars_store, "read", lambda *a, **k: state.stored)
    monkeypatch.setattr(client, "is_ready", lambda: True)
    monkeypatch.setattr(historical_service, "request_bars", request_bars)
    monkeypatch.setattr(hooks, "_last_history_send", -math.inf)
    monkeypatch.setattr(hooks, "time", SimpleNamespace(time=lambda: state.now, monotonic=lambda: 1_000.0))
    historical_service.reset_for_testing()
    return state


def test_live_history_asks_ibkr_when_nothing_covers_the_day(live):
    assert asyncio.run(hooks.live_history(SYM, at(4, 0))) == (SEED_FILLED, None)
    assert live.sent == [(SYM, "1Min", 960, "background")]


def test_live_history_asks_nothing_when_ibkrs_last_fill_covers_the_day(live):
    """A stock that first traded at 07:25, filled by a chart at 07:30, its line building since."""
    live.stored = _stored(minutes(7, 25, 26), fetched_ts=at(7, 30, 5))
    assert asyncio.run(hooks.live_history(SYM, at(4, 0))) == (SEED_COVERED, None)
    assert live.sent == []
    live.stored = _stored(minutes(7, 51, 1), fetched_ts=at(5, 0, 5))        # a 05:00 fill held nothing yet
    assert asyncio.run(hooks.live_history(SYM, at(4, 0)))[0] == SEED_FILLED
    assert len(live.sent) == 1


def test_live_history_maps_ibkrs_answers(live, monkeypatch):
    from ibkr import client, historical_service

    live.raise_ = historical_service.HistoricalShed("pacing wait 4.0s")
    assert asyncio.run(hooks.live_history(SYM, at(4, 0))) == (SEED_SHED, "pacing wait 4.0s")
    monkeypatch.setattr(hooks, "_last_history_send", -math.inf)
    live.raise_ = HTTPException(status_code=504, detail="IBKR historical data did not answer within 12s")
    assert asyncio.run(hooks.live_history(SYM, at(4, 0))) == (
        SEED_FAILED, "IBKR historical data did not answer within 12s")
    outcome, why = asyncio.run(hooks.live_history(SYM, at(4, 0)))          # 0 s after the last ask
    assert outcome == SEED_SHED and "asked 0s ago" in why and len(live.sent) == 2
    monkeypatch.setattr(client, "is_ready", lambda: False)
    assert asyncio.run(hooks.live_history(SYM, at(4, 0))) == (SEED_SHED, "IBKR is not ready")


def test_the_seed_leaves_out_the_minute_now_forming(monkeypatch):
    """IBKR's history holds the forming minute half-made; the line's own bar for it must win."""
    import bars_store

    asked = {}

    def read(sym, tf, limit, *, from_ts=None, through_ts=None):
        asked.update(from_ts=from_ts, through_ts=through_ts)
        return None

    monkeypatch.setattr(bars_store, "read", read)
    monkeypatch.setattr(hooks, "time", SimpleNamespace(time=lambda: at(7, 51, 40), monotonic=lambda: 0.0))
    assert hooks.default_seed(SYM, at(4, 0)) == []
    assert asked == {"from_ts": at(4, 0), "through_ts": at(7, 50)}
    monkeypatch.setattr(hooks, "time", SimpleNamespace(time=lambda: at(23, 32), monotonic=lambda: 0.0))
    hooks.default_seed(SYM, at(4, 0))
    assert asked["through_ts"] == at(19, 59)
