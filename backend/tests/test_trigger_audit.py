"""The squares, by ticker (ADR 043): ``GET /api/bot/triggers``.

A day's eyes' journal, the bot's audit stream and the day's hot list are written as Nova writes them;
every trigger is judged by the ten gates in Nova's order from what was recorded at it, the gates nothing
recorded are named in ``judged_now``, and each gate's effect is summed in ``impact``.
"""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from bot.persist import append_audit_line
from bot.trigger_timeline import UNKNOWN, Timeline
from constants_eyes import EYES_SCHEMA_VERSION
from main import app

ET = ZoneInfo("America/New_York")
DAY = "2026-09-30"
GATES = ["bot_on", "strategy_on", "grade", "setups_a_day", "bot_window", "hot_list", "nova_buys", "level2_line",
         "tape_go", "trades_today"]
client = TestClient(app)


def at(hour: int, minute: int, second: int = 0, day: str = DAY) -> float:
    d = datetime.fromisoformat(day)
    return datetime(d.year, d.month, d.day, hour, minute, second, tzinfo=ET).timestamp()


# -- the files, as Nova writes them -------------------------------------------------------------
def write_journal(lines: list[dict], day: str = DAY) -> None:
    from eyes.journal import journal_dir

    folder = journal_dir()
    folder.mkdir(parents=True, exist_ok=True)
    rows = [{"schema_version": EYES_SCHEMA_VERSION, "wall_ts": line["ts"], "date": day, "source": "live", **line}
            for line in lines]
    (folder / f"{day}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def write_audit(rows: list[dict]) -> None:
    for row in rows:
        append_audit_line({"level": 2, "strategy": None, "brain_session_id": None, "reason": None,
                           "order_id": None, "advise_spend": None, **row})


def write_hot_list(entries: list[dict], day: str = DAY) -> None:
    from constants_hot_list import HOT_LIST_DAY_DIR
    from paths import cache_dir

    folder = cache_dir() / HOT_LIST_DAY_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{day}.json").write_text(json.dumps({
        "schema_version": 1, "date": day, "auto_n": 5, "default": {"buy": "you", "sell": "you"},
        "entries": entries, "yesterday": []}), encoding="utf-8")


BOT_ON = {"level": 2, "active": True, "venue": "paper"}


def triggered(sym: str, sid: str, ts: float, *, setup_type: str = "first_pullback", kind: str = "first_pullback",
              nth: int = 1, verdict: str = "go", reasons: list[str] | None = None, depth: bool = True,
              bot: dict | None = None, playing: bool = True, wall: float | None = None) -> dict:
    return {"ts": wall or ts, "event": "triggered", "symbol": sym, "setup_id": sid, "setup_type": setup_type,
            "template": "default", "rev": 1, "playing": playing, "bot": bot or BOT_ON,
            "setup": {"kind": kind, "nth": nth, "entry": 10.02, "stop": 9.88, "risk": 0.14, "trigger": 10.01,
                      "triggered_at": ts},
            "tape": {"verdict": verdict, "reasons": reasons or ["green on the tape"],
                     "metrics": {"spread": 0.02}, "line": {"depth": depth, "tape": True}},
            "liquidity": {"state": "ok", "reasons": []}}


def armed(sym: str, sid: str, ts: float, grade: str, setup_type: str = "first_pullback") -> dict:
    return {"ts": ts, "event": "armed", "symbol": sym, "setup_id": sid, "setup_type": setup_type,
            "template": "default", "playing": True, "bot": BOT_ON, "grade": grade}


def scored(sym: str, sid: str, ts: float, outcome: str, r: float) -> dict:
    return {"ts": ts, "event": "scored", "symbol": sym, "setup_id": sid, "template": "default", "playing": True,
            "outcome": outcome, "bar_r": r}


