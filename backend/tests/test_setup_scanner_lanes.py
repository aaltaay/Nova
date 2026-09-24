"""One lane per first-pullback template (ADR 029): every template watches the same
bars and tape and scores its own rows; only the template in play proposes; a
stock filter keeps setups out on the record; the read-out is per template."""
from __future__ import annotations

import asyncio
import random
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from setup_scanner.bars import Bar
from setup_scanner.engine import SetupEngine
from setup_scanner.pullback import PullbackDetector, PullbackParams
from setup_scanner.series import Series, ema, macd_hist
from setup_scanner.store import SetupStore
from setup_templates.store import TemplateStore
from tests.setup_scanner_fixtures import add, base_morning, leg_up
from tests.test_setup_scanner_engine import SYM, FakeTape, bar_msg

FP = "first_pullback"
ET = ZoneInfo("America/New_York")
PILLARS = {"price": 4.35, "change_pct": 40.0, "rvol": 8.0, "float": 30_000_000.0, "news": None,
           "headline": None, "catalyst": None}


def make(tmp_path, bars, templates: TemplateStore):
    audits, journal = [], []
    clock = {"t": bars[-1].t + 30}
    eng = SetupEngine(store=SetupStore(tmp_path / "setups.db"), tape=FakeTape(), universe=lambda: [SYM],
                      seed=lambda sym, since: list(bars), replay_desk=lambda: False,
                      audit=lambda **kw: audits.append(kw), clock=lambda: clock["t"], templates=lambda: templates,
                      journal=journal.append, bot_state=lambda: {"level": 1, "active": True, "venue": "paper"})
    eng.pillars = lambda sym, now: dict(PILLARS)
    return eng, audits, journal, clock


def armed_bars():
    return add(leg_up(base_morning(), [4.08, 4.18, 4.28, 4.38]), 4.38, 4.37, 4.30, 4.32, 30_000)


def run(eng, now):
    asyncio.run(eng.tick(now))


def test_every_template_scores_but_only_the_one_in_play_proposes(tmp_path):
    templates = TemplateStore(tmp_path / "t.json")
    wide = templates.create(FP, name="Wide stop", values={"stop_cap": 0.5})
    eng, audits, journal, clock = make(tmp_path, armed_bars(), templates)
    run(eng, clock["t"])
    assert [lane.p.template_id for lane in eng.lanes] == ["default", wide.id]
    assert eng.playing.p.template_id == "default"
    eng.on_l1_minute("last", SYM, {"price": 4.35, "ts": clock["t"], "bar_open": 4.32})
    run(eng, clock["t"])
    other = eng.lanes[1]
    assert len(eng.proposals) == 1 and other.proposals == {}
    assert other.det[SYM].state == "near" and other.tape_view[SYM]["verdict"] == "go"
    rows = eng.store.rows()
    assert {(r["template_id"], r["template_rev"]) for r in rows} == {("default", 1), (wide.id, 1)}
    key = f"{SYM}-{eng.session}-{int(rows[0]['leg_t'])}"
    assert {r["id"] for r in rows} == {key, f"{key}~{wide.id}"}   # the default's ids are unchanged
    assert all(r["params_hash"] for r in rows)
    armed = [e for e in journal if e["event"] == "armed"]
    assert {e["template"] for e in armed} == {"default", wide.id}
    assert all(e["bot"] == {"level": 1, "active": True, "venue": "paper"} and e["source"] == "live" for e in armed)
    assert any(e["event"] == "proposal" and e["status"] == "proposed" and e["template"] == "default" for e in journal)
    assert audits and all(a["inputs"]["template_id"] == "default" for a in audits)


def test_putting_another_template_in_play_withdraws_the_open_proposal(tmp_path):
    templates = TemplateStore(tmp_path / "t.json")
    other = templates.create(FP, name="Other")
    eng, audits, journal, clock = make(tmp_path, armed_bars(), templates)
    run(eng, clock["t"])
    eng.on_l1_minute("last", SYM, {"price": 4.35, "ts": clock["t"], "bar_open": 4.32})
    run(eng, clock["t"])
    first = next(iter(eng.proposals.values()))
    templates.play(FP, other.id)
    run(eng, clock["t"] + 1)
    assert first["status"] == "template"
    assert eng.playing.p.template_id == other.id
    # The new template in play reads go on the same near setup and proposes on its own levels.
    assert [p["template_id"] for p in eng.board(clock["t"] + 1)["proposals"]] == [other.id]
    assert eng.board(clock["t"] + 1)["template"]["id"] == other.id


