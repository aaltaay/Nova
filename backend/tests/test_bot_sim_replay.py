"""Nova's bot trades a Sim replay like Paper, and goes back with the playhead (ADR 052).

The tests load a real historical window into the Sim (the IBKR download path: prints, no quotes), drive the
bot's loop one tick at a time on the Sim clock, and send its orders through the real execution door into the
Sim scratch account. The resting orders fill on the replay's prints when the Sim feed matches them
(``sim.feed.match_practice_fills``), and a backward scrub unwinds the account as the operator's does.
"""
from __future__ import annotations

import asyncio

import pytest

from bot import entry_rules, replay_desk
from bot.audit import list_entries
from bot.first_pullback import runner
from bot.persist import load_session
from constants_bot import BOT_SKIP_STALE
from execution import inflight
from practice.broker import for_venue
from ibkr import safety as _safety
from sim import broker as sim_broker, feed, practice
from sim import history_playback as playback, history_store as store, session_clock as clock
from sim.mode import set_venue
from tests.bot_helpers import ready_l2
from tests.test_sim_practice import isolated  # noqa: F401 -- autouse: a private Sim store and clean replay

DAY = "2026-09-18"
SYM = "IMCC"
# 07:00:10 10.00 · 07:00:30 11.00 (the trigger) · 07:00:32 10.40 (inside the entry's 3 s) · 07:01:00 12.00
# (target 1) · 07:01:30 10.00
TAPE = [(10, 10.00), (30, 11.00), (32, 10.40), (60, 12.00), (90, 10.00)]


def load_window() -> dict:
    spec = store.window(SYM, DAY, "07:00", "10:00")
    job = store.create(spec, "trades")
    a = spec["start_ts"]
    store.commit_page(job["id"], a, [dict(ts=a + sec, price=px, size=100) for sec, px in TAPE], spec["end_ts"], True)
    playback.select(spec)
    clock.set_paused(True)
    return spec


@pytest.fixture
def replay():
    """Sim off its live edge on IMCC 07:00-10:00, the desk armed, the bot Active at Strategy on IMCC."""
    inflight.reset_for_tests()
    set_venue("sim", persist=False)
    spec = load_window()
    ready_l2(brain=None, symbols=(SYM,))
    _safety.set_armed(True, reason="test")
    entry_rules.set_clock_for_tests(lambda: clock.now_et())   # the venue clock is the playhead
    runner.reset_for_tests()
    yield spec
    runner.reset_for_tests()
    inflight.reset_for_tests()


def at(spec: dict, sec: float) -> float:
    return float(spec["start_ts"]) + sec


def go(sec: float) -> None:
    """The operator moves the playhead (paused there); the Sim feed matches what rests."""
    clock.scrub_to_second(sec)
    clock.set_paused(True)
    feed.match_practice_fills()


def trigger(spec: dict, sec: float = 30, **over) -> dict:
    # The entry rests under the 11.00 last (an IBKR download has no quotes: a limit at the last fills at once)
    # and fills on the 10.40 print at :32, inside its 3 s; target 1 is the 12.00 print at :60.
    setup = {"kind": "first_pullback", "trigger": 10.49, "entry": 10.50, "stop": 10.30, "risk": 0.20,
             "target1": 12.00, "triggered_at": at(spec, sec), "trigger_price": 10.50, "nth": 1}
    setup.update(over.pop("setup", {}))
    event = {"symbol": SYM, "setup_id": f"{SYM}-{DAY}-leg1", "setup": setup,
             "tape": {"verdict": "go", "reasons": ["green on the tape"]}, "ts": at(spec, sec),
             "template_id": "default", "template_rev": 1, "template_name": "Default", "source": "sim",
             "replay_key": list(practice.loaded().key), "grade": "A",
             "pillars": {"passed": 5, "known": 5, "total": 5}, "filtered": None, "spread": 0.02}
    event.update(over)
    return event


def tick() -> dict | None:
    asyncio.run(runner.tick())
    return load_session().get("trade")


def rows(outcome: str | None = None) -> list[dict]:
    return [r for r in list_entries(limit=200)
            if r["action"] == "bot_trade" and (outcome is None or r["outcome"] == outcome)]


def test_activate_needs_a_loaded_replay_off_the_live_edge():
    from bot.activation import venue_block, venue_state

    set_venue("sim", persist=False)                     # the suite pins Sim's live edge off
    assert venue_block(*venue_state())[0] == "BOT_REPLAY_DESK"
    load_window()
    assert venue_block(*venue_state()) is None
    assert runner.playing(load_session())[1] != "nothing loaded"


