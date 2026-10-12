"""Every target choice scored side by side on each trigger, stored with it, and ranked (#845, operator ask
2026-10-12); the stores that keep the targets (setups.db schema 7, setup-templates.json schema 2)."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from constants_setups import SETUP_TEMPLATES_SCHEMA_VERSION, SETUPS_DB_SCHEMA_VERSION
from eyes.target_readout import rank, table
from setup_scanner.store import SetupStore
from setup_scanner.target_choices import NAMES
from setup_templates.store import TemplateStore
from tests.setup_scanner_fixtures import add
from tests.test_setup_scanner_engine import SYM, bar_msg
from tests.test_setup_scanner_lanes import armed_bars, make, run

REPO = Path(__file__).resolve().parents[2]


def _triggered(tmp_path):
    bars = armed_bars()
    eng, _audits, journal, clock = make(tmp_path, bars, TemplateStore(tmp_path / "t.json"))
    run(eng, clock["t"])
    eng.on_l1_minute("last", SYM, {"price": 4.35, "ts": clock["t"], "bar_open": 4.32})
    run(eng, clock["t"])
    clock["t"] += 2
    eng.on_l1_minute("last", SYM, {"price": 4.38, "ts": clock["t"], "bar_open": 4.32})
    run(eng, clock["t"])
    return eng, journal, clock, bars


def _row(eng):
    return next(r for r in eng.store.rows() if r.get("template_id") == "default" and r.get("triggered_at"))


def test_a_trigger_carries_both_targets_and_every_choice_side_by_side(tmp_path):
    eng, _journal, _clock, _bars = _triggered(tmp_path)
    row = _row(eng)
    # The template's own: 1c under $4.50 (11c over the 4.38 entry), the rest 1c under the next level past it.
    assert (row["entry"], row["stop"], row["target1"], row["target1_fraction"]) == (4.38, 4.30, 4.49, 0.5)
    assert row["target2"] == 4.99 and row["targets"]["first"]["why"] == "1c under $4.50"
    scores = row["target_scores"]
    assert scores["schema_version"] == 1 and list(scores["choices"]) == list(NAMES)
    c = scores["choices"]
    assert [c[n]["target1"] for n in ("fixed_10c", "fixed_20c", "fixed_30c")] == [4.48, 4.58, 4.68]
    assert c["default"]["target1"] == 4.49 and c["default"]["target2"] == 4.99 and c["default"]["target1_fraction"] == 0.5
    assert c["hod"]["fell_back"] is True and c["hod"]["target1"] == 4.58      # the high of day is no target here
    assert all(v["bar_r"] is None for v in c.values())                         # nothing has closed yet


def test_each_choice_is_scored_on_the_same_stop_until_every_one_closes(tmp_path):
    eng, journal, clock, bars = _triggered(tmp_path)
    t0 = bars[-1].t + 60                                         # the trigger's minute
    for o, h, lo, c in ((4.32, 4.40, 4.31, 4.39),                # the entry candle: closes over the stop
                        (4.39, 4.50, 4.37, 4.47),                # +10c sells; the default's half at 4.49
                        (4.47, 4.48, 4.25, 4.27)):               # the stop: everything else out at 4.30
        add(bars, o, h, lo, c, 20_000)
        eng.on_l1_minute("bar", SYM, bar_msg(bars[-1]))
        clock["t"] = bars[-1].t + 61
        run(eng, clock["t"])
    assert bars[-3].t == t0
    c = _row(eng)["target_scores"]["choices"]
    assert (c["fixed_10c"]["bar_r"], c["fixed_10c"]["exit_reason"]) == (1.25, "target")
    assert (c["default"]["bar_r"], c["default"]["exit_reason"]) == (pytest.approx(0.188, abs=1e-3), "stop_runner")
    assert (c["fixed_20c"]["bar_r"], c["fixed_20c"]["exit_reason"]) == (-1.0, "stop")
    row = _row(eng)
    assert row["bar_r"] == c["default"]["bar_r"] and row["bar_exit_reason"] == "stop_runner"   # the template's own
    said = [e for e in journal if e["event"] == "target_scores"]
    assert len(said) == 1 and said[0]["scores"]["choices"]["fixed_30c"]["exit_reason"] == "stop"
    lane = next(lane for lane in eng.lanes if lane.p.template_id == "default")
    assert lane.choices == {}                                    # every choice closed: nothing left to feed


# -- the read-out ------------------------------------------------------------------------------------------------
def _scored(i: int, **r) -> dict:
    choices = {n: {"bar_r": r.get(n, -1.0), "exit_reason": "stop", "fell_back": n == "hod"} for n in NAMES}
    return {"triggered_at": 1.0 + i, "risk": 0.10, "target_scores": {"schema_version": 1, "risk": 0.10,
                                                                     "choices": choices}}


def test_the_readout_ranks_by_net_r_and_names_no_leader_under_its_minimum():
    rows = [_scored(i, fixed_10c=0.5, default=1.0) for i in range(5)] + [{"triggered_at": None}]
    got = rank(rows, cost=0.01, min_n=30)
    assert got["triggers"] == 5 and got["leader"] is None and "fewest scored triggers of a choice is 5" in got["note"]
    first = got["choices"][0]
    assert first["name"] == "default" and first["n"] == 5 and first["win_pct"] == 100.0
    assert first["mean_r"] == 1.0 and first["sum_r"] == 5.0 and first["mean_net_r"] == pytest.approx(0.8)
    assert next(c for c in got["choices"] if c["name"] == "hod")["fell_back"] == 5
    assert rank(rows, min_n=5)["leader"] == "default"
    text = table(got)
    assert "default" in text and "No leader" in text and "cost 0.01" in text


def test_rows_without_scores_or_of_another_schema_are_left_out():
    old = {"triggered_at": 1.0, "risk": 0.1, "target_scores": {"schema_version": 99, "choices": {}}}
    assert rank([old, {"triggered_at": 2.0, "bar_r": 1.0}])["triggers"] == 0


def test_the_tool_reads_setups_db_from_a_date(tmp_path):
    db = tmp_path / "setups.db"
    store = SetupStore(db)
    for i in range(3):
        store.upsert({"id": f"X-{i}", "session_date": "2026-10-13", "symbol": "X", "armed_at": float(i),
                      "setup_type": "first_pullback", "template_id": "default", "template_rev": 1,
                      **_scored(i, default=2.0)})
    store.close()
    out = subprocess.run([sys.executable, str(REPO / "tools/target_readout.py"), "--from", "2026-10-13", "--db",
                          str(db), "--template", "all", "--json"], capture_output=True, text=True, check=True)
    got = json.loads(out.stdout)
    assert got["triggers"] == 3 and got["choices"][0]["name"] == "default" and got["leader"] is None


def test_the_route_ranks_the_template_in_plays_triggers_from_a_date(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import setup_scanner.routes as routes
    from setup_templates.store import set_store_for_tests

    eng, _journal, _clock, _bars = _triggered(tmp_path)
    set_store_for_tests(TemplateStore(tmp_path / "t.json"))
    try:
        monkeypatch.setattr(routes, "get_engine", lambda: eng)
        app = FastAPI()
        app.include_router(routes.router)
        c = TestClient(app)
        day = _row(eng)["session_date"]
        got = c.get("/api/setups/target-choices", params={"from": day, "min_n": 1}).json()
        assert got["from"] == day and got["setup_type"] == "first_pullback" and got["triggers"] == 1
        assert got["template"]["id"] == "default" and {ch["name"] for ch in got["choices"]} == set(NAMES)
        assert got["scored"] == 0 and got["leader"] is None             # nothing closed yet: no leader
        assert c.get("/api/setups/target-choices", params={"from": day, "setup": "all"}).json()["triggers"] == 1
        assert c.get("/api/setups/target-choices", params={"from": "today"}).status_code == 422
    finally:
        set_store_for_tests(None)


# -- the stores ------------------------------------------------------------------------------------------------
def test_a_schema_6_scoreboard_migrates_and_its_rows_sold_whole_at_target_1(tmp_path):
    from setup_scanner import store as setups_store

    path = tmp_path / "setups.db"
    v6 = [c for c in setups_store.COLUMNS[3:] if c not in setups_store._V7_COLUMNS]
    con = sqlite3.connect(path)
    con.executescript("CREATE TABLE setups (id TEXT PRIMARY KEY, session_date TEXT NOT NULL, symbol TEXT NOT NULL, "
                      + ", ".join(f"{c} {setups_store._type(c)}" for c in v6) + ");"
                      "INSERT INTO setups (id, session_date, symbol, target1, armed_at) "
                      "VALUES ('OLD', '2026-10-09', 'X', 4.54, 1.0);")
    con.execute("PRAGMA user_version = 6")
    con.commit()
    con.close()
    store = SetupStore(path)
    [row] = store.rows()
    assert row["target1_fraction"] == 1.0 and row["target2"] is None and row["target_scores"] is None
    assert sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0] == SETUPS_DB_SCHEMA_VERSION == 7


def test_a_schema_1_template_file_moves_to_the_menu_and_says_so(tmp_path):
    path = tmp_path / "setup-templates.json"
    base = {"stop_cap": 0.2}
    path.write_text(json.dumps({"schema_version": 1, "setups": {"first_pullback": {"in_play": "t-fix", "templates": [
        {"id": "t-fix", "name": "Fixed", "rev": 3, "values": {**base, "target_mode": "fixed", "target_fixed": 0.5,
                                                               "target_r": 2.0}},
        {"id": "t-leg", "name": "Leg", "rev": 1, "values": {**base, "target_mode": "leg_or_r", "target_r": 3.0}}]}}}),
        encoding="utf-8")
    store = TemplateStore(path)
    fixed, leg = (store.get("first_pullback", i) for i in ("t-fix", "t-leg"))
    assert store.error() is None and fixed.error is None and leg.error is None
    assert (fixed.rev, fixed.values["target1_kind"], fixed.values["target_fixed"]) == (4, "fixed", 0.3)
    assert "it was $0.5: the menu's fixed amount is 10-30c" in fixed.migrated
    assert (leg.rev, leg.values["target1_kind"], leg.values["target2_kind"]) == (2, "round_or_fixed", "hod_or_level")
    assert "target 1 = leg_or_r at 3R became the menu's default targets" in leg.migrated
    assert "target_mode" not in leg.values and leg.wire(in_play=False)["migrated"] == leg.migrated
    store.update("first_pullback", "t-leg", name="Leg 2")                 # a rename keeps the note
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["schema_version"] == SETUP_TEMPLATES_SCHEMA_VERSION == 2
    stored = {t["id"]: t for t in saved["setups"]["first_pullback"]["templates"]}
    assert "target_mode" not in stored["t-leg"]["values"] and stored["t-leg"]["migrated"] == leg.migrated
    edited, _ = store.update("first_pullback", "t-leg", values={"target_fixed": 0.15})
    assert edited.migrated is None                                         # saving its values clears it


def test_a_write_naming_the_old_target_is_refused_with_where_it_went(tmp_path):
    from setup_templates.catalogue import TemplateError

    store = TemplateStore(tmp_path / "t.json")
    with pytest.raises(TemplateError) as err:
        store.create("first_pullback", name="Old", values={"target_r": 2.0})
    assert err.value.field == "target_r" and "target1_kind" in err.value.message
