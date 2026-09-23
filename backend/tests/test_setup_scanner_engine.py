"""The setup scanner engine end to end on fakes (ADR 022): live bars in, board,
tape-gated proposal, trigger, score -- and never an order."""
from __future__ import annotations

import asyncio

import pytest

from setup_scanner.engine import SetupEngine
from setup_scanner.store import SetupStore
from tests.setup_scanner_fixtures import add, base_morning, leg_up

SYM = "ABCD"


class FakeTape:
    def __init__(self):
        self.go = True
        self.depth = True
        self.now = 0.0
        self.synced: set[str] = set()

    def sync(self, wanted, now):
        self.synced, self.now = set(wanted), now

    def books(self, sym):
        if not self.depth:
            return []
        book = {"bids": [{"price": 4.35, "size": 4000}], "asks": [{"price": 4.37, "size": 3000}]}
        return [(self.now - 5, book), (self.now - 0.2, book)]

    def prints(self, sym):
        side = "ask" if self.go else "bid"
        return [{"ts": self.now - 3 + i * 0.5, "size": 300, "side": side} for i in range(4)]

    def has_depth(self, sym):
        return self.depth

    def has_tape(self, sym):
        return True

    def close(self):
        pass


def make(tmp_path, seed_bars):
    audits: list[dict] = []
    clock = {"t": seed_bars[-1].t + 30}
    eng = SetupEngine(store=SetupStore(tmp_path / "setups.db"), tape=FakeTape(),
                      universe=lambda: [SYM], seed=lambda sym, since: list(seed_bars),
                      replay_desk=lambda: False, audit=lambda **kw: audits.append(kw),
                      clock=lambda: clock["t"])
    return eng, audits, clock


def run(eng, now):
    asyncio.run(eng.tick(now))


def bar_msg(b):
    return {"t": b.t, "o": b.o, "h": b.h, "l": b.l, "c": b.c, "v": b.v}


def test_seed_leg_then_armed_near_proposal_trigger_score(tmp_path):
    bars = leg_up(base_morning(), [4.08, 4.18, 4.28, 4.38])
    eng, audits, clock = make(tmp_path, bars)
    run(eng, clock["t"])
    assert eng.det[SYM].state == "leg"
    board = eng.board(clock["t"])
    assert board["rows"][0]["state"] == "leg" and board["universe"] == 1

    pb = add(list(bars), 4.38, 4.37, 4.30, 4.32, 30_000)[-1]
    eng.on_l1_minute("bar", SYM, bar_msg(pb))
    clock["t"] = pb.t + 61
    run(eng, clock["t"])
    assert eng.det[SYM].state == "armed"
    row = next(iter(eng.rows.values()))
    assert row["trigger"] == 4.37 and row["stop"] == 4.30 and row["grade"] in ("A", "B", "C")

    eng.on_l1_minute("last", SYM, {"price": 4.35, "ts": clock["t"], "bar_open": 4.32})
    run(eng, clock["t"])
    assert eng.det[SYM].state == "near"
    assert len(eng.proposals) == 1 and audits and audits[0]["action"] == "setup_proposal"
    prop = next(iter(eng.proposals.values()))
    assert prop["trigger"] == 4.37 and prop["status"] == "open"
    assert eng.board(clock["t"])["rows"][0]["proposal"]["id"] == prop["id"]

    clock["t"] += 2
    eng.on_l1_minute("last", SYM, {"price": 4.38, "ts": clock["t"], "bar_open": 4.32})
    run(eng, clock["t"])
    assert eng.det[SYM].state == "triggered"
    assert prop["status"] == "triggered"
    saved = eng.store.rows()[0]
    assert saved["triggered_at"] and saved["trigger_tape"]["verdict"] == "go"
    assert saved["near_tape"]["verdict"] == "go"

    clock["t"] += 5
    eng.on_l1_minute("last", SYM, {"price": 4.55, "ts": clock["t"], "bar_open": 4.32})
    run(eng, clock["t"])
    assert eng.store.rows()[0]["outcome"] == "target_first"


def test_no_proposal_when_the_tape_is_red(tmp_path):
    bars = add(leg_up(base_morning(), [4.08, 4.18, 4.28, 4.38]), 4.38, 4.37, 4.30, 4.32, 30_000)
    eng, audits, clock = make(tmp_path, bars)
    eng.tape.go = False
    run(eng, clock["t"])
    assert eng.det[SYM].state == "armed"
    eng.on_l1_minute("last", SYM, {"price": 4.36, "ts": clock["t"], "bar_open": 4.32})
    run(eng, clock["t"])
    assert eng.det[SYM].state == "near"
    assert eng.proposals == {} and audits == []
    assert eng.tape_view[SYM]["verdict"] in ("wait", "veto")


def test_blind_without_a_level2_line(tmp_path):
    bars = add(leg_up(base_morning(), [4.08, 4.18, 4.28, 4.38]), 4.38, 4.37, 4.30, 4.32, 30_000)
    eng, audits, clock = make(tmp_path, bars)
    eng.tape.depth = False
    run(eng, clock["t"])
    eng.on_l1_minute("last", SYM, {"price": 4.36, "ts": clock["t"], "bar_open": 4.32})
    run(eng, clock["t"])
    assert eng.tape_view[SYM]["verdict"] == "blind"
    assert eng.proposals == {}


def test_no_proposal_on_a_replay_desk(tmp_path):
    bars = add(leg_up(base_morning(), [4.08, 4.18, 4.28, 4.38]), 4.38, 4.37, 4.30, 4.32, 30_000)
    eng, audits, clock = make(tmp_path, bars)
    eng._replay_fn = lambda: True
    run(eng, clock["t"])
    eng.on_l1_minute("last", SYM, {"price": 4.36, "ts": clock["t"], "bar_open": 4.32})
    run(eng, clock["t"])
    assert eng.proposals == {}
    assert eng.board(clock["t"])["proposing"] is False


def test_symbols_outside_the_universe_are_ignored(tmp_path):
    bars = base_morning()
    eng, _, clock = make(tmp_path, bars)
    run(eng, clock["t"])
    eng.on_l1_minute("bar", "ZZZZ", {"t": clock["t"], "o": 1, "h": 1, "l": 1, "c": 1})
    assert not any(k[1] == "ZZZZ" for k in eng.inbox)


def test_engine_never_imports_the_execution_door():
    import setup_scanner.engine as eng_mod
    src = open(eng_mod.__file__, encoding="utf-8").read()
    for banned in ("execution.service", "place_order", "ExecutionCommand", "actions.fire"):
        assert banned not in src