def test_the_bot_buys_a_trigger_the_playhead_plays_across(replay):
    go(30)
    runner.submit(trigger(replay))
    trade = tick()
    assert trade["state"] == "entering" and trade["venue"] == "sim"
    assert trade["replay_key"] == list(practice.loaded().key) and trade["entry_sent_ts"] == at(replay, 30)
    assert trade["venue_day"] == DAY                                     # the replayed day, not today
    assert [o["order_id"] for o in for_venue("sim").working_orders()][:1] == [trade["entry_order_id"]]
    assert sim_broker.snapshot()["replay_key"] == trade["replay_key"]
    assert entry_rules.today("sim")["count"] == 1
    [line] = [r for r in list_entries(limit=50) if r["action"] == "buy_setup_limit"]
    assert line["replay"]["key"] == trade["replay_key"] and line["replay"]["playhead_ts"] == at(replay, 30)


def test_a_trigger_older_than_five_seconds_at_the_playhead_is_stale(replay):
    go(40)                                                               # 10 s after the trigger
    runner.submit(trigger(replay))
    assert tick() is None
    [row] = rows("skipped")
    assert row["inputs"]["code"] == BOT_SKIP_STALE and "10s old" in row["reason"]


def test_a_trigger_from_another_feed_is_not_this_desks(replay):
    go(30)
    runner.submit(trigger(replay, source="live", replay_key=None))      # the live scanner's
    runner.submit(trigger(replay, replay_key=["historical", "ABCD", DAY, "07:00", "10:00"]))
    assert tick() is None and rows() == []


def test_the_entry_ttl_runs_on_the_sim_clock_and_stands_still_while_paused(replay):
    go(30)
    runner.submit(trigger(replay, setup={"entry": 10.20, "trigger": 10.19, "stop": 9.90, "risk": 0.30,
                                         "target1": 10.80, "trigger_price": 10.20}))    # 10.40 at :32 never fills it
    assert tick()["state"] == "entering"
    for _ in range(3):                                                   # the wall clock runs, the playhead not
        assert tick()["state"] == "entering" and tick().get("entry_cancel_ts") is None
    go(34)                                                               # 4 s of replay: past the 3 s TTL
    trade = tick()
    assert trade["entry_cancel_ts"] == at(replay, 34)
    trade = tick()
    assert trade["state"] == "missed" and "not filled in 3s" in trade["note"]
    assert entry_rules.today("sim")["count"] == 0                        # a miss gives the replay's day back


def test_a_rewind_takes_the_trade_back_as_it_stood_and_a_setup_can_trade_again(replay):
    go(30)
    runner.submit(trigger(replay))
    assert tick()["state"] == "entering"
    first_entry = load_session()["trade"]["entry_order_id"]
    go(50)                                                               # the 10.40 print at :32 fills the buy
    assert tick()["state"] == "open"
    assert load_session()["trade"]["entry_fill_price"] is not None
    go(31)                                                               # back before the fill
    trade = tick()
    assert trade["state"] == "entering" and trade["entry_order_id"] == first_entry
    assert trade["entry_fill_price"] is None
    assert any("the playhead went back to 07:00:31 ET" in (r["reason"] or "") for r in rows("note"))
    go(20)                                                               # back before the entry was sent
    assert tick() is None
    assert for_venue("sim").working_orders() == [] and entry_rules.today("sim")["count"] == 0
    go(30)                                                               # the playhead plays the trigger again
    runner.submit(trigger(replay))
    trade = tick()
    assert trade["state"] == "entering" and trade["entry_order_id"] != first_entry
    assert entry_rules.today("sim")["count"] == 1


def test_the_target_fills_on_the_replay_and_the_trade_closes(replay):
    go(30)
    runner.submit(trigger(replay))
    tick()
    go(50)
    assert tick()["state"] == "open"
    go(65)                                                               # 12.00 at :60: target 1
    trade = tick()
    assert trade["state"] == "closed" and trade["exit_reason"] == "target" and trade["r"] > 0


def test_another_replay_retires_the_trade_made_on_the_old_one(replay):
    go(30)
    runner.submit(trigger(replay))
    assert tick()["state"] == "entering"
    spec = store.window(SYM, DAY, "07:00", "09:00")                    # another window: the account starts over
    job = store.create(spec, "trades")
    store.commit_page(job["id"], spec["start_ts"], [dict(ts=spec["start_ts"] + 5, price=10.0, size=100)],
                      spec["end_ts"], True)
    playback.select(spec)
    clock.set_paused(True)
    trade = tick()                                                       # gone with the old account, and said so
    assert trade["state"] == "rewound" and "another replay was loaded" in trade["note"]
    assert load_session().get("working") == [] and replay_desk.today(at(replay, 100))["count"] == 0
    assert any("another replay was loaded" in (r["reason"] or "") for r in rows("note"))


