"""The agent endpoints (ADR 050): find stock-days and show them on the desk in the Sim.

Commands queue for the main desk window, which takes one by a long poll and reports each step; a new show
replaces one not finished; nobody listening is refused. A show parks a few minutes before the run (or on the
high, at a time) inside the desk's usual window, with narrower ones to fall back on. A venue switch or a Sim
window that would start the Sim account over is refused while something is at stake, until confirmed. Writes
need the API key even on loopback. The dictionary keeps the operator's entries beside the seeds.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from agent_desk import commands, dictionary, planner, routes, safety
from day_movers import store
from main import app
from tests.bot_helpers import headers

ET = ZoneInfo("America/New_York")
client = TestClient(app)
DAY = "2026-09-25"


def ts(day: str, hh: int, mm: int) -> int:
    d = date.fromisoformat(day)
    return int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET).timestamp())


ROW = {"symbol": "MSGY", "session_date": DAY, "up10_ts": ts(DAY, 7, 32), "up20_ts": ts(DAY, 9, 34),
       "day_high_ts": ts(DAY, 17, 4), "day_low_ts": ts(DAY, 9, 37), "down10_ts": None, "down20_ts": None}


@pytest.fixture(autouse=True)
def fresh_board(monkeypatch):
    clock = {"now": 1_000.0}
    board = commands.CommandBoard(now=lambda: clock["now"])
    monkeypatch.setattr(commands, "BOARD", board)
    return clock


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("NOVA_API_KEY", "agent-test-key")
    monkeypatch.setenv("NOVA_API_HOST", "127.0.0.1")
    return headers("agent-test-key")


@pytest.fixture
def desk(monkeypatch, tmp_path, key):
    """A Sim desk listening, the day's trades on disk, MSGY in the index, nothing at stake."""
    import sim.massive_files as massive_files
    import sim.mode as sim_mode

    trades = tmp_path / "trades.csv.gz"
    trades.write_bytes(b"")
    monkeypatch.setattr(massive_files, "day_file", lambda dataset, day: trades if day == DAY else None)
    monkeypatch.setattr(sim_mode, "venue", lambda: "sim")
    monkeypatch.setattr(routes.movers_read, "row_or_none", lambda day, symbol: dict(ROW) if symbol == "MSGY" else None)
    monkeypatch.setattr(routes, "loaded_window", lambda: None)
    monkeypatch.setattr(safety, "READERS", ())
    monkeypatch.setattr(safety, "SIM_READERS", ())
    assert client.get("/api/agent/desk/next?wait=0", headers=key).json() == {"command": None}
    return key


# ── The plan ──────────────────────────────────────────────────────────────────────────────────────

def test_a_show_parks_five_minutes_before_the_run_inside_the_desks_window():
    plan = planner.plan_show("msgy", DAY, "run", ROW, today="2026-10-06")
    assert plan["symbol"] == "MSGY" and plan["park_et"] == "09:29:00"
    assert plan["park_words"] == "5 min before it first traded +20% (09:34)"
    assert plan["window"]["start"] == "08:45" and plan["window"]["end"] == "11:00"
    assert plan["window"]["start_ts"] == ts(DAY, 8, 45)
    assert [(w["start"], w["end"]) for w in plan["fallback_windows"]] == [("08:45", "09:45"), ("09:20", "09:50")]


def test_a_stock_already_up_at_its_first_print_parks_before_its_next_leg():
    gap = dict(ROW, first_ts=ts(DAY, 4, 0), up10_ts=ts(DAY, 4, 0), up20_ts=ts(DAY, 4, 0), up50_ts=ts(DAY, 4, 1),
               up100_ts=ts(DAY, 4, 2), up300_ts=ts(DAY, 9, 47))
    plan = planner.plan_show("AMOD", DAY, "run", gap, today="2026-10-06")
    assert plan["park_et"] == "09:42:00" and "already moving at its first print" in plan["park_words"]
    flat = dict(gap, up300_ts=None)
    assert planner.plan_show("AMOD", DAY, "run", flat, today="2026-10-06")["park_et"] == "17:04:00"   # the high


@pytest.mark.parametrize("at,park,window", [
    ("high", "17:04:00", ("16:30", "18:45")),
    ("09:45", "09:45:00", ("09:15", "11:30")),
    ("19:55", "19:55:00", ("17:45", "20:00")),
    ("premarket", "04:00:00", ("04:00", "06:15")),
])
def test_other_moments_and_the_session_edges(at, park, window):
    plan = planner.plan_show("MSGY", DAY, at, ROW, today="2026-10-06")
    assert plan["park_et"] == park and (plan["window"]["start"], plan["window"]["end"]) == window


