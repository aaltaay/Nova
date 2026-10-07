"""The squares, by ticker (ADR 044): ``GET /api/bot/triggers``.

A day's eyes' journal, the bot's audit stream and the day's hot list are written as Nova writes them;
every trigger is judged by the nine gates in Nova's order from what was recorded at it, the gates nothing
recorded are named in ``judged_now``, and each gate's effect is summed in ``impact``. Being on the hot list
is no gate (ADR 044, amended 2026-10-06): the list orders the rows, and today's bot-buy stocks get a row of
their own whether or not they are listed.
"""
from __future__ import annotations

import json
import time
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
GATES = ["bot_on", "strategy_on", "grade", "setups_a_day", "bot_window", "nova_buys", "level2_line", "tape_go",
         "trades_today", "not_against"]
SHORT_GATES = ["short_borrow", "short_ssr", "short_halt", "short_margin", "short_hours"]
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
        "schema_version": 1, "date": day, "auto_n": 5, "entries": entries, "yesterday": []}), encoding="utf-8")


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
        {"timestamp": at(9, 41, 1), "venue": "paper", "action": "buy_setup_limit", "outcome": "ok",
         "inputs": {"symbol": "AISP", "setup_id": "AISP-1", "setup_type": "first_pullback", "side": "long"}},
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


def get(day_: str | None = DAY) -> dict:
    """The table of ``day_``; ``None`` asks as the desk does, with no date (today's trading day)."""
    res = client.get("/api/bot/triggers" + (f"?date={day_}" if day_ is not None else ""))
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
    labels = {g["id"]: g["label"] for g in body["gates"]}
    assert [labels["bot_on"], labels["strategy_on"], labels["nova_buys"]] == ["Bot on", "Strategy on", "Entry: Bot"]
    assert labels["not_against"] == "Not against you" and [g["id"] for g in body["short_gates"]] == SHORT_GATES
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
    assert oks(first["cells"]) == [True] * 10 and first["reasons"] == [] and list(first["cells"]) == GATES
    assert first["side"] == "long" and first["cells"]["not_against"]["why"] == "you held no AISP short"
    assert first["cells"]["trades_today"]["why"].startswith("it takes Nova's 1st entry of the day")
    assert first["cells"]["nova_buys"]["why"].startswith("Entry was Bot (Bot")