def test_a_rewind_never_touches_a_trade_made_on_paper(replay):
    """The session's one trade slot can hold a Paper trade the desk left (its exits rest at the broker there): a
    rewind on the replay takes back only the replay's own part, never that trade."""
    from bot.persist import save_session

    go(30)
    tick()                                                               # the run begins at :30
    paper = {"setup_id": "P1", "symbol": "ABCD", "state": "open", "venue": "paper", "qty": 50.0, "side": "long",
             "replay_key": None, "entry_order_id": 7, "target_order_id": 8, "stop_order_id": 9}
    row = load_session()
    row.update(trade=dict(paper), bot_qty={"ABCD": 50.0}, working=[{"order_id": 77, "symbol": "ABCD"}])
    save_session(row)
    go(40)
    tick()                                                               # remembered at :40
    go(35)                                                               # back: nothing of the replay's to undo
    tick()
    after = load_session()
    assert after["trade"] == paper and after["bot_qty"] == {"ABCD": 50.0}
    assert after["working"] == [{"order_id": 77, "symbol": "ABCD"}]


def test_a_restart_retires_a_replay_trade_the_scratch_account_lost(replay):
    from bot.persist import save_session

    row = load_session()
    row["trade"] = {"setup_id": "OLD", "symbol": SYM, "state": "open", "venue": "sim", "qty": 10.0, "side": "long",
                    "replay_key": list(practice.loaded().key), "entry_order_id": 999}
    row["bot_qty"] = {SYM: 10.0}
    save_session(row)
    go(30)
    trade = tick()
    assert trade["state"] == "rewound" and "does not survive a restart" in trade["note"]
    assert load_session().get("bot_qty", {}).get(SYM) is None


# -- the entry carries its own TTL (#816) ----------------------------------------------------------------------------
LOW_ENTRY = {"entry": 10.20, "trigger": 10.19, "stop": 9.90, "risk": 0.30, "target1": 10.80, "trigger_price": 10.20}


def leap(sec: float, *, expire: bool = True) -> None:
    """The operator jumps the playhead forward; the Sim feed's tick matches what rests, then expires what is due.
    ``expire=False`` stops after the match: the bot's tick may come before the expiry pass."""
    go(sec)
    if expire:
        feed.expire_practice_orders()


def ledger_row(order_id: int) -> dict:
    return for_venue("sim").ledger.order_row(order_id)


@pytest.mark.parametrize("expire_first", [True, False], ids=["the-feed-expires-it", "the-bot-cancel-comes-first"])
def test_a_jump_past_the_entrys_ttl_never_fills_it_and_a_scrub_back_restores_it(replay, expire_first):
    from constants_practice import PRACTICE_GOOD_FOR_EXPIRED_CODE
    from practice.ledger import EVENT_EXPIRED

    go(30)
    runner.submit(trigger(replay, setup=LOW_ENTRY))       # 10.40 at :32 never fills a 10.20 buy; 10.00 at :90 would
    trade = tick()
    entry = trade["entry_order_id"]
    row = ledger_row(entry)
    assert (row["good_for_sec"], row["expires_ts"]) == (3.0, at(replay, 33))         # sent + the sleeve's 3 s
    assert all(ledger_row(oid)["good_for_sec"] is None for oid in (trade["target_order_id"], trade["stop_order_id"]))

    leap(150, expire=expire_first)          # 2 minutes forward, across the 10.00 at :90
    trade = tick()
    if not expire_first:
        assert trade["entry_cancel_ts"] == at(replay, 150)                          # the bot's own TTL cancel
        trade = tick()
    row = ledger_row(entry)
    assert (row["status"], row["reason_code"], row["filled_qty"]) == ("Expired", PRACTICE_GOOD_FOR_EXPIRED_CODE, 0.0)
    [expired] = [e for e in for_venue("sim").ledger.events if e["type"] == EVENT_EXPIRED]
    assert (expired["order_id"], expired["ts"]) == (entry, at(replay, 33))           # at sent + TTL, not at the jump
    assert {ledger_row(oid)["status"] for oid in (trade["target_order_id"], trade["stop_order_id"])} == {"Cancelled"}
    assert for_venue("sim").positions() == [] and for_venue("sim").working_orders() == []
    assert trade["state"] == "missed" and "not filled in 3s" in trade["note"]
    assert entry_rules.today("sim")["count"] == 0

    go(32)                                                               # back before the expiry
    trade = tick()
    assert trade["state"] == "entering" and trade["entry_order_id"] == entry
    assert ledger_row(entry)["status"] == "Submitted"
    assert [o["order_id"] for o in for_venue("sim").working_orders()][:1] == [entry]
    assert entry_rules.today("sim")["count"] == 1


def test_a_print_inside_the_ttl_still_fills_the_entry_on_a_jump(replay):
    go(30)
    runner.submit(trigger(replay))
    trade = tick()
    leap(150)                               # the 10.40 at :32 is inside the entry's 3 s: it fills there
    assert tick()["state"] == "open"
    row = ledger_row(trade["entry_order_id"])
    assert (row["status"], row["fill_ts"]) == ("Filled", at(replay, 32))
