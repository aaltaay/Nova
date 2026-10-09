"""Auto-entry, Approve and "Nova takes the exit" trade a Sim replay, and go back with the playhead (ADR 052 amendment,
#815).

The tests load a real historical window into the Sim (the IBKR download path: prints, no quotes), drive the stock-mode
runner one tick at a time on the Sim clock, and send its orders through the real execution door into the Sim scratch
account. Resting orders fill on the replay's prints when the Sim feed matches them, and a backward scrub unwinds the
account as the operator's does: 07:00:10 10.00 · 07:00:30 11.00 · 07:00:45 10.40 · 07:01:00 12.00 · 07:01:30 10.00.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from bot import entry_rules
from bot.audit import list_entries
from execution import inflight
from ibkr import safety as _safety
from practice.broker import for_venue
from sim import practice
from sim import session_clock as clock
from sim.mode import set_venue
from stock_mode import runner, store
from tests.bot_helpers import headers, ready_l2
from tests.test_bot_sim_replay import DAY, SYM, at, go, load_window
from tests.test_bot_sim_replay import trigger as bot_trigger
from tests.test_sim_practice import isolated  # noqa: F401 -- autouse: a private Sim store and clean replay
from tests.test_stock_mode import api_key, client  # noqa: F401 -- fixture

SETUP_ID = f"{SYM}-{DAY}-leg1"


@pytest.fixture
def desk(api_key):  # noqa: F811 -- the fixture
    """Sim off its live edge on IMCC 07:00-10:00, the desk armed, the bot Active at Strategy with nothing on its
    list (IMCC is Auto-entry's or Approve's, never the bot's)."""
    inflight.reset_for_tests()
    store.reset_for_tests()
    set_venue("sim", persist=False)
    spec = load_window()
    ready_l2(brain=None, symbols=())
    _safety.set_armed(True, reason="test")
    entry_rules.set_clock_for_tests(lambda: clock.now_et())      # the venue clock is the playhead
    runner.reset_for_tests()
    yield SimpleNamespace(spec=spec, key=api_key)
    runner.reset_for_tests()
    store.reset_for_tests()
    inflight.reset_for_tests()


def trigger(d, sec: float = 30, **over) -> dict:
    return bot_trigger(d.spec, sec, setup_type="first_pullback", **over)


def tick() -> dict | None:
    asyncio.run(runner.tick())
    return store.trade("sim", SYM, key())


def key() -> list:
    return list(practice.loaded().key)


def put(d, entry: str, exit_: str):
    return client.put(f"/api/stock-mode/{SYM}", json={"entry": entry, "exit": exit_}, headers=headers(d.key))


def view() -> dict:
    return client.get(f"/api/stock-mode/{SYM}").json()


def working() -> list[int]:
    return [int(o["order_id"]) for o in for_venue("sim").working_orders()]


def notes(outcome: str = "note") -> list[str]:
    return [r["reason"] or "" for r in list_entries(limit=200) if r["action"] == "stock_mode" and r["outcome"] == outcome]


def approve(d, **over) -> None:
    """Approve as the operator did on the replay (the lane check is the route's; here the approval stands)."""
    store.set_switch(SYM, {"buy": "you", "sell": "nova", "set_at": clock.now_et().timestamp()})
    row = {"setup_id": SETUP_ID, "entry": 10.50, "stop": 10.30, "target": 12.00, "qty": 10,
           "setup_type": "first_pullback", "side": "long", "approved_at": clock.now_et().timestamp(),
           "state": "waiting", "reason": None, "replay_key": key()}
    row.update(over)
    store.set_approval(SYM, row)


@pytest.fixture
def lanes(monkeypatch):
    """The Sim eyes' lane for the approved setup, armed at its levels (the eyes themselves are tested elsewhere)."""
    lane = {"setup_id": SETUP_ID, "setup_type": "first_pullback", "state": "armed",
            "setup": {"entry": 10.50, "stop": 10.30, "target1": 12.00, "trigger": 10.49}}
    monkeypatch.setattr(runner, "_lanes", lambda sym: ([dict(lane)], None))
    return lane


# -- the switch -------------------------------------------------------------------------------------
def test_on_a_loaded_replay_every_mode_is_open_and_with_nothing_loaded_only_bot(desk):
    go(20)
    body = view()
    assert body["locks"]["modes"] == {"bot": None, "auto_entry": None, "approve": None}
    assert put(desk, "nova", "you").json()["mode"] == "auto_entry"
    assert put(desk, "you", "nova").json()["mode"] == "approve"
    from sim import history_playback

    history_playback.clear()                                           # nothing loaded off the edge
    body = view()
    assert body["locks"]["modes"]["auto_entry"] and "Nothing is loaded" in body["locks"]["modes"]["approve"]
    r = put(desk, "nova", "you")
    assert r.status_code == 409 and r.json()["detail"]["reason"] == "STOCK_MODE_REPLAY"
    assert "Nothing is loaded" in r.json()["detail"]["error"]


# -- Auto-entry -------------------------------------------------------------------------------------
def test_auto_entry_buys_a_trigger_the_playhead_plays_across_on_the_sim_account(desk):
    go(20)
    put(desk, "nova", "you")
    go(30)
    runner.submit(trigger(desk))
    trade = tick()
    assert trade["kind"] == "auto_entry" and trade["state"] == "entering" and trade["venue"] == "sim"
    assert trade["replay_key"] == key() and trade["sent_at"] == at(desk.spec, 30) and trade["venue_day"] == DAY
    assert working() == [trade["entry_order_id"]]
    assert entry_rules.today("sim")["count"] == 1                     # the replay run's day, the bot's cap
    [sent] = [r for r in list_entries(limit=50) if r["action"] == "stock_mode" and r["outcome"] == "sent"]
    assert sent["replay"]["key"] == key() and sent["replay"]["playhead_ts"] == at(desk.spec, 30)
    assert view()["trade"]["replay_key"] == key()
    go(50)                                                             # the 10.40 print at :45 fills it
    trade = tick()
    assert trade["state"] == "holding" and trade["fill_price"] is not None and trade["exits"] == "you"


def test_a_trigger_from_another_feed_is_not_this_desks(desk):
    go(20)
    put(desk, "nova", "you")
    go(30)
    runner.submit(trigger(desk, source="live", replay_key=None))      # the live scanner's
    runner.submit(trigger(desk, replay_key=["historical", "ABCD", DAY, "07:00", "10:00"]))
    assert tick() is None and working() == []


def test_the_entry_ttl_runs_on_the_playhead_and_stands_still_while_paused(desk):
    go(20)
    put(desk, "nova", "you")
    go(30)
    runner.submit(trigger(desk, setup={"entry": 10.20, "trigger": 10.19, "stop": 9.90, "risk": 0.30,
                                       "target1": 10.80, "trigger_price": 10.20}))     # 10.40 at :45 never fills it
    assert tick()["state"] == "entering"
    for _ in range(3):                                                 # the wall clock runs, the playhead not
        assert tick()["cancel_sent_at"] is None
    go(34)                                                             # 4 s of replay: past the 3 s TTL
    assert tick()["cancel_sent_at"] == at(desk.spec, 34)
    trade = tick()
    assert trade["state"] == "missed" and "not filled in 3s" in trade["note"]
    assert entry_rules.today("sim")["count"] == 0                      # a miss gives the replay's day back


def test_a_rewind_takes_the_auto_entry_back_as_it_stood_and_the_setup_trades_again(desk):
    go(20)
    put(desk, "nova", "you")
    go(30)
    runner.submit(trigger(desk))
    first = tick()["entry_order_id"]
    go(50)
    assert tick()["state"] == "holding"
    go(32)                                                             # back before the fill
    trade = tick()
    assert trade["state"] == "entering" and trade["entry_order_id"] == first and trade["fill_price"] is None
    assert any("the playhead went back to 07:00:32 ET" in n for n in notes())
    assert "went back to 07:00:32" in view()["last_event"]["text"]
    go(20)                                                             # back before the trigger
    assert tick() is None
    assert working() == [] and entry_rules.today("sim")["count"] == 0
    go(30)                                                             # the playhead plays the trigger again
    runner.submit(trigger(desk))
    trade = tick()
    assert trade["state"] == "entering" and trade["entry_order_id"] != first      # sent again, not the old receipt
    assert entry_rules.today("sim")["count"] == 1


# -- Approve ----------------------------------------------------------------------------------------
def test_an_approved_plan_goes_out_at_the_trigger_and_a_rewind_takes_it_back(desk, lanes):
    go(20)
    approve(desk)
    tick()                                                             # the run begins: the approval waits
    go(30)
    runner.submit(trigger(desk))
    trade = tick()
    assert trade["kind"] == "approve" and trade["state"] == "entering" and trade["replay_key"] == key()
    assert store.approval(SYM, key())["state"] == "sent"
    assert sorted(working()) == sorted([trade["entry_order_id"], trade["target_order_id"], trade["stop_order_id"]])
    assert entry_rules.today("sim")["approved"] == 1 and entry_rules.today("sim")["count"] == 0   # counted, not capped
    first = trade["entry_order_id"]
    go(32)
    tick()
    go(31)                                                             # back, after the send: as it stood
    assert tick()["entry_order_id"] == first and store.approval(SYM, key())["state"] == "sent"
    go(25)                                                             # back before the trigger
    assert tick() is None
    assert store.approval(SYM, key())["state"] == "waiting" and working() == []
    assert entry_rules.today("sim")["approved"] == 0
    go(30)
    runner.submit(trigger(desk))
    trade = tick()
    assert trade["entry_order_id"] != first and store.approval(SYM, key())["state"] == "sent"


def test_the_bracket_fills_and_closes_on_the_replay(desk, lanes):
    go(20)
    approve(desk)
    tick()
    go(30)
    runner.submit(trigger(desk))
    tick()
    go(50)                                                             # 10.40 at :45 fills the entry
    assert tick()["state"] == "holding"
    go(65)                                                             # 12.00 at :60: the target
    tick()
    trade = tick()
    assert trade["state"] == "closed" and trade["exit_reason"] == "target"
    assert store.approval(SYM, key()) is None


def test_an_approval_made_after_the_new_playhead_was_never_made(desk, lanes, monkeypatch):
    from stock_mode import model

    monkeypatch.setattr(model, "lane_verdict", lambda lane, spread=None: {"ok": True, "reasons": []})
    go(20)
    put(desk, "you", "nova")
    tick()                                                             # the run begins with no approval
    go(25)
    body = {"setup_id": SETUP_ID, "entry": 10.50, "stop": 10.30, "target": 12.00, "qty": 10}
    r = client.post(f"/api/stock-mode/{SYM}/approve", json=body, headers=headers(desk.key))
    assert r.status_code == 200, r.text
    assert r.json()["approval"]["replay_key"] == key() and r.json()["approval"]["approved_at"] == at(desk.spec, 25)
    go(27)
    tick()
    go(26)                                                             # back, after the approval: it stands
    tick()
    assert store.approval(SYM, key())["state"] == "waiting"
    go(22)                                                             # back before it: never made
    tick()
    assert store.approval(SYM, key()) is None and view()["approval"] is None


# -- Nova takes the exit ----------------------------------------------------------------------------
def test_nova_takes_the_exit_on_a_replay_its_stop_fills_there_and_a_rewind_takes_it_back(desk):
    go(30)
    for_venue("sim").place(SYM, "BUY", 100, "MKT")                     # bought by hand at 11.00
    tick()
    go(35)
    r = client.post(f"/api/stock-mode/{SYM}/take-exit", json={"stop": 10.50, "trail": False},
                    headers=headers(desk.key))
    assert r.status_code == 200, r.text
    trade = r.json()["trade"]
    assert trade["kind"] == "exit" and trade["replay_key"] == key() and trade["sent_at"] == at(desk.spec, 35)
    stop_id = trade["stop_order_id"]
    assert working() == [stop_id] and r.json()["sell"] == "nova"
    go(40)
    assert tick()["state"] == "holding"
    go(50)                                                             # 10.40 at :45 runs the stop
    tick()
    done = tick()
    assert done["state"] == "closed" and done["exit_reason"] == "stop"
    go(38)                                                             # back before the stop filled: it holds again
    trade = tick()
    assert trade["state"] == "holding" and trade["stop_order_id"] == stop_id and working() == [stop_id]
    go(32)                                                             # back before Nova took the exit
    assert tick() is None
    assert working() == [] and view()["sell"] == "you"


# -- the places stay apart --------------------------------------------------------------------------
def test_a_rewind_never_touches_a_live_edge_trade_and_the_runner_leaves_it_waiting(desk):
    go(20)
    tick()
    edge = {"kind": "auto_entry", "state": "entering", "venue": "sim", "symbol": "ABCD", "setup_id": "E1",
            "qty": 5, "entry": 5.0, "stop": 4.8, "target": None, "entry_order_id": 4242, "sent_at": 1.0,
            "ttl_sec": 3, "cancel_sent_at": None, "exits": "you", "attempt": "E1", "replay_key": None}
    store.set_trade(dict(edge))
    go(40)
    tick()
    go(25)
    tick()
    assert store.trade("sim", "ABCD") == edge                         # never restored, never managed (it waits)
    assert store.trade("sim", "ABCD", key()) is None


def test_another_replay_drops_the_old_replays_trades_and_says_so(desk):
    from sim import history_playback as playback, history_store as hstore

    go(20)
    put(desk, "nova", "you")
    go(30)
    runner.submit(trigger(desk))
    assert tick()["state"] == "entering"
    old = key()
    spec = hstore.window(SYM, DAY, "07:00", "09:00")                  # another window: the account starts over
    job = hstore.create(spec, "trades")
    hstore.commit_page(job["id"], spec["start_ts"], [dict(ts=spec["start_ts"] + 5, price=10.0, size=100)],
                       spec["end_ts"], True)
    playback.select(spec)
    clock.set_paused(True)
    assert tick() is None and store.trade("sim", SYM, old) is None
    assert any("another replay was loaded" in n for n in notes())


def test_a_replays_trades_are_never_written_to_the_trades_file(desk, tmp_path):
    go(20)
    put(desk, "nova", "you")
    go(30)
    runner.submit(trigger(desk))
    assert tick()["state"] == "entering"
    path = store._path()
    rows = json.loads(path.read_text(encoding="utf-8"))["trades"] if path.exists() else []
    assert not any(r.get("replay_key") for r in rows)