def test_a_show_refuses_a_day_not_over_and_an_anchor_with_no_index_row():
    with pytest.raises(planner.PlanError, match="not over"):
        planner.plan_show("MSGY", "2026-10-06", "run", ROW, today="2026-10-06")
    with pytest.raises(planner.PlanError, match="not in the movers index"):
        planner.plan_show("ZZZ", DAY, "run", None, today="2026-10-06")
    with pytest.raises(planner.PlanError, match="at must be"):
        planner.plan_show("MSGY", DAY, "lunch", ROW, today="2026-10-06")


def test_a_move_inside_the_loaded_window_needs_no_new_one_and_outside_it_does():
    loaded = {"symbol": "MSGY", "date": DAY, "start": "09:00", "end": "11:15"}
    inside = planner.plan_move(loaded, ts(DAY, 9, 30), to=None, by_min=10, paused=None, row=ROW)
    assert inside["target_et"] == "09:40:00" and inside["window"] is None
    assert inside["loaded_start_ts"] == ts(DAY, 9, 0)
    outside = planner.plan_move(loaded, ts(DAY, 9, 30), to="high", by_min=None, paused=True, row=ROW)
    assert outside["target_et"] == "17:04:00" and outside["window"]["start"] == "16:30"
    pause = planner.plan_move(loaded, ts(DAY, 9, 30), to=None, by_min=None, paused=True, row=ROW)
    assert pause["target_ts"] is None and pause["paused"] is True


# ── The commands ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_desk_takes_the_oldest_and_reports_and_a_new_show_replaces_the_old(fresh_board):
    board = commands.BOARD
    first = board.create("show", {"symbol": "A"}, {"x": 1})
    taken = await board.next_for_desk(0, "main")
    assert taken["id"] == first["id"] and taken["status"] == "running" and board.listening()
    board.report(first["id"], status="running", step="load", text="Loading 10%")
    board.report(first["id"], status="running", step="load", text="Loading 50%")
    assert [s["text"] for s in board.get(first["id"])["steps"]] == ["Loading 50%"]   # a step's progress replaces
    second = board.create("show", {"symbol": "B"}, {"x": 2})
    assert board.report(first["id"], status="running", step="park")["status"] == "cancelled"
    assert (await board.next_for_desk(0, "main"))["id"] == second["id"]
    done = board.report(second["id"], status="done", step="parked", result={"ok": 1})
    assert done["status"] == "done" and done["result"] == {"ok": 1}


def test_a_command_no_desk_takes_expires(fresh_board):
    board = commands.BOARD
    command = board.create("show", {}, None)
    fresh_board["now"] += commands.AGENT_COMMAND_CLAIM_SEC + 1
    expired = board.get(command["id"])
    assert expired["status"] == "expired" and "desk" in expired["error"]
    assert not board.listening()


@pytest.mark.asyncio
async def test_a_command_a_vanished_window_took_goes_back_in_the_queue(fresh_board):
    board = commands.BOARD
    command = board.create("show", {}, None)
    assert (await board.next_for_desk(0, "main"))["claims"] == 1
    fresh_board["now"] += commands.AGENT_COMMAND_FIRST_REPORT_SEC + 1       # took it, never said a word
    assert board.get(command["id"])["status"] == "queued"
    again = await board.next_for_desk(0, "main")
    assert again["id"] == command["id"] and again["claims"] == 2
    board.release(command["id"])                                           # the poll's window went away
    assert board.get(command["id"])["status"] == "queued"
    await board.next_for_desk(0, "main")
    fresh_board["now"] += commands.AGENT_COMMAND_FIRST_REPORT_SEC + 1
    gone = board.get(command["id"])
    assert gone["status"] == "failed" and "never ran it" in gone["error"]    # three claims, no step: given up


@pytest.mark.asyncio
async def test_a_command_that_stops_reporting_mid_way_fails(fresh_board):
    board = commands.BOARD
    command = board.create("move", {}, None)
    await board.next_for_desk(0, "main")
    board.report(command["id"], status="running", step="load", text="Loading")
    fresh_board["now"] += commands.AGENT_COMMAND_LEASE_SEC + 1
    assert board.get(command["id"])["status"] == "failed"


# ── The at-stake check ────────────────────────────────────────────────────────────────────────────

def test_at_stake_reads_the_venue_left_and_the_sim_account_and_a_failed_check_is_at_stake():
    position = (("orders", lambda v: [{"kind": "position", "venue": v, "symbol": "AAPL", "text": "Paper position"}]),)

    def broken(_venue):
        raise RuntimeError("ledger locked")

    assert safety.at_stake("sim", readers=position)["safe"] is True                # nothing is left on the Sim
    paper = safety.at_stake("paper", readers=position)
    assert paper["safe"] is False and paper["items"][0]["symbol"] == "AAPL"
    unknown = safety.at_stake("paper", readers=(("bot", broken),))
    assert unknown["safe"] is False and unknown["unknown"][0]["kind"] == "bot"
    sim = safety.at_stake("sim", reloading=True, sim_readers=position)
    assert sim["safe"] is False