def test_editing_a_template_starts_a_new_lane_for_its_new_rules(tmp_path):
    templates = TemplateStore(tmp_path / "t.json")
    t = templates.create(FP, name="Mine")
    eng, _, journal, clock = make(tmp_path, armed_bars(), templates)
    run(eng, clock["t"])
    templates.update(FP, t.id, values={"leg_pct": 6})
    run(eng, clock["t"] + 1)
    assert [(lane.p.template_id, lane.p.template_rev) for lane in eng.lanes] == [("default", 1), (t.id, 2)]
    lanes_events = [e for e in journal if e["event"] == "lanes"]
    assert len(lanes_events) == 2 and lanes_events[-1]["lanes"][1]["rev"] == 2


def test_a_stock_filter_keeps_the_setup_out_on_the_record(tmp_path):
    templates = TemplateStore(tmp_path / "t.json")
    lf = templates.create(FP, name="Low float", values={"max_float_m": 10})
    templates.play(FP, lf.id)
    eng, audits, journal, clock = make(tmp_path, armed_bars(), templates)
    run(eng, clock["t"])
    eng.on_l1_minute("last", SYM, {"price": 4.35, "ts": clock["t"], "bar_open": 4.32})
    run(eng, clock["t"])
    row = eng.board(clock["t"])["rows"][0]
    assert row["state"] == "filtered" and "float 30.0M over 10.0M" in row["reason"]
    assert eng.proposals == {} and audits == []
    assert eng.playing.watching() == set()
    assert [r["template_id"] for r in eng.store.rows()] == ["default"]     # the filtered setup is not scored
    filtered = [e for e in journal if e["event"] == "filtered"]
    assert len(filtered) == 1 and filtered[0]["template"] == lf.id


def test_the_read_out_counts_only_its_own_template_rows(tmp_path, monkeypatch):
    from setup_scanner import readout

    store = SetupStore(tmp_path / "setups.db")
    t0 = 1_790_000_000.0
    for i in range(3):
        store.upsert({"id": f"A{i}", "session_date": "2026-09-23", "symbol": "X", "kind": "first_pullback",
                      "triggered_at": t0 + i, "trigger_tape": {"verdict": "go"}, "bar_r": 1.0, "risk": 0.2,
                      "template_id": "default", "template_rev": 1})
    store.upsert({"id": "B0", "session_date": "2026-09-23", "symbol": "X", "kind": "first_pullback",
                  "triggered_at": t0, "trigger_tape": {"verdict": "go"}, "bar_r": 1.0, "risk": 0.2,
                  "template_id": "t-other", "template_rev": 2})

    class Eng:
        pass

    Eng.store, Eng.store_error = store, None
    monkeypatch.setattr("setup_scanner.engine.get_engine", lambda: Eng())
    readout.reset_for_tests()
    out = readout.current(now=t0)
    assert out["go"]["triggered"] == 3 and out["rules"]["template"] == {"id": "default", "rev": 1,
                                                                       "name": "Default (pre-registered)"}


def test_a_v1_scoreboard_is_migrated_and_its_rows_become_the_default_templates(tmp_path):
    path = tmp_path / "setups.db"
    con = sqlite3.connect(path)
    con.executescript("CREATE TABLE setups (id TEXT PRIMARY KEY, session_date TEXT NOT NULL, symbol TEXT NOT NULL,"
                      " kind TEXT, triggered_at REAL, bar_r REAL, risk REAL, trigger_tape TEXT, armed_at REAL);"
                      "INSERT INTO setups (id, session_date, symbol, kind, armed_at) VALUES"
                      " ('OLD', '2026-09-22', 'X', 'first_pullback', 1);")
    con.execute("PRAGMA user_version = 1")
    con.commit()
    con.close()
    store = SetupStore(path)
    row = store.rows()[0]
    assert (row["template_id"], row["template_rev"]) == ("default", 1) and row["params_hash"]
    assert sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0] == 2
    assert store.rows(template_id="default", template_rev=1)[0]["id"] == "OLD"


