"""QA R40 / R41 (2026-09-22): what a discarded practice ledger leaves behind.

R40: closing (or reloading) a replay while a SELL rested dropped the order with
its ledger but kept its ``execution.inflight`` commitment, so the shares read
"already sent" until a restart -- through later trades and a Sim reset.
R41: practice order ids restarted at 1 after a reset or a replay load, so a
telemetry update for a new order found an old execution row with the same id
(a never-filled resting SELL then read "Filled"); and an order that filled
inside the send never marked its own row filled.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from archive import db
from capture import recorder
from execution import inflight
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests
from sim import broker, capture_player, feed, replay
from sim import history_playback as playback, history_store as store, session_clock as clock
from sim.fill_model import Reference

DAY = "2026-09-18"
NOW = 1_700_000_000.0


@pytest.fixture
def sim_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("NOVA_SIM_CAPTURE_DIR", str(tmp_path / "capture"))
    monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
    db.init_db()
    _reset()
    spec = store.window("IMCC", DAY, "04:00", "09:30")
    job = store.create(spec, "trades")
    a = spec["start_ts"]
    rows = [dict(ts=a + sec, price=price, size=100) for sec, price in ((10, 10.0), (30, 11.0), (60, 12.0))]
    store.commit_page(job["id"], a, rows, spec["end_ts"], True)
    playback.select(spec)
    clock.set_paused(True)
    clock.scrub_to_second(40)
    yield spec
    _reset()


def _reset() -> None:
    clock.reset_for_tests()
    playback.clear()
    replay.clear_capture()
    capture_player.reset_for_tests()
    recorder.reset_for_tests()
    broker.reset_for_tests()
    feed.reset_for_tests()
    inflight.reset_for_tests()


def _resting_sell_held_by_the_door(execution_id: str) -> int:
    """What the execution door does: commit the shares, send, attach the order id."""
    inflight.commit(execution_id, symbol="IMCC", side="SELL", qty=1)
    raw = broker.place("IMCC", "SELL", 1, "LMT", limit_price=50.0)
    assert raw["ok"] and raw["broker_status"] == "Submitted"
    inflight.attach_order(execution_id, raw["order_id"])
    return int(raw["order_id"])


def test_unloading_the_replay_frees_a_resting_sells_shares(sim_replay) -> None:
    assert broker.place("IMCC", "BUY", 1, "MKT")["broker_status"] == "Filled"
    _resting_sell_held_by_the_door("exec-rest-1")
    assert inflight.committed_qty("IMCC", "SELL") == 1.0
    broker.reset_scratch_account("historical replay unloaded")
    assert inflight.committed_qty("IMCC", "SELL") == 0.0
    assert broker.open_orders() == []


def test_a_new_scratch_ledger_continues_the_old_order_ids(sim_replay) -> None:
    broker.place("IMCC", "BUY", 1, "MKT")
    _resting_sell_held_by_the_door("exec-rest-2")
    before = for_venue("sim").ledger.next_order_id()
    broker.reset_scratch_account("another window selected")
    assert for_venue("sim").ledger.next_order_id() == before
    raw = broker.place("IMCC", "BUY", 1, "MKT")
    assert raw["order_id"] == before  # never 1 again


class FakeLive:
    def __init__(self) -> None:
        self.now = NOW

    def reference(self, symbol: str) -> Reference:
        return Reference(10.0, 9.98, 10.02, live=True)

    def admission(self, symbol: str):
        return True, "OK", None

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return self.now


@pytest.fixture
def paper(monkeypatch):
    reset_for_tests()
    inflight.reset_for_tests()
    fake = FakeLive()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: fake)
    yield SimpleNamespace(broker=for_venue("paper"), ref=fake)
    reset_for_tests()
    inflight.reset_for_tests()


def test_a_paper_reset_continues_the_ids_and_keeps_them_across_a_restart(paper) -> None:
    paper.broker.place("IMCC", "BUY", 1, "MKT")
    paper.broker.place("IMCC", "SELL", 1, "LMT", limit_price=50.0)
    assert paper.broker.ledger.next_order_id() == 3
    paper.broker.reset()
    assert paper.broker.ledger.next_order_id() == 3
    reset_for_tests()  # a restart reloads practice-paper.json
    again = for_venue("paper")
    assert again.ledger.next_order_id() == 3
    assert again.place("IMCC", "BUY", 1, "MKT")["order_id"] == 3


@pytest.mark.asyncio
async def test_an_order_that_fills_inside_the_send_marks_its_own_row_filled(paper) -> None:
    from execution import store as exec_store
    from execution.models import ExecutionCommand, StageTimings
    from sim.execution import send_practice_broker

    exec_store.init_db()
    cmd = ExecutionCommand(
        operation="place", idempotency_key="r41-filled-inside", source="flatten",
        symbol="IMCC", side="BUY", qty=1, order_type="MKT",
    )
    execution_id, _new = exec_store.reserve(
        idempotency_key=cmd.idempotency_key, operation="place", source="flatten", symbol="IMCC", received_ns=0,
    )
    receipt = await send_practice_broker(
        cmd, execution_id, StageTimings(received_ns=0), broker=paper.broker, wait_ack=False, reject=None,
    )
    assert receipt.ok and receipt.broker_status == "Filled"
    row = exec_store.get_by_id(execution_id)
    assert row["status"] == "filled" and row["broker_status"] == "Filled"
    assert row["mode"] == "paper"