def test_each_red_square_says_why(day):
    aisp = by_symbol(get())["AISP"]["triggers"]
    bull, second = aisp[1], aisp[2]
    assert bull["cells"]["strategy_on"] == {"ok": False, "why": "the bull flag was Off: Nova trades only the "
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
    assert "hot_list" not in cells                                       # listed at 07:30, after it: no square
    assert cells["nova_buys"]["ok"] is False and cells["nova_buys"]["why"].startswith("Entry was You (Signal only)")
    assert cells["tape_go"] == {"ok": False, "why": "WAIT: burst of red"}
    assert cells["trades_today"]["ok"] is True                          # the cap still had room at 07:16


def test_an_unlisted_ticker_and_not_a_trade(day):
    zzzz = by_symbol(get())["ZZZZ"]["triggers"][0]
    assert list(zzzz["cells"]) == GATES                                 # never on the list: no square says so
    assert not any("hot list" in reason for reason in zzzz["reasons"])
    assert zzzz["cells"]["grade"]["ok"] is False and zzzz["cells"]["grade"]["why"].startswith("grade C")
    assert zzzz["cells"]["tape_go"] == {"ok": False, "why": "VETO: a seller of 60,000 at 10.05"}


def test_the_impact_of_each_gate(day):
    impact = {i["gate"]: i for i in get()["impact"]}
    assert list(impact) == GATES + SHORT_GATES
    assert impact["trades_today"] == {"gate": "trades_today", "blocked": 3, "target_first": 1, "stop_first": 1,
                                      "r": 1.0}
    assert "hot_list" not in impact
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
    set_symbols("AISP")                                                 # the bot buys AISP; it is not listed
    hold_depth_line("AISP")
    list_hot("LGHL")
    monkeypatch.setattr(trigger_now, "_lanes", lambda sym: [
        {"setup_type": "first_pullback", "state": "near", "grade": "B" if sym == "LGHL" else "A",
         "liquidity": None, "phase": None}])
    body = get(None)
    tickers = by_symbol(body)
    assert list(tickers) == ["LGHL", "AISP"]                             # the listed, then the bot's own
    assert tickers["AISP"]["listed"] is None
    aisp = tickers["AISP"]["now"]
    assert aisp["answer"] == "yes" and aisp["reasons"] == [] and list(aisp["cells"]) == GATES
    assert aisp["cells"]["nova_buys"] == {"ok": True, "why": "Entry: Bot (Bot)"}
    assert aisp["cells"]["tape_go"]["ok"] is None and aisp["cells"]["level2_line"]["ok"] is True
    lghl = tickers["LGHL"]["now"]
    assert lghl["answer"] == "no"
    assert lghl["cells"]["nova_buys"] == {"ok": False, "why": "Entry is You on LGHL: set its Entry to Bot (Who trades)"}
    assert lghl["cells"]["level2_line"]["ok"] is None                    # no line now: not known until the trigger
    from setup_templates.store import get_store

    get_store().update("first_pullback", "default", values={"bot_grades": "A"})
    lghl = by_symbol(get(None))["LGHL"]["now"]
    assert lghl["cells"]["grade"]["ok"] is False and "grade B: this strategy buys grade A only" in \
        lghl["cells"]["grade"]["why"]


def test_now_when_the_bot_is_off(monkeypatch):
    from tests.bot_helpers import list_hot, on_practice

    on_practice()
    list_hot("AISP")
    now = by_symbol(get(None))["AISP"]["now"]
    assert now["answer"] == "no" and now["cells"]["bot_on"]["ok"] is False
    assert now["cells"]["strategy_on"] == {"ok": False, "why": "no strategy is On: turn one On"}
    assert now["cells"]["setups_a_day"]["ok"] is None and now["cells"]["bot_window"]["ok"] is None


@pytest.mark.parametrize(("hour", "minute", "trading_day"), [(0, 30, "2026-10-01"), (10, 0, "2026-10-02")])
def test_today_is_the_hot_lists_trading_day(monkeypatch, hour, minute, trading_day):
    """Today is the hot list's trading day, which starts at 04:00 ET. From midnight to the rollover the
    calendar already reads Friday while the list is still Thursday's: the table follows the list, so its
    tickers and their "now" rows do not vanish overnight."""
    from tests.bot_helpers import list_hot, on_practice

    monkeypatch.setattr(time, "time", lambda: at(hour, minute, day="2026-10-02"))
    on_practice()
    list_hot("AISP")
    body = get(None)                                                    # the desk's ask: no date
    assert body["date"] == trading_day
    assert body["sources"]["hot_list"] == {"ok": True, "error": None}
    assert by_symbol(body)["AISP"]["now"] is not None
    assert by_symbol(get(trading_day))["AISP"]["now"] is not None       # asked by name, it is today too
    if trading_day != "2026-10-02":                                     # before 04:00 Friday has no list yet
        friday = get("2026-10-02")
        assert friday["tickers"] == [] and friday["sources"]["hot_list"]["ok"] is False


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


def test_a_retried_reset_clears_only_the_bot_lists_it_names():
    """A reset that failed at 04:00 and ran on a retry at 06:00 cleared the bot lists it names, not every mode:
    the Bot stock reads You · You after it, and an Auto-entry switch set at 05:00 is still Auto-entry."""
    def mode(sym, to, h):
        return {"timestamp": at(h, 0), "venue": "paper", "action": "stock_mode", "outcome": "set",
                "inputs": {"symbol": sym, "from": "signal", "to": to}}

    rows = [mode("BOTX", "bot", 5), mode("AUTOX", "auto_entry", 5),
            {"timestamp": at(6, 0), "venue": "paper", "action": "hot_list", "outcome": "rollover",
             "inputs": {"event": "rollover", "retry": True, "from": DAY, "to": DAY,
                        "cleared": [{"venue": "paper", "symbol": "BOTX", "was": "bot"}]}}]
    line = Timeline(rows)
    unknown = lambda: UNKNOWN  # noqa: E731
    assert line.mode_at("paper", "BOTX", at(5, 30), unknown) == "bot"
    assert line.mode_at("paper", "BOTX", at(7, 0), unknown) == "signal"
    assert line.mode_at("paper", "AUTOX", at(7, 0), unknown) == "auto_entry"
    full = Timeline(rows[:2] + [{**rows[2], "inputs": {"event": "rollover"}}])        # the 04:00 kind clears all
    assert full.mode_at("paper", "AUTOX", at(7, 0), unknown) == "signal"


def test_a_stock_taken_off_the_hot_list_before_its_trigger_is_judged_the_same(day):
    """A star is watching, never permission: AISP taken off the list at 09:30 still passes every gate at 09:41,
    and LGHL listed only after its trigger is red for its own reasons, never for the list."""
    write_audit([{"timestamp": at(9, 30), "venue": "paper", "action": "hot_list", "outcome": "remove",
                  "inputs": {"event": "remove", "symbol": "AISP"}}])
    tickers = by_symbol(get())
    first = tickers["AISP"]["triggers"][0]
    assert oks(first["cells"]) == [True] * 10 and first["reasons"] == []
    lghl = tickers["LGHL"]["triggers"][0]
    assert not any("hot list" in r or "listed" in r for r in lghl["reasons"])


def test_a_bot_buy_stock_off_the_hot_list_gets_a_row_with_now(monkeypatch):
    """Today's bot-buy stocks -- the bot list, then each Auto-entry switch -- get a row after the listed names
    whether or not they are listed, each with a ``now``; a stock at Signal only off the list gets none."""
    from bot import trigger_now
    from bot.arming import issue_arm_token
    from bot.autonomy import apply_patch
    from stock_mode import store
    from tests.bot_helpers import list_hot, on_practice, set_symbols

    on_practice()
    apply_patch({"level": 2, "setup_levels": {"first_pullback": 2}}, desk=True)
    issue_arm_token()
    set_symbols("BOTX", "LGHL")                                         # LGHL is both listed and the bot's
    store.set_switch("AUTOX", {"buy": "nova", "sell": "you", "set_at": time.time()})
    store.set_switch("APPX", {"buy": "you", "sell": "nova", "set_at": time.time()})
    list_hot("LGHL")
    monkeypatch.setattr(trigger_now, "_lanes", lambda sym: [])
    try:
        tickers = by_symbol(get(None))
    finally:
        store.reset_for_tests()
    assert list(tickers) == ["LGHL", "BOTX", "AUTOX"]
    assert tickers["LGHL"]["listed"]["how"] == "star"
    for sym in ("BOTX", "AUTOX"):
        assert tickers[sym]["listed"] is None and tickers[sym]["triggers"] == []
        assert list(tickers[sym]["now"]["cells"]) == GATES
    assert tickers["BOTX"]["now"]["cells"]["nova_buys"] == {"ok": True, "why": "Entry: Bot (Bot)"}
    assert tickers["AUTOX"]["now"]["cells"]["nova_buys"] == {"ok": True, "why": "Entry: Bot (Auto-entry)"}


def test_now_says_the_bot_buys_nothing_before_todays_reset(monkeypatch):
    """No file for today: the ``now`` row of a bot-buy stock is a no, with the reset's words in Bot buys."""
    from bot import trigger_now
    from bot.arming import issue_arm_token
    from bot.autonomy import apply_patch
    from constants_hot_list import HOT_LIST_FILE
    from paths import cache_dir
    from tests.bot_helpers import hold_depth_line, on_practice, set_symbols

    on_practice()
    apply_patch({"level": 2, "setup_levels": {"first_pullback": 2}}, desk=True)
    issue_arm_token()
    set_symbols("AISP")
    hold_depth_line("AISP")
    (cache_dir() / HOT_LIST_FILE).unlink()
    monkeypatch.setattr(trigger_now, "_lanes", lambda sym: [])
    body = get(None)
    now = by_symbol(body)["AISP"]["now"]
    assert now["answer"] == "no"
    assert now["cells"]["nova_buys"]["ok"] is False
    assert now["cells"]["nova_buys"]["why"].startswith("the 04:00 ET reset of yesterday's bot buys has not run yet")
    assert now["reasons"] == [now["cells"]["nova_buys"]["why"]]


def test_now_says_whether_a_level_2_line_would_come(monkeypatch):
    """No line held now: a free line or a hidden tab's loan may still come (unknown), or none can: BLIND."""
    from bot import trigger_now

    monkeypatch.setattr("bot.eligibility.holds_depth_line", lambda sym: sym == "HELD")
    assert trigger_now._line("HELD")["ok"] is True
    monkeypatch.setattr("line_lending.lines.free_lines", lambda: 1)
    monkeypatch.setattr("line_lending.setting.is_on", lambda: (False, None))
    free = trigger_now._line("AISP")
    assert free["ok"] is None and "1 of IBKR's lines are free" in free["why"]
    monkeypatch.setattr("line_lending.lines.free_lines", lambda: 0)
    monkeypatch.setattr("line_lending.setting.is_on", lambda: (True, None))
    lent = trigger_now._line("AISP")
    assert lent["ok"] is None and "lends its lines when a setup comes near" in lent["why"]
    monkeypatch.setattr("line_lending.setting.is_on", lambda: (False, None))
    blind = trigger_now._line("AISP")
    assert blind == {"ok": False, "why": "Nova holds no Level 2 line on AISP, every line is taken and lending is off: "
                                         "a trigger now would read BLIND"}


# -- both sides (ADR 049, #778 step 5) --------------------------------------------------------------
def test_a_short_trigger_gets_the_short_block_and_its_ssr_square_is_never_red(day):
    write_journal([
        {"ts": at(4, 0, 1), "event": "session", "symbol": None, "bot": BOT_ON},
        {**triggered("FADE", "FADE-BF", at(10, 30), setup_type="bear_flag", kind="bear_flag"), "side": "short",
         "ssr": "on"},
    ])
    check = [{"id": "borrow", "label": "Borrow", "ok": False, "text": "IBKR lists no FADE shares to borrow."},
             {"id": "halt", "label": "Halt", "ok": True, "text": "FADE is trading."},
             {"id": "margin", "label": "Margin", "ok": True, "text": "$400 of $5,000 fits."},
             {"id": "cushion", "label": "25% cushion", "ok": True, "text": "IBKR would liquidate near 9.10."}]
    write_audit([{"timestamp": at(10, 30, 1), "venue": "paper", "action": "bot_trade", "outcome": "skipped",
                  "inputs": {"symbol": "FADE", "setup_id": "FADE-BF", "setup_type": "bear_flag", "side": "short",
                             "ssr": "on", "codes": ["SHORT_NOT_SHORTABLE"], "short_check": check}}])
    fade = by_symbol(get())["FADE"]["triggers"][0]
    cells = fade["cells"]
    assert fade["side"] == "short" and list(cells) == GATES + SHORT_GATES
    assert cells["not_against"] == {"ok": True, "why": "you held no FADE long"}
    assert cells["short_borrow"] == {"ok": False, "why": "Borrow: IBKR lists no FADE shares to borrow."}
    assert cells["short_ssr"]["ok"] is True and cells["short_ssr"]["warn"] is True
    assert cells["short_ssr"]["why"].startswith("SSR · at the ask")
    assert cells["short_halt"]["ok"] is True and cells["short_margin"]["ok"] is True
    assert cells["short_hours"] == {"ok": True, "why": "10:30 ET, before the 15:50 last short"}
    assert "Borrow: IBKR lists no FADE shares to borrow." in fade["reasons"]


def test_a_trigger_against_a_position_you_hold_says_so(day):
    write_audit([{"timestamp": at(9, 50, 1), "venue": "paper", "action": "bot_trade", "outcome": "skipped",
                  "inputs": {"symbol": "AISP", "setup_id": "AISP-BF", "setup_type": "bull_flag",
                             "codes": ["BOT_SKIP_HELD_OTHER_SIDE"],
                             "reasons": ["you hold AISP short: Nova enters nothing on AISP while you do"]}}])
    bull = by_symbol(get())["AISP"]["triggers"][1]
    assert bull["cells"]["not_against"] == {"ok": False, "why": "you hold AISP short: Nova enters nothing on AISP "
                                                                "while you do"}
    assert "short_borrow" not in bull["cells"]                         # a long leaves the short block empty


def test_a_trigger_nova_never_judged_says_so_never_a_pass(day):
    zzzz = by_symbol(get())["ZZZZ"]["triggers"][0]
    assert zzzz["cells"]["not_against"]["ok"] is None and "did not judge" in zzzz["cells"]["not_against"]["why"]


# -- a short-only square stops only the short side (PR #790 review) --------------------------------
def _mixed_desk(on: list[str], *, long_window_open: bool = True):
    from types import SimpleNamespace

    window = {"start": "09:30", "end": "11:30"}
    rules = {"first_pullback": {"window": {**window, "open": long_window_open}, "setups_a_day": 1},
             "bear_flag": {"window": {**window, "start": "09:35", "open": True}, "setups_a_day": 1}}
    return SimpleNamespace(on=on, rules=rules, row={}, venue="paper", cap=2, used=0,
                           now=SimpleNamespace(mode=lambda venue, sym: "bot"))


@pytest.fixture
def short_block_blocked(monkeypatch):
    """A desk reading where only the short block fails: before 09:35, no short may enter."""
    from bot import switch, trigger_now, trigger_short
    from bot.trigger_cells import cell

    held = {"long": None, "short": None}
    monkeypatch.setattr(switch, "is_on", lambda row: True)
    monkeypatch.setattr(trigger_now, "_lanes", lambda sym: [])
    monkeypatch.setattr(trigger_now, "_line", lambda sym: cell(True, f"Nova holds {sym}'s Level 2 line"))
    monkeypatch.setattr("bot.first_pullback.admit.day_reset", lambda: None)
    monkeypatch.setattr(trigger_short, "against_now", lambda sym, sides: {s: held[s] for s in sorted(sides)})
    monkeypatch.setattr(trigger_short, "now_cells", lambda sym, venue, armed, row: {
        "short_borrow": cell(True, "IBKR lists 50,000 FADE shares to borrow"),
        "short_ssr": cell(True, "no SSR: the short sells at its entry"),
        "short_halt": cell(True, "not halted"),
        "short_margin": cell(None, "no short setup is armed or near on FADE"),
        "short_hours": cell(False, "09:31 ET: new shorts open at 09:35")})
    return held


def test_a_short_only_square_never_vetoes_a_long_that_could_trade(short_block_blocked):
    from bot import trigger_now

    got = trigger_now.row(_mixed_desk(["first_pullback", "bear_flag"]), "FADE", [])
    assert got["cells"]["short_hours"]["ok"] is False                   # the square stays red
    assert got["answer"] == "yes" and got["reasons"] == []              # a long trigger would still be taken


def test_the_short_block_stops_the_answer_when_no_long_could_trade(short_block_blocked):
    from bot import trigger_now

    short_only = trigger_now.row(_mixed_desk(["bear_flag"]), "FADE", [])
    assert short_only["answer"] == "no" and short_only["reasons"] == ["09:31 ET: new shorts open at 09:35"]
    long_window_shut = trigger_now.row(_mixed_desk(["first_pullback", "bear_flag"], long_window_open=False),
                                       "FADE", [])
    assert long_window_shut["answer"] == "no" and "09:31 ET: new shorts open at 09:35" in long_window_shut["reasons"]
    long_used = trigger_now.row(_mixed_desk(["first_pullback", "bear_flag"]), "FADE",
                                [{"symbol": "FADE", "setup_type": "first_pullback", "nth": 1, "ts": at(9, 40)}])
    assert long_used["answer"] == "no" and "09:31 ET: new shorts open at 09:35" in long_used["reasons"]
    short_block_blocked["long"] = ("BOT_SKIP_HELD_OTHER_SIDE", "you hold FADE short: Nova enters nothing long")
    held_short = trigger_now.row(_mixed_desk(["first_pullback", "bear_flag"]), "FADE", [])
    assert held_short["answer"] == "no" and "09:31 ET: new shorts open at 09:35" in held_short["reasons"]