@pytest.fixture
def day(monkeypatch):
    """2026-09-30 on Paper: AISP set to Bot at 07:10, the first pullback On from 07:20, the 04:00 rollover,
    a restart at 11:00, and five triggers (one said twice by the restart's warm-up)."""
    from sim.mode import set_venue

    set_venue("paper", persist=False)
    write_audit([
        {"timestamp": at(4, 0, 5), "venue": "paper", "action": "hot_list", "outcome": "rollover",
         "inputs": {"event": "rollover", "cleared": ["OLD"]}},
        {"timestamp": at(7, 10), "venue": "paper", "action": "stock_mode", "outcome": "set",
         "inputs": {"symbol": "AISP", "from": "signal", "to": "bot"}},
        {"timestamp": at(7, 20), "venue": "paper", "action": "setup_level", "outcome": "first_pullback:1->2",
         "inputs": {"setup": "first_pullback", "from": 1, "to": 2}},
    ])
    write_hot_list([
        {"symbol": "AISP", "how": "star", "at": at(7, 5), "board": None, "rank": None, "change_pct": None},
        {"symbol": "LGHL", "how": "auto", "at": at(7, 30), "board": "gainers", "rank": 2, "change_pct": 41.0},
        {"symbol": "WHLR", "how": "star", "at": at(10, 30), "board": None, "rank": None, "change_pct": None},
    ])
    write_journal([
        {"ts": at(4, 0, 1), "event": "session", "symbol": None, "bot": BOT_ON},
        triggered("LGHL", "LGHL-1", at(7, 16, 10), verdict="wait", reasons=["burst of red"],
                  bot={"level": 1, "active": False, "venue": "paper"}),
        armed("LGHL", "LGHL-1", at(7, 12), "A"),
        scored("LGHL", "LGHL-1", at(7, 17), "target_first", 1.0),
        armed("AISP", "AISP-1", at(9, 35), "A"),
        triggered("AISP", "AISP-1", at(9, 41)),
        scored("AISP", "AISP-1", at(9, 50), "target_first", 1.5),
        armed("AISP", "AISP-BF", at(9, 44), "B", setup_type="bull_flag"),
        triggered("AISP", "AISP-BF", at(9, 50), setup_type="bull_flag", kind="bull_flag"),
        scored("AISP", "AISP-BF", at(9, 58), "stop_first", -1.0),
        triggered("ZZZZ", "ZZZZ-R2G", at(9, 45), setup_type="red_to_green", kind="red_to_green", verdict="veto",
                  reasons=["a seller of 60,000 at 10.05"]),
        armed("ZZZZ", "ZZZZ-R2G", at(9, 40), "C", setup_type="red_to_green"),
        armed("AISP", "AISP-2", at(10, 15), "A"),
        triggered("AISP", "AISP-2", at(10, 22), kind="second_pullback", nth=2, verdict="blind",
                  reasons=["no book"], depth=False),
        scored("AISP", "AISP-2", at(10, 40), "target_first", 2.0),
        triggered("AISP", "AISP-1", at(9, 41), wall=at(11, 0, 30)),                # the restart's warm-up
        triggered("AISP", "AISP-X~t-1", at(9, 41), playing=False),                 # a template not in play
        {"ts": at(11, 0), "event": "session", "symbol": None, "bot": BOT_ON},
    ])
    yield
    from bot import trigger_inputs

    trigger_inputs.reset_for_tests()


def get(day_: str = DAY) -> dict:
    res = client.get(f"/api/bot/triggers?date={day_}")
    assert res.status_code == 200, res.text
    return res.json()


def by_symbol(body: dict) -> dict[str, dict]:
    return {t["symbol"]: t for t in body["tickers"]}


def oks(cells: dict) -> list:
    return [cells[g]["ok"] for g in GATES]


# -- the answer -----------------------------------------------------------------------------------
def test_the_shape_the_gates_and_the_sources(day):
    body = get()
    assert body["schema_version"] == 1 and body["date"] == DAY
    assert [g["id"] for g in body["gates"]] == GATES
    assert [g["label"] for g in body["gates"]][:2] == ["Bot on", "Strategy on"]
    assert body["judged_now"] == ["grade", "setups_a_day", "bot_window"]
    assert body["sources"] == {"journal": {"ok": True, "error": None}, "audit": {"ok": True, "error": None},
                               "hot_list": {"ok": True, "error": None}}
    assert [t["symbol"] for t in body["tickers"]] == ["AISP", "LGHL", "WHLR", "ZZZZ"]   # listed first, then the rest
    tickers = by_symbol(body)
    assert tickers["AISP"]["listed"] == {"how": "star", "at": at(7, 5)}
    assert tickers["ZZZZ"]["listed"] is None and tickers["WHLR"]["triggers"] == []
    assert all(t["now"] is None for t in body["tickers"])              # a past day has no "now"


