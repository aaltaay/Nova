"""A short setup's five-year test and its On lock (ADR 049 section 12), the read-out's SSR split and the
scoreboard's schema 6 (#778 step 4). Nova never writes a result: these tests write the harness's file."""
from __future__ import annotations

import json
import sqlite3
import time

import pytest

from bot.autonomy import apply_patch
from bot.errors import BotError
from bot.persist import load_session
from bot.session import get_session
from bot.setup_levels import effective, short_lock
from constants_bot import BOT_REASON_SHORT_TEST
from setup_scanner import readout, short_tests
from setup_scanner.store import COLUMNS, SetupStore, _type
from setup_templates.store import get_store

SETUP = "bear_flag"


def write_result(setup: str = SETUP, **over) -> dict:
    folder = short_tests.folder()
    folder.mkdir(parents=True, exist_ok=True)
    body = {
        "schema_version": 1, "setup": setup, "state": "passed", "started_at": 1.0, "updated_at": 2.0,
        "finished_at": 3.0, "harness": {"version": 1, "command": short_tests.SHORT_TEST_COMMAND.format(setup=setup)},
        "rules": {"template_id": "default", "template_rev": 1,
                  "rules_hash": get_store().in_play(setup).fingerprint},
        "data": {"first_day": "2021-10-01", "last_day": "2026-09-30", "days": 1255, "symbol_days": 9000},
        "assumptions": [], "progress": None, "main": {"trades": 412, "pf": 1.31, "exp_r": 0.12}, "ssr_days": None,
        "criteria": {"trades": {"value": 412, "ok": True}, "best_year_removed": {"ok": True},
                     "costs_2x": {"pf": 1.08, "ok": True}, "neighbourhood": {"ok": True},
                     "permutation": {"p": 0.01, "ok": True}},
        "passed": True, "error": None,
    }
    body.update(over)
    (folder / f"{setup}.json").write_text(json.dumps(body), encoding="utf-8")
    short_tests.reset_for_tests()
    return body


# -- the result as the cards read it --------------------------------------------------------------
def test_a_short_setups_test_is_queued_until_its_result_exists_and_a_long_has_none():
    got = short_tests.test_in_play(SETUP)
    assert got["state"] == "queued" and got["matches"] is None and got["summary"] is None
    assert "py -3 research/shorts/test_shorts.py --setup bear_flag" in got["text"]
    assert got["file"].endswith("bear_flag.json")
    assert short_tests.test_in_play("first_pullback") is None and short_lock("first_pullback") is None
    assert short_lock(SETUP).startswith("On waits on the bear flag five-year test: five-year test queued")


def test_a_running_test_says_how_far_it_got_and_when_it_may_have_stopped():
    now = time.time()
    write_result(state="running", passed=None, finished_at=None, updated_at=now - 60,
                 progress={"done": 300, "total": 1255}, main=None, criteria=None)
    got = short_tests.test_in_play(SETUP, now=now)
    assert got["state"] == "running" and got["text"] == "five-year test running: 300 of 1255 days"
    write_result(state="running", passed=None, finished_at=None, updated_at=now - 45 * 60,
                 progress={"done": 300, "total": 1255}, main=None, criteria=None)
    assert "no update for 45 min, so it may have stopped" in short_tests.test_in_play(SETUP, now=now)["text"]


