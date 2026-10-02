"""The setup scanner's day is the trading session, 04:00-20:00 ET (operator report 2026-10-01 23:33:
"How come these things are getting triggered right now? ... the entire market is closed, no?").

The Bots page showed OM's first pullback "new high 4.20 on a 12% leg" and its flat top "new high of
day", from one 200-share print at 20:48 in IBKR's overnight session, and RIBBU / XRPNU still "pushing
HOD" from legs at 15:52 and 17:38 that nothing ever ended. After midnight the same overnight prints
began the next day: red to green read a 23:59 print as "the 09:30 open" and armed SDEV at 00:12. The
engine now reads no minute or price outside its session and ends the day at the close.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from constants_setups import SETUPS_SESSION_CLOSED_REASON
from setup_scanner.bars import Bar
from setup_scanner.engine import SetupEngine
from setup_scanner.store import SetupStore
from setup_templates.store import TemplateStore
from tests.setup_scanner_fixtures import add, base_morning, leg_up
from tests.test_setup_scanner_engine import EYES, FakeTape, bar_msg

ET = ZoneInfo("America/New_York")
DAY = "2026-10-01"     # a Thursday: the night of the report
PILLARS = {"price": 4.0, "change_pct": 8.0, "rvol": 6.0, "float": 9e6, "news": None, "headline": None,
           "catalyst": None}


def at(hh: int, mm: int, ss: float = 0.0, day: str = DAY) -> float:
    y, mo, d = (int(x) for x in day.split("-"))
    return datetime(y, mo, d, hh, mm, tzinfo=ET).timestamp() + ss


def quiet(hh: int, mm: int, n: int, price: float) -> list[Bar]:
    """``n`` one-minute bars from ``hh:mm`` wiggling a cent around ``price``."""
    t0 = at(hh, mm)
    out = []
    for i in range(n):
        o, c = (price, price + 0.01) if i % 2 else (price + 0.01, price)
        out.append(Bar(t0 + 60 * i, o, max(o, c) + 0.01, min(o, c) - 0.01, c, 5_000))
    return out


def run_up(bars: list[Bar], closes: list[float]) -> list[Bar]:
    for c in closes:
        o = bars[-1].c
        bars.append(Bar(bars[-1].t + 60, o, c + 0.01, o - 0.01, c, 80_000))
    return bars


def engine(tmp_path, *, universe, seed, clock, setups, journal=None, audits=None, levels=EYES):
    eng = SetupEngine(store=SetupStore(tmp_path / "setups.db"), tape=FakeTape(), universe=lambda: list(universe),
                      seed=seed, replay_desk=lambda: False,
                      audit=(lambda **kw: audits.append(kw)) if audits is not None else (lambda **kw: None),
                      clock=lambda: clock["t"], templates=lambda: TemplateStore(tmp_path / "t.json"),
                      journal=journal.append if journal is not None else (lambda e: None), levels=levels,
                      setups=setups)
    eng.pillars = lambda sym, now: dict(PILLARS)
    return eng


def tick(eng, clock, t):
    clock["t"] = t
    asyncio.run(eng.tick(t))


def forming(eng) -> dict[str, int]:
    return {s["id"]: s["counts"]["forming"] for s in eng.board(eng.clock())["setups"]}


def test_a_print_after_the_close_is_not_read(tmp_path):
    """OM: a quiet afternoon to 3.79, then IBKR's overnight session printed 4.20 x 200 at 20:48."""
    day = quiet(18, 0, 120, 3.79)                                   # 18:00-19:59
    clock = {"t": at(19, 59, 30)}
    eng = engine(tmp_path, universe=["OM"], seed=lambda s, since: list(day), clock=clock,
                 setups=("first_pullback", "flat_top_breakout"))
    tick(eng, clock, at(19, 59, 30))
    overnight = Bar(at(20, 48), 4.20, 4.20, 4.20, 4.20, 200)
    eng.on_l1_minute("bar", "OM", bar_msg(overnight))
    eng.on_l1_minute("last", "OM", {"price": 4.20, "ts": at(20, 48, 31), "bar_open": 4.20})
    tick(eng, clock, at(20, 49))

    assert eng.bars["OM"].completed[-1].t == at(19, 59)            # the 20:48 minute never joined the day
    assert all(lane.det["OM"].state != "leg" for lane in eng.lanes)
    assert all(lane.det["OM"].last_price != 4.20 for lane in eng.lanes)
    assert eng.board(clock["t"])["rows"] == [] and set(forming(eng).values()) == {0}