def test_a_trigger_that_passes_every_gate_takes_the_days_cap(day):
    aisp = by_symbol(get())["AISP"]["triggers"]
    assert [t["setup_id"] for t in aisp] == ["AISP-1", "AISP-BF", "AISP-2"]     # once each, oldest first
    first = aisp[0]
    assert first["ts"] == at(9, 41) and first["grade"] == "A" and first["tape"] == "go"
    assert first["outcome"] == "target_first" and first["r"] == 1.5 and first["nth"] == 1
    assert oks(first["cells"]) == [True] * 10 and first["reasons"] == []
    assert first["cells"]["trades_today"]["why"].startswith("it takes Nova's 1st entry of the day")
    assert first["cells"]["nova_buys"]["why"].startswith("Buy was Nova (Bot")


def test_each_red_square_says_why(day):
    aisp = by_symbol(get())["AISP"]["triggers"]
    bull, second = aisp[1], aisp[2]
    assert bull["cells"]["strategy_on"] == {"ok": False, "why": "the bull flag was Off: Nova buys only the "
                                                                 "strategies that are On"}
    assert bull["cells"]["grade"]["ok"] is True                         # B, and the bull flag buys A and B
    assert bull["cells"]["trades_today"] == {"ok": False, "why": "the day's 1 Nova entry went to AISP at 09:41 ET"}
    cells = second["cells"]
    assert cells["setups_a_day"] == {"ok": False, "why": "a 2nd first pullback: this strategy buys the 1st of "
                                                          "the day only"}
    assert cells["bot_window"] == {"ok": False, "why": "10:22 ET, outside the 07:00-10:00 bot window"}
    assert cells["level2_line"] == {"ok": False, "why": "BLIND: no book"}
    assert cells["tape_go"]["ok"] is None                               # BLIND is the line's red, never the tape's
    assert second["reasons"][0].startswith("a 2nd first pullback")


def test_what_was_set_at_the_trigger_is_read_from_the_records(day):
    lghl = by_symbol(get())["LGHL"]["triggers"][0]
    cells = lghl["cells"]
    assert cells["bot_on"] == {"ok": False, "why": "the bot was off (at Eyes)"}
    assert cells["strategy_on"]["ok"] is False and "at Eyes" in cells["strategy_on"]["why"]   # before 07:20
    assert cells["hot_list"] == {"ok": False, "why": "listed by the leaders rule at 07:30 ET, after this trigger"}
    assert cells["nova_buys"]["ok"] is False and cells["nova_buys"]["why"].startswith("Buy was You (Signal only)")
    assert cells["tape_go"] == {"ok": False, "why": "WAIT: burst of red"}
    assert cells["trades_today"]["ok"] is True                          # the cap still had room at 07:16


def test_an_unlisted_ticker_and_not_a_trade(day):
    zzzz = by_symbol(get())["ZZZZ"]["triggers"][0]
    assert zzzz["cells"]["hot_list"] == {"ok": False, "why": "ZZZZ was not on the day's hot list"}
    assert zzzz["cells"]["grade"]["ok"] is False and zzzz["cells"]["grade"]["why"].startswith("grade C")
    assert zzzz["cells"]["tape_go"] == {"ok": False, "why": "VETO: a seller of 60,000 at 10.05"}


def test_the_impact_of_each_gate(day):
    impact = {i["gate"]: i for i in get()["impact"]}
    assert list(impact) == GATES
    assert impact["trades_today"] == {"gate": "trades_today", "blocked": 3, "target_first": 1, "stop_first": 1,
                                      "r": 1.0}
    assert impact["hot_list"]["blocked"] == 2 and impact["hot_list"]["r"] == 1.0      # LGHL +1.0, ZZZZ unscored
    assert impact["level2_line"] == {"gate": "level2_line", "blocked": 1, "target_first": 1, "stop_first": 0,
                                     "r": 2.0}
    assert impact["tape_go"]["blocked"] == 2                            # LGHL wait, ZZZZ veto (not BLIND)


def test_today_s_rules_judge_the_rules_nothing_recorded(day):
    from setup_templates.store import get_store

    get_store().update("first_pullback", "default", values={"bot_setups_a_day": 2, "bot_window_end": "10:30"})
    second = by_symbol(get())["AISP"]["triggers"][2]
    assert second["cells"]["setups_a_day"]["ok"] is True and second["cells"]["bot_window"]["ok"] is True


