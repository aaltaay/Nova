"""The tape at a trigger is the tape Nova saw (ADR 022 amendment 2026-09-30).

LGHL 2026-09-30: the first pullback armed on an 8.61 trigger, and IBKR's L1 last
traded 8.66 over it, stamped 07:16:10 (IBKR's whole-second trade time). That price
reached the setup scanner at 07:16:10.856. The sweep that lifted the offer from 8.52
to 8.63 had arrived at 07:16:10.60, and prints are stamped when they arrive (#563).
Read at the stamp, the gate said WAIT, "burst of red", and the bot could not take
it. Read when the trigger arrived, it says GO.

The fixture is cut from the Session Record (prints with the side the live tape
stamped, books sampled every 0.5 s) and the archive's one-minute bars, up to the
moment the trigger arrived: ``fixtures/trigger_read/lghl-2026-09-30.json``.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from setup_scanner.bars import Bar
from setup_scanner.engine import SetupEngine
from setup_scanner.lane import Lane
from setup_scanner.lane_params import lane_params
from setup_scanner.store import SetupStore
from setup_scanner.tape_feed import TapeFeed
from setup_scanner.tape_gate import evaluate
from setup_templates.store import default_template

FIXTURE = Path(__file__).parent / "fixtures" / "trigger_read" / "lghl-2026-09-30.json"
SYM = "LGHL"


def load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def books(fx: dict) -> list[tuple[float, dict]]:
    def side(levels):
        return [{"price": px, "size": sz} for px, sz in levels]

    return [(ts, {"bids": side(b["bids"]), "asks": side(b["asks"])}) for ts, b in fx["books"]]


class RecordedTape:
    """What the live tape feed held for LGHL when the trigger arrived: the recorded books and prints."""

    def __init__(self, fx: dict):
        self._books, self._prints = books(fx), fx["prints"]

    def sync(self, wanted, now):
        pass

    def books(self, sym):
        return list(self._books)

    def prints(self, sym):
        return list(self._prints)

    def has_depth(self, sym):
        return True

    def has_tape(self, sym):
        return True

    def close(self):
        pass


def EYES():  # noqa: N802 -- a levels hook, named for what it says
    return {"chosen": None, "levels": {"first_pullback": 1}}


def armed_engine(tmp_path, fx: dict, clock: dict, journal: list) -> SetupEngine:
    seed = [Bar(t, o, h, lo, c, v) for t, o, h, lo, c, v in fx["bars"]]
    eng = SetupEngine(store=SetupStore(tmp_path / "setups.db"), tape=RecordedTape(fx),
                      universe=lambda: [SYM], seed=lambda sym, since: list(seed),
                      replay_desk=lambda: False, audit=lambda **kw: None, clock=lambda: clock["t"],
                      journal=journal.append, levels=EYES, setups=("first_pullback",))
    asyncio.run(eng.tick(clock["t"]))
    return eng


def test_the_recorded_trigger_reads_wait_at_its_stamp_and_go_when_it_arrived():
    fx = load()
    trigger, live = fx["setup"]["trigger"], fx["live_tape"]

    at_stamp = evaluate(trigger=trigger, now=fx["stamp"], books=books(fx), prints=fx["prints"])
    m = at_stamp["metrics"]
    # The read the live eyes made at 07:16:10, reproduced from the recording.
    assert at_stamp["verdict"] == live["verdict"] == "wait"
    assert at_stamp["reasons"] == live["reasons"]
    assert (m["ask_volume"], m["bid_volume"], m["ask_prints"], m["bid_prints"]) == (
        live["ask_volume"], live["bid_volume"], live["ask_prints"], live["bid_prints"]) == (0.0, 1454.0, 0, 50)

    arrived = evaluate(trigger=trigger, now=fx["arrived"], books=books(fx), prints=fx["prints"])
    m = arrived["metrics"]
    assert arrived["verdict"] == "go"
    assert (m["ask_prints"], m["ask_volume"]) == (124, 7882.0)
    assert m["read_at"] == fx["arrived"]


def test_the_engine_reads_the_trigger_when_it_sees_it(tmp_path):
    fx = load()
    clock, journal = {"t": fx["stamp"] - 9.5}, []          # 07:16:00.5: the 07:15 pullback candle has closed
    eng = armed_engine(tmp_path, fx, clock, journal)
    assert eng.det[SYM].state == "armed"
    armed = eng.det[SYM].armed
    assert (armed["trigger"], armed["entry"], armed["stop"]) == (8.61, 8.62, 8.45)

    clock["t"] = fx["arrived"]
    eng.on_l1_minute("last", SYM, {"price": fx["price"], "ts": fx["stamp"], "bar_open": fx["bar_open"]})
    asyncio.run(eng.tick(clock["t"]))

    row = eng.store.rows()[0]
    assert row["state"] == "triggered"
    assert row["triggered_at"] == fx["stamp"]                 # the trigger keeps IBKR's own stamp
    tape = row["trigger_tape"]
    assert tape["verdict"] == "go", tape["reasons"]
    assert tape["metrics"]["read_at"] == fx["arrived"]          # its tape is the tape Nova saw
    line = next(e for e in journal if e["event"] == "triggered" and e.get("playing"))
    assert line["tape"]["verdict"] == "go" and line["setup"]["triggered_at"] == fx["stamp"]


def test_a_setup_coming_near_is_read_when_the_price_arrives(tmp_path):
    fx = load()
    clock, journal = {"t": fx["stamp"] - 9.5}, []
    eng = armed_engine(tmp_path, fx, clock, journal)
    # A price 2c under the trigger, stamped on IBKR's whole second and seen 0.6 s later.
    clock["t"] = fx["stamp"] - 5.4
    eng.on_l1_minute("last", SYM, {"price": 8.59, "ts": fx["stamp"] - 6, "bar_open": fx["bar_open"]})
    asyncio.run(eng.tick(clock["t"]))
    assert eng.det[SYM].state == "near"
    near = next(e for e in journal if e["event"] == "near" and e.get("playing"))
    assert near["tape"]["metrics"]["read_at"] == clock["t"]


def test_a_read_is_never_before_the_price_it_is_for():
    lane = Lane(lane_params(default_template("first_pullback")), SimpleNamespace(clock=lambda: 100.0))
    assert lane.read_at(99.0) == 100.0          # seen after its stamp: read when seen
    assert lane.read_at(101.0) == 101.0         # a clock behind the stamp never reads before the price


class _HeldLine:
    """A tick-by-tick line someone else holds: the feed attaches a passive viewer queue."""

    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()

    def is_subscribed(self, sym):
        return True

    def open_viewer_queue(self, sym):
        return self.queue

    def close_viewer_queue(self, sym, queue):
        pass


def test_a_read_takes_the_prints_still_waiting_in_the_queue():
    line = _HeldLine()
    feed = TapeFeed(depth=SimpleNamespace(is_live=lambda sym: False, current_book=lambda sym: None), tape=line)
    feed.sync({SYM}, 100.0)                                  # attaches the queue
    line.queue.put_nowait({"ts": 100.6, "price": 8.6, "size": 194, "side": "ask", "exchange": "NASDAQ"})
    # No sync since: the engine reads a trigger before it syncs that tick.
    assert [p["ts"] for p in feed.prints(SYM)] == [100.6]
    assert [p["ts"] for p in feed.prints(SYM)] == [100.6]    # taken once, kept
    assert feed.prints("OTHER") == []
