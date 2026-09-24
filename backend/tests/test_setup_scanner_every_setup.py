"""Every setup with a scanner runs on the same bars and tape (ADR 031): its own lane, its own
rows and read-out, and proposals only at Eyes."""
from __future__ import annotations

import asyncio
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from setup_scanner import readout, routes
from setup_scanner.engine import SetupEngine
from setup_scanner.store import SetupStore
from setup_templates.store import TemplateStore
from tests.setup_scanner_fixtures import add, base_morning
from tests.test_setup_scanner_engine import SYM, FakeTape, bar_msg

LEVELS = {"chosen": "first_pullback", "levels": {"first_pullback": 0, "bull_flag": 1, "flat_top_breakout": 0,
                                                  "red_to_green": 0}}


def flag_day():
    """A quiet morning, a three-candle pole to 4.35 on rising volume, then a two-candle flag."""
    bars = base_morning()
    for close, vol in ((4.10, 80_000), (4.22, 88_000), (4.34, 96_000)):
        o = bars[-1].c
        add(bars, o, close + 0.01, o - 0.01, close, vol)
    add(bars, 4.34, 4.34, 4.28, 4.29, 30_000)
    add(bars, 4.29, 4.30, 4.26, 4.27, 25_000)
    return bars


def make(tmp_path, bars, levels=LEVELS):
    audits: list[dict] = []
    clock = {"t": bars[-1].t + 30}
    eng = SetupEngine(store=SetupStore(tmp_path / "setups.db"), tape=FakeTape(), universe=lambda: [SYM],
                      seed=lambda sym, since: list(bars), replay_desk=lambda: False,
                      audit=lambda **kw: audits.append(kw), clock=lambda: clock["t"],
                      templates=lambda: TemplateStore(tmp_path / "t.json"), journal=lambda e: None,
                      levels=lambda: levels)
    eng.pillars = lambda sym, now: {"price": 4.3, "change_pct": 8.0, "rvol": 6.0, "float": 9e6, "news": None,
                                    "headline": None, "catalyst": None}
    return eng, audits, clock


def run(eng, now):
    asyncio.run(eng.tick(now))


def test_every_setup_gets_a_lane_and_a_card_on_the_board(tmp_path):
    eng, _, clock = make(tmp_path, flag_day())
    run(eng, clock["t"])
    assert [lane.setup for lane in eng.playing_lanes()] == [
        "first_pullback", "bull_flag", "flat_top_breakout", "red_to_green"]
    board = eng.board(clock["t"])
    assert board["schema_version"] == 2 and [s["id"] for s in board["setups"]] == [
        "first_pullback", "bull_flag", "flat_top_breakout", "red_to_green"]
    cards = {s["id"]: s for s in board["setups"]}
    assert cards["bull_flag"]["level"] == 1 and cards["bull_flag"]["proposing"] is True
    assert cards["first_pullback"]["level"] == 0 and cards["first_pullback"]["proposing"] is False
    assert cards["first_pullback"]["chosen"] is True and cards["bull_flag"]["chosen"] is False
    assert cards["red_to_green"]["window"] == {"start": "09:30", "end": "10:30", "state": "before"}
    assert cards["bull_flag"]["window"]["start"] == "07:00" and cards["bull_flag"]["window"]["state"] == "open"
    assert cards["bull_flag"]["template"]["id"] == "default" and cards["bull_flag"]["templates_watched"] == 1
    flag = [r for r in board["rows"] if r["setup_type"] == "bull_flag"]
    assert flag and flag[0]["state"] == "armed" and flag[0]["setup"]["trigger"] == 4.30
    assert cards["bull_flag"]["counts"]["armed"] == 1 and cards["bull_flag"]["counts"]["watching"] == 1


def test_a_setup_at_eyes_proposes_and_one_at_off_scores_in_silence(tmp_path):
    bars = flag_day()
    eng, audits, clock = make(tmp_path, bars)
    run(eng, clock["t"])
    eng.on_l1_minute("last", SYM, {"price": 4.29, "ts": clock["t"], "bar_open": 4.27})
    run(eng, clock["t"])
    props = eng.board(clock["t"])["proposals"]
    assert [p["setup_type"] for p in props] == ["bull_flag"] and props[0]["trigger"] == 4.30
    # The first pullback is near its own trigger with the tape at go too -- the flag is its shape --
    # but it is at Off: it scores, it does not propose.
    assert any(r["setup_type"] == "first_pullback" and r["state"] == "near" for r in eng.board(clock["t"])["rows"])
    assert all(a["inputs"]["setup_type"] == "bull_flag" for a in audits if a["action"] == "setup_proposal")
    (tmp_path / "off").mkdir()
    quiet, quiet_audits, qclock = make(tmp_path / "off", bars, levels={"chosen": "first_pullback", "levels": {}})
    run(quiet, qclock["t"])
    quiet.on_l1_minute("last", SYM, {"price": 4.29, "ts": qclock["t"], "bar_open": 4.27})
    run(quiet, qclock["t"])
    assert quiet.board(qclock["t"])["proposals"] == [] and quiet_audits == []