def test_a_restart_after_the_close_shows_the_day_ended_not_forming(tmp_path):
    """The 23:32 restart replayed the day from the bar store, overnight minutes and all."""
    ribbu = run_up(quiet(15, 0, 40, 12.00), [12.4, 12.9, 13.5, 14.2, 15.0, 15.9, 16.89])   # to 15:46
    om = quiet(18, 0, 120, 3.79) + [Bar(at(20, 48), 4.20, 4.20, 4.20, 4.20, 200)]
    stored = {"RIBBU": ribbu, "OM": om}
    lines: list[dict] = []
    clock = {"t": at(23, 33, 39)}
    eng = engine(tmp_path, universe=["RIBBU", "OM"], seed=lambda s, since: list(stored[s]), clock=clock,
                 setups=("first_pullback", "flat_top_breakout"), journal=lines)
    tick(eng, clock, at(23, 33, 39))

    assert eng.bars["OM"].completed[-1].t == at(19, 59)            # the stored 20:48 minute is left out
    board = eng.board(clock["t"])
    assert board["rows"] == [] and set(forming(eng).values()) == {0}
    for lane in eng.playing_lanes():
        assert lane.det["RIBBU"].state == "watching"
        assert lane.det["RIBBU"].reason == SETUPS_SESSION_CLOSED_REASON
    # The day is told as it happened: RIBBU's leg, then the close that ended it.
    ribbu_lines = [ln for ln in lines if ln.get("symbol") == "RIBBU" and ln.get("setup_type") == "flat_top_breakout"
                   and ln.get("playing")]
    assert any(ln["event"] == "leg" for ln in ribbu_lines)
    assert ribbu_lines[-1]["event"] == "state" and ribbu_lines[-1]["state"] == "watching"
    assert ribbu_lines[-1]["reason"] == SETUPS_SESSION_CLOSED_REASON
    said = len(lines)
    tick(eng, clock, at(23, 33, 40))                                 # the close is said once
    assert [ln["event"] for ln in lines[said:]] in ([], ["beat"])


def test_the_close_disarms_an_armed_setup_and_withdraws_its_proposal(tmp_path):
    """A thin name armed and near at 08:58 that never printed again: it stood "near" into the night."""
    bars = add(leg_up(base_morning(), [4.08, 4.18, 4.28, 4.38]), 4.38, 4.37, 4.30, 4.32, 30_000)
    day = "2026-09-21"
    audits: list[dict] = []
    clock = {"t": bars[-1].t + 30}
    eng = engine(tmp_path, universe=["ABCD"], seed=lambda s, since: list(bars), clock=clock,
                 setups=("first_pullback",), audits=audits)
    tick(eng, clock, clock["t"])
    eng.on_l1_minute("last", "ABCD", {"price": 4.35, "ts": clock["t"], "bar_open": 4.32})
    tick(eng, clock, clock["t"])
    assert eng.det["ABCD"].state == "near"
    prop = next(iter(eng.proposals.values()))
    assert prop["status"] == "open"

    tick(eng, clock, at(20, 0, 0.2, day=day))
    assert eng.det["ABCD"].state == "watching" and eng.det["ABCD"].reason == SETUPS_SESSION_CLOSED_REASON
    assert prop["status"] == "disarmed"
    assert any(a["action"] == "setup_proposal" and a["outcome"] == "disarmed" for a in audits)
    saved = eng.store.rows()[0]
    assert saved["disarmed_at"] and not saved.get("triggered_at")
    assert eng.board(clock["t"])["rows"] == [] and eng.tape.synced == set()   # no tape line held for it