def test_a_missing_journal_or_hot_list_is_stated(day):
    body = get("2026-09-29")
    assert body["sources"]["journal"] == {"ok": False, "error": "no eyes' journal on file for 2026-09-29"}
    assert body["sources"]["hot_list"]["ok"] is False and body["tickers"] == []


def test_a_bad_date_is_a_400():
    assert client.get("/api/bot/triggers?date=2026-13-45").status_code == 400
    assert client.get("/api/bot/triggers?date=yesterday").status_code == 400


# -- today: the "now" row ---------------------------------------------------------------------------
def test_now_says_whether_nova_would_buy_each_listed_ticker(monkeypatch):
    from bot import trigger_now
    from bot.arming import issue_arm_token
    from bot.autonomy import apply_patch
    from tests.bot_helpers import hold_depth_line, list_hot, on_practice, set_symbols

    on_practice()
    apply_patch({"level": 2, "setup_levels": {"first_pullback": 2}}, desk=True)
    issue_arm_token()
    set_symbols("AISP")
    hold_depth_line("AISP")
    list_hot("LGHL")
    monkeypatch.setattr(trigger_now, "_lanes", lambda sym: [
        {"setup_type": "first_pullback", "state": "near", "grade": "B" if sym == "LGHL" else "A",
         "liquidity": None, "phase": None}])
    body = get(datetime.now(ET).date().isoformat())
    tickers = by_symbol(body)
    aisp = tickers["AISP"]["now"]
    assert aisp["answer"] == "yes" and aisp["reasons"] == []
    assert aisp["cells"]["tape_go"]["ok"] is None and aisp["cells"]["level2_line"]["ok"] is True
    lghl = tickers["LGHL"]["now"]
    assert lghl["answer"] == "no"
    assert lghl["cells"]["nova_buys"] == {"ok": False, "why": "Buy is You on LGHL: set its Buy to Nova (Who trades)"}
    assert lghl["cells"]["level2_line"]["ok"] is None                    # no line now: not known until the trigger
    from setup_templates.store import get_store

    get_store().update("first_pullback", "default", values={"bot_grades": "A"})
    lghl = by_symbol(get(datetime.now(ET).date().isoformat()))["LGHL"]["now"]
    assert lghl["cells"]["grade"]["ok"] is False and "grade B: this strategy buys grade A only" in \
        lghl["cells"]["grade"]["why"]


def test_now_when_the_bot_is_off(monkeypatch):
    from tests.bot_helpers import list_hot, on_practice

    on_practice()
    list_hot("AISP")
    now = by_symbol(get(datetime.now(ET).date().isoformat()))["AISP"]["now"]
    assert now["answer"] == "no" and now["cells"]["bot_on"]["ok"] is False
    assert now["cells"]["strategy_on"] == {"ok": False, "why": "no strategy is On: turn one On"}
    assert now["cells"]["setups_a_day"]["ok"] is None and now["cells"]["bot_window"]["ok"] is None


# -- the timeline ------------------------------------------------------------------------------------
def test_the_nearest_record_tells_a_setting_at_any_moment():
    rows = [{"timestamp": 100.0, "venue": "paper", "action": "setup_level", "inputs": {"setup": "x", "from": 1, "to": 2}},
            {"timestamp": 200.0, "venue": "paper", "action": "stock_mode", "outcome": "set",
             "inputs": {"symbol": "A", "from": "signal", "to": "auto_entry"}},
            {"timestamp": 400.0, "venue": "paper", "action": "stock_mode", "outcome": "set",
             "inputs": {"symbol": "B", "from": "signal", "to": "bot"}}]
    tl = Timeline(rows, restarts=[300.0])
    assert tl.level_at("paper", "x", 50.0, lambda: 0) == 1                 # the first change's "from"
    assert tl.level_at("paper", "x", 150.0, lambda: 0) == 2
    assert tl.level_at("live", "x", 150.0, lambda: 0) == 0                 # another venue: nothing recorded
    assert tl.mode_at("paper", "A", 250.0, lambda: "signal") == "auto_entry"
    assert tl.mode_at("paper", "A", 350.0, lambda: "signal") == "signal"   # the restart dropped the switch
    assert tl.mode_at("paper", "B", 350.0, lambda: "signal") == "signal"   # "from" of the 400 line
    assert tl.mode_at("paper", "C", 250.0, lambda: "bot") == "bot"         # a restart keeps the bot list
    assert tl.mode_at("paper", "C", 250.0, lambda: "signal") == UNKNOWN    # ... but not what a switch was