def test_series_extends_exactly_as_a_full_recomputation():
    rng = random.Random(7)
    bars, px = [], 4.0
    for i in range(300):
        o = px
        px = max(0.5, px + rng.uniform(-0.05, 0.06))
        bars.append(Bar(1_790_000_000 + 60 * i, o, max(o, px) + 0.01, min(o, px) - 0.01, px, 1000))
    s = Series(ema_period=9)
    for n in range(1, len(bars) + 1):
        s.update(bars[:n])
    closes = [b.c for b in bars]
    assert s.e == ema(closes, 9) and s.hist == macd_hist(closes)
    assert all(s.hod[i] == max(b.h for b in bars[: i + 1]) for i in range(len(bars)))
    s.update(bars[1:])                    # a different first bar: rebuilt, not extended
    assert s.e == ema(closes[1:], 9)


def test_at_most_the_days_setups_trigger_on_one_symbol():
    det = PullbackDetector("ABCD", p=PullbackParams(max_per_symbol_day=1))
    bars = armed_bars()
    det.on_bars(bars)
    assert det.state == "armed"
    det.on_price(4.38, bars[-1].t + 70)
    assert det.state == "triggered" and det.nth == 1
    more = leg_up(list(bars), [4.45, 4.55, 4.65])
    assert det.on_bars(more) == [] and det.state == "triggered"


def test_a_fixed_target_is_entry_plus_the_amount():
    det = PullbackDetector("ABCD", p=PullbackParams(target_mode="fixed", target_fixed=0.20))
    det.on_bars(armed_bars())
    assert det.armed["target1"] == round(det.armed["entry"] + 0.20, 4)


def test_the_bot_window_and_daily_cap_come_from_the_template_in_play(tmp_path):
    from bot import entry_rules
    from bot.errors import BotError
    from setup_templates.store import set_store_for_tests

    templates = TemplateStore(tmp_path / "t.json")
    set_store_for_tests(templates)
    t = templates.create(FP, name="Late", values={"bot_window_start": "09:30", "bot_window_end": "11:00",
                                                  "bot_entries_per_day": 2})
    templates.play(FP, t.id)
    at = datetime(2026, 9, 23, 10, 30, tzinfo=ET)
    entry_rules.set_clock_for_tests(lambda: at)
    status = entry_rules.status(at)
    assert (status["start"], status["end"], status["max_entries"], status["open"]) == ("09:30", "11:00", 2, True)
    assert status["template"]["id"] == t.id
    entry_rules.set_clock_for_tests(lambda: datetime(2026, 9, 23, 11, 5, tzinfo=ET))
    with pytest.raises(BotError) as err:
        entry_rules.assert_entry_allowed("buy_market")
    assert err.value.reason == "BOT_OUTSIDE_WINDOW" and "09:30-11:00" in err.value.message


def test_the_scoreboard_answers_for_the_template_in_play_unless_asked(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import setup_scanner.routes as routes
    from setup_templates.store import set_store_for_tests

    templates = TemplateStore(tmp_path / "t.json")
    set_store_for_tests(templates)
    wide = templates.create(FP, name="Wide stop", values={"stop_cap": 0.5})
    eng, _, _, clock = make(tmp_path, armed_bars(), templates)
    run(eng, clock["t"])
    monkeypatch.setattr(routes, "get_engine", lambda: eng)
    app = FastAPI()
    app.include_router(routes.router)
    c = TestClient(app)
    mine = c.get("/api/setups/scoreboard", params={"days": 0}).json()
    assert mine["row_count"] == 1 and mine["template"] == {"id": "default", "rev": 1, "name": "Default (pre-registered)"}
    assert c.get("/api/setups/scoreboard", params={"days": 0, "template": "all"}).json()["row_count"] == 2
    other = c.get("/api/setups/scoreboard", params={"days": 0, "template": wide.id}).json()
    assert other["row_count"] == 1 and other["rows"][0]["template_id"] == wide.id
    assert c.get("/api/setups/scoreboard", params={"template": "t-nope"}).status_code == 404
    day = other["rows"][0]["session_date"]
    assert len(c.get("/api/setups/rows", params={"date": day}).json()["rows"]) == 1