def test_a_result_nova_cannot_read_never_unlocks_on():
    folder = short_tests.folder()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{SETUP}.json").write_text("{not json", encoding="utf-8")
    short_tests.reset_for_tests()
    assert short_tests.test_in_play(SETUP)["state"] == "error" and short_lock(SETUP)
    write_result(schema_version=2)
    got = short_tests.test_in_play(SETUP)
    assert got["state"] == "error" and "schema version 2" in got["text"] and short_lock(SETUP)
    write_result(passed=False)                         # says passed, but its own verdict disagrees
    assert short_tests.test_in_play(SETUP)["state"] == "error" and short_lock(SETUP)


def test_a_failed_test_reads_its_numbers_and_keeps_on_locked():
    write_result(state="failed", passed=False, main={"trades": 280, "pf": 0.91, "exp_r": -0.04})
    got = short_tests.test_in_play(SETUP)
    assert got["state"] == "failed" and got["summary"] == {"trades": 280, "pf": 0.91, "pf_2x": 1.08,
                                                           "exp_r": -0.04, "p": 0.01}
    assert got["text"] == "five-year test failed (280 trades, PF 0.91, -0.04R a trade)"
    assert "five-year test failed" in short_lock(SETUP)


def test_a_number_that_is_not_finite_never_reaches_the_wire():
    write_result(state="failed", passed=False, main={"trades": 1, "pf": float("inf"), "exp_r": 1.7})
    got = short_tests.test_in_play(SETUP)
    assert got["summary"]["pf"] is None and got["text"] == "five-year test failed (1 trade, +1.70R a trade)"


def test_a_result_file_is_named_only_by_a_known_short_setup():
    assert short_tests.path_of(SETUP).name == f"{SETUP}.json"
    for name in ("../../etc/passwd", "first_pullback", "", f"{SETUP}/../x"):
        with pytest.raises(ValueError):
            short_tests.path_of(name)
    assert short_tests.test("../x", "h") is None and short_tests.lock("../x", "h") is None


# -- the On lock ------------------------------------------------------------------------------------
def test_on_is_refused_until_the_test_passed_on_the_rules_in_play():
    with pytest.raises(BotError) as refused:
        apply_patch({"setup_levels": {SETUP: 2}}, desk=True)
    assert refused.value.status_code == 409 and refused.value.reason == BOT_REASON_SHORT_TEST
    assert "five-year test queued" in refused.value.message
    apply_patch({"setup_levels": {SETUP: 1}}, desk=True)            # Eyes is never locked
    assert load_session()["setup_levels"][SETUP] == 1

    write_result()
    assert short_lock(SETUP) is None
    apply_patch({"level": 2, "setup_levels": {SETUP: 2}}, desk=True)
    assert effective(load_session())[SETUP] == 2
    card = next(s for s in get_session()["setups"] if s["id"] == SETUP)
    assert card["side"] == "short" and card["test"]["state"] == "passed" and card["test"]["matches"] is True
    assert card["locked"] is None and card["effective"] == 2


def test_a_short_at_on_whose_test_stops_matching_reads_as_eyes():
    write_result()
    apply_patch({"level": 2, "setup_levels": {SETUP: 2}}, desk=True)
    write_result(rules={"template_id": "default", "template_rev": 1, "rules_hash": "0123456789ab"})
    assert effective(load_session())[SETUP] == 1
    card = next(s for s in get_session()["setups"] if s["id"] == SETUP)
    assert card["level"] == 2 and card["effective"] == 1 and card["test"]["matches"] is False
    assert "on other rules: the template in play has changed since" in card["locked"]
    long_card = next(s for s in get_session()["setups"] if s["id"] == "first_pullback")
    assert long_card["side"] == "long" and long_card["test"] is None and long_card["locked"] is None


# -- the read-out: a breakdown short is judged with SSR off ---------------------------------------------
def _row(i: int, ssr: str | None, verdict: str, r: float) -> dict:
    return {"id": f"X{i}", "kind": SETUP, "triggered_at": 1000.0 + i, "risk": 0.10, "bar_r": r,
            "bar_exit_reason": "stop", "trigger_tape": {"verdict": verdict}, "ssr": ssr}


def test_a_breakdown_shorts_readout_judges_the_triggers_with_ssr_off_and_counts_ssr_apart():
    rows = [_row(i, "off", "go", 1.0) for i in range(3)] + [_row(10, "on", "go", -1.0), _row(11, None, "go", -1.0),
                                                              _row(12, "unknown", "blind", -1.0)]
    out = readout.evaluate(rows, kind=SETUP, ssr_apart=True)
    assert out["go"]["triggered"] == 3 and out["go"]["avg_net_r"] == pytest.approx(0.8)   # 1R less two cents
    assert out["control"]["triggered"] == 0 and out["rules"]["ssr_apart"] is True
    assert out["ssr"]["triggered"] == 3 and out["ssr"]["avg_net_r"] < -1.0
    pooled = readout.evaluate(rows, kind=SETUP)            # the SSR bounce, and every long: one pool
    assert pooled["go"]["triggered"] == 5 and pooled["ssr"] is None and pooled["rules"]["ssr_apart"] is False


# -- the scoreboard: schema 6 -------------------------------------------------------------------------
def test_a_schema_5_scoreboard_migrates_and_its_rows_are_long(tmp_path):
    path = tmp_path / "setups.db"
    con = sqlite3.connect(path)
    v5 = [c for c in COLUMNS[3:] if c not in ("side", "ssr")]
    con.executescript("CREATE TABLE setups (id TEXT PRIMARY KEY, session_date TEXT NOT NULL, symbol TEXT NOT NULL, "
                      + ", ".join(f"{c} {_type(c)}" for c in v5) + ");"
                      "INSERT INTO setups (id, session_date, symbol, kind, armed_at) VALUES ('OLD', '2026-10-06', 'X',"
                      " 'first_pullback', 1);")
    con.execute("PRAGMA user_version = 5")
    con.commit()
    con.close()
    store = SetupStore(path)
    [row] = store.rows()
    assert row["side"] == "long" and row["ssr"] is None
    store.upsert({"id": "NEW", "session_date": "2026-10-07", "symbol": "FADE", "armed_at": 2.0, "side": "short",
                  "ssr": "off", "setup_type": SETUP})
    assert next(r for r in store.rows() if r["id"] == "NEW")["ssr"] == "off"
    assert sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0] == 6


# -- what price did after a short setup died (the past setups on the chart) ------------------------------
def test_a_short_episodes_aftermath_reads_the_breakdown_the_short_way():
    from eyes.aftermath import after
    from setup_scanner.bars import Bar

    t = 1_000_020.0 // 60 * 60
    bars = [Bar(t, 5.47, 5.47, 5.40, 5.41, 1),                    # the fade's candle: the leg's low 5.40
            Bar(t + 60, 5.42, 5.50, 5.42, 5.49, 1), Bar(t + 120, 5.49, 5.55, 5.47, 5.48, 1),
            Bar(t + 180, 5.48, 5.58, 5.46, 5.56, 1),              # it died on this one: the highest high 5.58
            Bar(t + 240, 5.50, 5.52, 5.35, 5.38, 1),              # then broke down under 5.40
            Bar(t + 300, 5.38, 5.39, 5.00, 5.02, 1)]
    ep = {"setup_type": "backside_lower_high", "setup": None, "leg": {"t": t, "high": 6.01, "low": 5.40},
          "died_at": t + 190, "died_bar_t": t + 180, "end": "failed"}
    got = after(ep, bars, now=t + 3600)
    assert got["first"] == "low" and got["crossed_at"] == t + 240
    assert got["level"] == 5.40 and got["entry"] == 5.39 and got["floor"] == 5.58
    assert got["high"] == 5.58 and got["low"] == 5.00 and got["price"] == 5.56
    trade = got["trade"]
    assert trade["entry"] == 5.39 and trade["stop"] == 5.58 and trade["risk"] == pytest.approx(0.19)
    assert trade["target"] == pytest.approx(5.01) and trade["outcome"] == "target_first"
    assert after({**ep, "setup_type": "ssr_bounce"}, bars, now=t + 3600) is None