# ── The dictionary ────────────────────────────────────────────────────────────────────────────────

def test_the_dictionary_keeps_the_operators_entries_beside_the_seeds(tmp_path):
    target = tmp_path / "agent-dictionary.json"
    seeds = dictionary.view(target)
    assert seeds["error"] is None and any(e["id"] == "show-in-sim" and e["seed"] for e in seeds["entries"])
    entry = {"id": "ascending", "phrases": ["ascending chart"], "means": "closed +20% in the top third",
             "call": {"method": "GET", "path": "/api/agent/movers", "params": {"close_min": 20, "close_pos_min": 0.67}}}
    stored = dictionary.put(entry, target=target, now=10.0)
    assert stored["added_at"] == 10.0 and stored["seed"] is False
    again = dictionary.put(dict(entry, phrases=["ascending", "up all day"]), target=target, now=20.0)
    assert again["added_at"] == 10.0 and again["updated_at"] == 20.0
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1 and len(raw["entries"]) == 1
    assert dictionary.remove("ascending", target=target) is True and dictionary.remove("show-in-sim", target=target) is False


@pytest.mark.parametrize("entry,field", [
    ({"id": "Bad Id", "phrases": ["x"], "means": "x", "call": {"method": "GET", "path": "/api/agent"}}, "id"),
    ({"id": "a", "phrases": [], "means": "x", "call": {"method": "GET", "path": "/api/agent"}}, "phrases"),
    ({"id": "a", "phrases": ["x"], "means": "x", "call": {"method": "GET", "path": "/api/ibkr/order"}}, "call.path"),
    ({"id": "a", "phrases": ["x"], "call": {"method": "GET", "path": "/api/agent"}}, "means"),
])
def test_a_bad_entry_names_its_field(tmp_path, entry, field):
    with pytest.raises(dictionary.EntryInvalid) as caught:
        dictionary.put(entry, target=tmp_path / "d.json")
    assert caught.value.field == field


def test_an_unreadable_dictionary_reads_as_the_seeds_and_refuses_writes(tmp_path):
    target = tmp_path / "agent-dictionary.json"
    target.write_text(json.dumps({"schema_version": 7, "entries": []}), encoding="utf-8")
    view = dictionary.view(target)
    assert "schema_version 7" in view["error"] and all(e["seed"] for e in view["entries"])
    with pytest.raises(dictionary.DictionaryUnreadable):
        dictionary.put({"id": "a", "phrases": ["x"], "means": "x", "call": {"method": "GET", "path": "/api/agent"}},
                       target=target)


# ── The routes ────────────────────────────────────────────────────────────────────────────────────

def test_writes_and_the_desks_poll_need_the_key_and_the_reads_do_not():
    assert client.post("/api/agent/show", json={"symbol": "MSGY", "date": DAY}).status_code == 503
    assert client.get("/api/agent/desk/next?wait=0").status_code == 503
    catalogue = client.get("/api/agent")
    assert catalogue.status_code == 200 and catalogue.json()["schema_version"] == 1
    assert any(e["path"] == "/api/agent/show" for e in catalogue.json()["endpoints"])


def test_the_search_says_when_the_index_is_not_built_and_answers_once_it_is(monkeypatch, tmp_path):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    missing = client.get("/api/agent/movers", params={"high_min": 300})
    assert missing.status_code == 503 and missing.json()["detail"]["reason"] == "AGENT_INDEX_UNAVAILABLE"
    with store.connect(tmp_path / "movers" / "day_movers.sqlite3") as db:
        store.replace_session(db, {"session_date": DAY, "prev_date": None, "tickers": 1, "rows": 1, "minute_bars": 1,
                                   "builder": 1, "built_ts": 0.0, "note": None}, [{
            "session_date": DAY, "symbol": "MSGY", "kind": "CS", "prev_close": 1.97, "open": 2.13, "high": 11.42,
            "low": 1.97, "close": 8.07, "volume": 5.6e7, "day_high": 12.73, "day_low": 1.97, "high_pct": 5.46,
            "low_pct": 0.0, "close_pct": 3.1, "gap_pct": 0.08, "split_factor": 1.0, "split_listed": 0,
            "split_suspect": 0, "day_high_ts": ts(DAY, 17, 4)}])
    found = client.get("/api/agent/movers", params={"high_min": 300, "price_max": 20})
    assert found.status_code == 200 and [r["symbol"] for r in found.json()["rows"]] == ["MSGY"]
    assert found.json()["coverage"]["sessions"] == 1
    bad = client.get("/api/agent/movers", params={"high_min": "lots"})
    assert bad.status_code == 400 and bad.json()["detail"]["field"] == "high_min"
    one = client.get(f"/api/agent/movers/{DAY}/msgy")
    assert one.status_code == 200 and one.json()["row"]["day_high_et"] == "17:04"