def test_rows_carry_their_setup_and_ids_name_it(tmp_path):
    eng, _, clock = make(tmp_path, flag_day())
    run(eng, clock["t"])
    rows = eng.store.rows(setup_type="bull_flag")
    assert rows and all(r["setup_type"] == "bull_flag" for r in rows)
    assert rows[0]["id"] == f"{SYM}-{eng.session}-{int(rows[0]['leg_t'])}@bull_flag"
    assert rows[0]["kind"] == "bull_flag" and rows[0]["detail"]["pole_bars"] == 3
    [fp] = eng.store.rows(setup_type="first_pullback")          # the same candles are a first pullback too
    assert "@" not in fp["id"] and fp["setup_type"] == "first_pullback" and fp["kind"] == "first_pullback"


def test_the_trigger_is_announced_with_its_setup(tmp_path):
    bars = flag_day()
    eng, _, clock = make(tmp_path, bars)
    heard: list[dict] = []
    eng.add_trigger_listener(heard.append)
    run(eng, clock["t"])
    nxt = add(list(bars), 4.28, 4.33, 4.27, 4.32, 60_000)[-1]
    clock["t"] = nxt.t + 5
    eng.on_l1_minute("last", SYM, {"price": 4.31, "ts": clock["t"], "bar_open": 4.28})
    run(eng, clock["t"])
    assert sorted(e["setup_type"] for e in heard) == ["bull_flag", "first_pullback"]
    flag_event = next(e for e in heard if e["setup_type"] == "bull_flag")
    assert flag_event["setup"]["kind"] == "bull_flag" and flag_event["setup_id"].endswith("@bull_flag")


def test_each_setup_has_its_own_readout(tmp_path, monkeypatch):
    store = SetupStore(tmp_path / "setups.db")
    t0 = 1_790_000_000.0
    for i in range(3):
        store.upsert({"id": f"X-{i}@bull_flag", "session_date": "2026-09-24", "symbol": "X", "kind": "bull_flag",
                      "setup_type": "bull_flag", "template_id": "default", "template_rev": 1, "risk": 0.1,
                      "triggered_at": t0 + i, "bar_r": 1.0, "trigger_tape": {"verdict": "go"}})

    class Eng:
        pass

    Eng.store, Eng.store_error = store, None
    monkeypatch.setattr("setup_scanner.engine.get_engine", lambda: Eng())
    from setup_templates.store import TemplateStore as TS, set_store_for_tests

    set_store_for_tests(TS(tmp_path / "t.json"))
    readout.reset_for_tests()
    bf = readout.current(setup="bull_flag", now=t0)
    fp = readout.current(setup="first_pullback", now=t0)
    assert bf["go"]["triggered"] == 3 and bf["rules"]["kind"] == "bull_flag"
    assert fp["go"]["triggered"] == 0 and fp["rules"]["kind"] == "first_pullback"


def test_the_scoreboard_answers_for_the_setup_named(tmp_path, monkeypatch):
    eng, _, clock = make(tmp_path, flag_day())
    run(eng, clock["t"])
    monkeypatch.setattr(routes, "get_engine", lambda: eng)
    from setup_templates.store import set_store_for_tests

    set_store_for_tests(TemplateStore(tmp_path / "t.json"))
    app = FastAPI()
    app.include_router(routes.router)
    c = TestClient(app)
    bf = c.get("/api/setups/scoreboard", params={"setup": "bull_flag", "days": 0}).json()
    assert bf["setup_type"] == "bull_flag" and bf["row_count"] == 1
    assert c.get("/api/setups/scoreboard", params={"days": 0}).json()["setup_type"] == "first_pullback"
    assert c.get("/api/setups/scoreboard", params={"setup": "gap_and_go"}).status_code == 404
    day = c.get("/api/setups/rows", params={"date": eng.session, "setup": "all"}).json()
    # The same candles are a bull flag, a first pullback and a flat-top base: each setup keeps its own row.
    assert sorted(r["setup_type"] for r in day["rows"]) == ["bull_flag", "first_pullback", "flat_top_breakout"]


def test_a_schema_2_scoreboard_is_migrated_and_its_rows_are_the_first_pullbacks(tmp_path):
    path = tmp_path / "setups.db"
    con = sqlite3.connect(path)
    con.executescript("CREATE TABLE setups (id TEXT PRIMARY KEY, session_date TEXT NOT NULL, symbol TEXT NOT NULL,"
                      " kind TEXT, armed_at REAL, template_id TEXT, template_rev INTEGER, params_hash TEXT);"
                      "INSERT INTO setups (id, session_date, symbol, kind, armed_at, template_id, template_rev)"
                      " VALUES ('OLD', '2026-09-23', 'X', 'first_pullback', 1, 'default', 1);")
    con.execute("PRAGMA user_version = 2")
    con.commit()
    con.close()
    store = SetupStore(path)
    [row] = store.rows()
    assert row["setup_type"] == "first_pullback" and row["detail"] is None
    assert sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0] == 3
    assert store.rows(setup_type="first_pullback")[0]["id"] == "OLD" and store.rows(setup_type="bull_flag") == []