def test_the_sessions_last_minute_landing_after_the_close_is_read_then_ended(tmp_path):
    """The 19:59 minute is flushed a moment after 20:00: it is the session's, and the day still ends."""
    bars = run_up(quiet(19, 0, 40, 12.00), [12.4, 12.9, 13.5, 14.2, 15.0, 15.9])      # to 19:45
    clock = {"t": at(19, 46, 30)}
    eng = engine(tmp_path, universe=["RIBBU"], seed=lambda s, since: list(bars), clock=clock,
                 setups=("first_pullback",))
    tick(eng, clock, at(19, 46, 30))
    assert eng.det["RIBBU"].state == "leg"
    tick(eng, clock, at(20, 0, 0.2))
    assert eng.det["RIBBU"].state == "watching"

    late = Bar(at(19, 59), 15.9, 16.89, 15.9, 16.89, 9_000)                          # a new high
    eng.on_l1_minute("bar", "RIBBU", bar_msg(late))
    tick(eng, clock, at(20, 0, 2.0))
    assert eng.bars["RIBBU"].completed[-1].t == late.t
    assert eng.det["RIBBU"].state == "watching" and eng.det["RIBBU"].reason == SETUPS_SESSION_CLOSED_REASON
    assert eng.board(clock["t"])["rows"] == []


def test_after_midnight_an_overnight_print_is_no_09_30_open(tmp_path):
    """SDEV 2026-10-01 00:12 ET: red to green armed at "the 2.78 open" -- a 23:59 overnight minute."""
    sdev = [(at(23, 59, day="2026-09-30"), 2.78, 2.78, 2.77, 2.77, 7)] + [
        (at(0, m), o, h, lo, c, v) for m, (o, h, lo, c, v) in enumerate((
            (2.77, 2.77, 2.76, 2.76, 960), (2.75, 2.75, 2.73, 2.74, 1258), (2.75, 2.75, 2.74, 2.74, 2283),
            (2.73, 2.73, 2.73, 2.73, 4812), (2.73, 2.73, 2.72, 2.72, 8186), (2.72, 2.73, 2.72, 2.73, 439),
            (2.73, 2.74, 2.73, 2.74, 4406), (2.76, 2.76, 2.75, 2.75, 2460), (2.75, 2.75, 2.74, 2.74, 114),
            (2.76, 2.76, 2.75, 2.75, 714), (2.75, 2.75, 2.75, 2.75, 3)), start=1)]
    lines: list[dict] = []
    clock = {"t": at(0, 0, 0.5)}
    eng = engine(tmp_path, universe=["SDEV"], seed=lambda s, since: [], clock=clock, setups=("red_to_green",),
                 journal=lines)
    tick(eng, clock, at(0, 0, 0.5))
    for t, o, h, lo, c, v in sdev:
        eng.on_l1_minute("bar", "SDEV", {"t": t, "o": o, "h": h, "l": lo, "c": c, "v": v})
        tick(eng, clock, t + 60.5)
    eng.on_l1_minute("last", "SDEV", {"price": 2.75, "ts": at(0, 12, 10), "bar_open": 2.75})
    tick(eng, clock, at(0, 12, 11))

    lane = eng.playing_lane("red_to_green")
    assert eng.bars["SDEV"].completed == []
    assert lane.rows == {} and lane.det["SDEV"].state == "watching"
    assert not any(ln["event"] in ("armed", "near") for ln in lines)


def test_the_seed_reads_the_session_only(monkeypatch):
    import bars_store
    from setup_scanner.hooks import default_seed

    asked: dict = {}

    def read(symbol, timeframe, limit, **kw):
        asked.update(symbol=symbol, timeframe=timeframe, limit=limit, **kw)
        return {"bars": []}

    monkeypatch.setattr(bars_store, "read", read)
    default_seed("QTEX", at(4, 0))
    # The newest 960 rows came first: QTEX's 2026-10-01 23:32 restart seed began at 07:27, its
    # morning pushed out by 207 overnight minutes.
    assert asked["from_ts"] == at(4, 0) and asked["through_ts"] == at(19, 59) and asked["limit"] == 960