def test_a_show_runs_on_the_desk_step_by_step(desk):
    sent = client.post("/api/agent/show", json={"symbol": "msgy", "date": DAY}, headers=desk)
    assert sent.status_code == 202
    command = sent.json()["command"]
    assert command["status"] == "queued" and command["plan"]["park_et"] == "09:29:00"
    assert command["plan"]["switch_venue"] is False and command["plan"]["in_index"] is True
    taken = client.get("/api/agent/desk/next?wait=0", headers=desk).json()["command"]
    assert taken["id"] == command["id"] and taken["status"] == "running"
    step = client.post(f"/api/agent/desk/commands/{command['id']}", headers=desk,
                       json={"status": "running", "step": "load", "text": "Loading 40%"})
    assert step.status_code == 200 and step.json()["command"]["step"] == "load"
    client.post(f"/api/agent/desk/commands/{command['id']}", headers=desk,
                json={"status": "done", "step": "parked", "text": "Paused at 09:29", "result": {"playhead_et": "09:29:00"}})
    final = client.get(f"/api/agent/commands/{command['id']}?wait=0").json()["command"]
    assert final["status"] == "done" and final["result"]["playhead_et"] == "09:29:00"


def test_a_show_is_refused_off_file_with_no_desk_and_while_something_is_at_stake(desk, monkeypatch):
    import sim.mode as sim_mode

    gone = client.post("/api/agent/show", json={"symbol": "MSGY", "date": "2026-09-24"}, headers=desk)
    assert gone.status_code == 404 and gone.json()["detail"]["reason"] == "AGENT_NOT_ON_FILE"
    monkeypatch.setattr(sim_mode, "venue", lambda: "paper")
    monkeypatch.setattr(safety, "READERS", (("orders", lambda v: [
        {"kind": "position", "venue": v, "symbol": "AAPL", "text": "Paper position AAPL 100"}]),))
    stake = client.post("/api/agent/show", json={"symbol": "MSGY", "date": DAY}, headers=desk)
    assert stake.status_code == 409 and stake.json()["detail"]["reason"] == "AGENT_AT_STAKE"
    assert "Paper position AAPL 100" in stake.json()["detail"]["error"]
    agreed = client.post("/api/agent/show", json={"symbol": "MSGY", "date": DAY, "confirm": True}, headers=desk)
    assert agreed.status_code == 202 and agreed.json()["command"]["plan"]["switch_venue"] is True


def test_nobody_listening_is_refused_and_a_move_needs_a_loaded_window(key, fresh_board, monkeypatch):
    import sim.massive_files as massive_files

    monkeypatch.setattr(massive_files, "day_file", lambda dataset, day: massive_files.root())
    refused = client.post("/api/agent/show", json={"symbol": "MSGY", "date": DAY, "at": "09:45"}, headers=key)
    assert refused.status_code == 409 and refused.json()["detail"]["reason"] == "AGENT_NO_DESK"
    client.get("/api/agent/desk/next?wait=0", headers=key)
    monkeypatch.setattr(routes, "loaded_window", lambda: None)
    move = client.post("/api/agent/move", json={"to": "high"}, headers=key)
    assert move.status_code == 409 and move.json()["detail"]["reason"] == "AGENT_NOTHING_LOADED"


def test_the_dictionary_routes(key, monkeypatch, tmp_path):
    monkeypatch.setattr(dictionary, "path", lambda: tmp_path / "agent-dictionary.json")
    entry = {"id": "ascending", "phrases": ["ascending chart"], "means": "closed +20% in the top third",
             "call": {"method": "GET", "path": "/api/agent/movers", "params": {"close_min": 20}}}
    assert client.post("/api/agent/dictionary", json={"entry": entry}).status_code == 401        # no key sent
    saved = client.post("/api/agent/dictionary", json={"entry": entry}, headers=key)
    assert saved.status_code == 200 and saved.json()["entry"]["id"] == "ascending"
    assert any(e["id"] == "ascending" for e in client.get("/api/agent/dictionary").json()["entries"])
    bad = client.post("/api/agent/dictionary", json={"entry": dict(entry, id="Bad Id")}, headers=key)
    assert bad.status_code == 400 and bad.json()["detail"]["field"] == "id"
    assert client.delete("/api/agent/dictionary/ascending", headers=key).status_code == 200
    assert client.delete("/api/agent/dictionary/ascending", headers=key).status_code == 404
