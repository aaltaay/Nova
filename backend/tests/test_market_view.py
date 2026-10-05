"""The real-time view and the order gate (ADR 045).

2026-10-05 08:30 ET: the operator sold APUS at a 6.58 bid their Level 2 had shown since
08:30:18-21; Nova's book was 6.50 x 6.55 at the click, and the order reached the backend 2-3 s
later. These pin what makes that impossible now: versions with history, a hand-off that wakes the
socket's loop from the IB thread and never replays a backlog, and the gate that refuses the order.
"""
from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

import instance_identity
from constants_market_view import (
    FEED_STALE,
    ORDER_LATE,
    ORDER_MAX_SEND_MS,
    VIEW_MISSING,
    VIEW_STALE,
)
from market_view import gate, versions
from market_view.viewer_queues import BookVersion, LatestBookQueue, PrintQueue
from perf import counters


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    versions.reset_for_tests()
    counters.reset_for_tests()
    # The gate's "now" readers: no feed gap and no stuck IB loop unless a test says so.
    from ibkr import feed_pulse
    from perf import stall_watch

    monkeypatch.setattr(feed_pulse, "gaps_for_tape", lambda now=None: [])
    monkeypatch.setattr(stall_watch, "stalled_ms", lambda name: 0.0)
    import sim.mode

    monkeypatch.setattr(sim.mode, "is_replay_desk", lambda: False)   # the live feed, unless a test says so
    yield
    versions.reset_for_tests()


# ── versions ──────────────────────────────────────────────────────────────


def test_a_version_knows_when_the_next_one_replaced_it():
    first = versions.bump(versions.BOOK, "apus", at=100.0)
    versions.bump(versions.BOOK, "APUS", at=101.5)
    assert first.seq == 1
    assert versions.latest(versions.BOOK, "APUS").seq == 2
    assert versions.replaced(versions.BOOK, "APUS", 2).current is True
    replaced = versions.replaced(versions.BOOK, "APUS", 1)
    assert replaced.current is False and replaced.at == 101.5


def test_a_version_older_than_the_history_counts_from_the_oldest_kept(monkeypatch):
    track_keep = 3
    monkeypatch.setattr(versions, "MARKET_VIEW_HISTORY_KEEP", track_keep)
    versions.reset_for_tests()
    for i in range(10):
        versions.bump(versions.QUOTE, "XYZ", at=1000.0 + i)
    gone = versions.replaced(versions.QUOTE, "XYZ", 2)
    assert gone.before_history is True and gone.at == 1007.0   # the oldest kept: replaced before that


def test_a_version_nova_never_issued_is_unknown():
    versions.bump(versions.BOOK, "XYZ")
    assert versions.replaced(versions.BOOK, "XYZ", 5).unknown is True
    assert versions.replaced(versions.BOOK, "XYZ", 0).unknown is True
    assert versions.replaced(versions.BOOK, "NONE", 1).unknown is True


# ── the hand-off: thread-safe, woken, never a backlog ─────────────────────


def _book(seq: int, price: float) -> BookVersion:
    return BookVersion(seq, float(seq), {"bids": [{"price": price}], "asks": [], "l1_fallback": False})


def test_a_book_put_from_another_thread_wakes_the_socket_at_once():
    """The old asyncio.Queue filled from the IB thread never woke the socket's loop: a frame waited
    for some other wake-up. Nothing else runs on this loop, so only the queue's own wake can end the wait."""

    async def run() -> tuple[BookVersion, float]:
        q = LatestBookQueue()

        def produce() -> None:
            time.sleep(0.05)
            for seq, price in ((1, 6.58), (2, 6.56), (3, 6.50)):
                q.put_nowait(_book(seq, price))

        start = time.perf_counter()
        threading.Thread(target=produce, daemon=True).start()
        item = await asyncio.wait_for(q.get(), timeout=5.0)
        return item, time.perf_counter() - start

    item, waited = asyncio.run(run())
    assert waited < 1.0
    assert item.seq >= 1
    # Whatever got there first, the queue never holds more than the newest book.


def test_a_viewer_gets_the_newest_book_and_counts_the_rest():
    q = LatestBookQueue()
    for seq, price in ((1, 6.58), (2, 6.56), (3, 6.50)):
        q.put_nowait(_book(seq, price))
    assert q.qsize() == 1
    assert q.get_nowait().book["bids"][0]["price"] == 6.50
    assert counters.read()["depth.viewer_skipped"] == 2
    with pytest.raises(asyncio.QueueEmpty):
        q.get_nowait()


def test_every_print_from_another_thread_arrives_in_order_and_at_once():
    from ibkr.tape_stream import stream_batches

    async def run() -> list[int]:
        q = PrintQueue(4096)
        got: list[int] = []

        def produce() -> None:
            for i in range(1000):
                q.put_nowait({"type": "print", "symbol": "XYZ", "i": i})

        threading.Thread(target=produce, daemon=True).start()
        gen = stream_batches(q)
        while len(got) < 1000:
            batch = await asyncio.wait_for(gen.__anext__(), timeout=5.0)
            if batch is not None:
                got.extend(p["i"] for p in batch)
        await gen.aclose()
        return got

    assert asyncio.run(run()) == list(range(1000))


def test_a_print_queue_drops_its_oldest_past_its_size():
    q = PrintQueue(3)
    for i in range(5):
        q.put_nowait({"i": i})
    assert [p["i"] for p in q.drain_nowait()] == [2, 3, 4]
    assert counters.read()["tape.viewer_dropped"] == 2


# ── the Level 2 line sends a book only when it changed ────────────────────


def test_an_unchanged_book_is_not_a_new_version(monkeypatch):
    from ibkr.depth import handlers, state
    from tests.depth_ticks import depth_ticker, dom_ticks

    import sim.mode

    monkeypatch.setattr(sim.mode, "is_replay_desk", lambda: False)
    state.reset_all()
    q = state.open_viewer_queue("APUS")
    ticker = depth_ticker(bids=[(6.50, 400)], asks=[(6.55, 700)])
    handlers.on_update_book(ticker, "APUS")
    # An L1 tick or a print on the same contract fires the handler with no row operations.
    handlers.on_update_book(SimpleNamespace(domTicks=[]), "APUS")
    handlers.on_update_book(SimpleNamespace(domTicks=[]), "APUS")
    assert state.book_version("APUS").seq == 1
    assert q.get_nowait().seq == 1 and q.qsize() == 0
    handlers.on_update_book(SimpleNamespace(domTicks=dom_ticks(bids=[(6.49, 100)], asks=[(6.55, 700)])), "APUS")
    assert state.book_version("APUS").seq == 2
    state.reset_all()


def test_book_and_beat_frames_say_how_current_the_book_is():
    import json

    from ibkr.depth.stream import beat_frame, book_frame

    item = BookVersion(7, 123.5, {"bids": [], "asks": [], "l1_fallback": False})
    frame = json.loads(book_frame("APUS", item, now=124.0))
    assert frame == {"type": "book", "symbol": "APUS", "data": item.book, "seq": 7, "at": 123.5, "sent": 124.0}
    assert json.loads(beat_frame("APUS", now=125.0)) == {
        "type": "beat", "symbol": "APUS", "seq": 0, "at": None, "now": 125.0,
    }
    versions.bump(versions.BOOK, "APUS", at=126.0)
    assert json.loads(beat_frame("APUS", now=127.0))["seq"] == 1


# ── the gate ──────────────────────────────────────────────────────────────


def _cmd(*, view=..., source="manual", operation="place", act_ms=None, arrival_ms=None, timing=True):
    act = act_ms if act_ms is not None else time.time() * 1000.0
    arrival = arrival_ms if arrival_ms is not None else act + 30.0
    if view is ...:
        view = {"schema_version": 1, "symbol": "APUS", "action_wall_ms": act,
                "instance": instance_identity.INSTANCE_ID, "book": None, "quote": None, "desk": None}
    return SimpleNamespace(
        operation=operation, source=source, symbol="APUS", view=view,
        client_timing={"action_wall_ms": act} if timing else None,
        backend_ingress_wall_ns=int(arrival * 1e6),
    )


def test_flatten_kill_cancels_and_novas_own_senders_are_never_gated():
    assert gate.check(_cmd(source="flatten", view=None)).verdict == "exempt"
    assert gate.check(_cmd(source="kill", view=None)).verdict == "exempt"
    assert gate.check(_cmd(operation="cancel", view=None)).verdict == "exempt"
    assert gate.check(_cmd(source="bot", view=None)).verdict == "exempt"
    assert gate.check(_cmd(view=None, timing=False)).verdict == "exempt"   # not from the desk's routes


def test_a_desk_order_without_its_view_is_refused():
    check = gate.check(_cmd(view=None))
    assert check.refused and check.code == VIEW_MISSING
    assert "Flatten and cancels still work" in (check.text or "")


def test_the_apus_sell_is_refused_its_book_had_been_replaced_for_seconds(monkeypatch):
    """The screen showed version 1 (bid 6.58), replaced 6 s before the click."""
    act = time.time() * 1000.0
    versions.bump(versions.BOOK, "APUS", at=act / 1000.0 - 7.0)
    versions.bump(versions.BOOK, "APUS", at=act / 1000.0 - 6.0)
    from ibkr.depth import state

    monkeypatch.setattr(state, "current_book",
                        lambda sym: {"bids": [{"price": 6.50}], "asks": [{"price": 6.55}], "l1_fallback": False})
    cmd = _cmd(act_ms=act)
    cmd.view["book"] = {"seq": 1, "at": act / 1000.0 - 7.0, "bid": 6.58, "ask": 6.65}
    check = gate.check(cmd)
    assert check.code == VIEW_STALE
    assert check.measures["book_lag_ms"] == pytest.approx(6000.0, abs=1.0)
    assert "6.58" in check.text and "6.5 x 6.55" in check.text


def test_a_book_replaced_a_moment_before_the_click_is_fine():
    act = time.time() * 1000.0
    versions.bump(versions.BOOK, "APUS", at=act / 1000.0 - 1.0)
    versions.bump(versions.BOOK, "APUS", at=act / 1000.0 - 0.1)   # in flight to the desk
    cmd = _cmd(act_ms=act)
    cmd.view["book"] = {"seq": 1, "at": None, "bid": 6.5, "ask": 6.55}
    check = gate.check(cmd)
    assert check.verdict == "ok" and check.measures["book_lag_ms"] == pytest.approx(100.0, abs=1.0)


def test_a_stale_quote_is_refused_without_level_2():
    act = time.time() * 1000.0
    versions.bump(versions.QUOTE, "APUS", at=act / 1000.0 - 5.0)
    versions.bump(versions.QUOTE, "APUS", at=act / 1000.0 - 3.0)
    cmd = _cmd(act_ms=act)
    cmd.view["quote"] = {"seq": 1, "at": None, "price": 6.6}
    assert gate.check(cmd).code == VIEW_STALE


def test_an_order_that_reached_nova_late_is_refused():
    act = time.time() * 1000.0
    check = gate.check(_cmd(act_ms=act, arrival_ms=act + 2300.0))
    assert check.code == ORDER_LATE and "2.3 s" in check.text


def test_a_view_from_another_backend_or_version_is_refused():
    cmd = _cmd()
    cmd.view["instance"] = "not-this-process"
    assert gate.check(cmd).code == VIEW_STALE
    cmd = _cmd()
    cmd.view["book"] = {"seq": 9, "at": None, "bid": 1.0, "ask": 1.1}   # Nova never issued 9
    assert gate.check(cmd).code == VIEW_STALE


def test_clocks_that_disagree_are_never_trusted():
    act = time.time() * 1000.0
    check = gate.check(_cmd(act_ms=act + 5000.0, arrival_ms=act))
    assert check.code == VIEW_STALE and "clock" in check.text


def test_orders_wait_while_nova_itself_is_behind_the_feed(monkeypatch):
    from ibkr import feed_pulse
    from perf import stall_watch

    now = time.time()
    monkeypatch.setattr(feed_pulse, "gaps_for_tape", lambda t=None: [{"start": now - 4.0, "end": None}])
    check = gate.check(_cmd(), now=now)
    assert check.code == FEED_STALE and "no IBKR data" in check.text
    monkeypatch.setattr(feed_pulse, "gaps_for_tape", lambda t=None: [{"start": now - 9.0, "end": now - 2.0}])
    assert gate.check(_cmd(), now=now).code == FEED_STALE          # still catching up after the burst
    monkeypatch.setattr(feed_pulse, "gaps_for_tape", lambda t=None: [])
    monkeypatch.setattr(stall_watch, "stalled_ms", lambda name: 1200.0)
    check = gate.check(_cmd(), now=now)
    assert check.code == FEED_STALE and "stuck" in check.text


def test_a_replay_desk_is_never_held_by_the_live_feed(monkeypatch):
    """Sim off the live edge fills against its recording: a gap in IBKR's live feed or a stuck IB
    thread says nothing about that market, so neither refuses a replay order."""
    import sim.mode
    from ibkr import feed_pulse
    from perf import stall_watch

    now = time.time()
    monkeypatch.setattr(feed_pulse, "gaps_for_tape", lambda t=None: [{"start": now - 4.0, "end": None}])
    monkeypatch.setattr(stall_watch, "stalled_ms", lambda name: 1200.0)
    monkeypatch.setattr(sim.mode, "is_replay_desk", lambda: True)
    check = gate.check(_cmd(), now=now)
    assert check.verdict == "ok" and check.record()["feed_gap"] is None
    monkeypatch.setattr(sim.mode, "is_replay_desk", lambda: False)
    assert gate.check(_cmd(), now=now).code == FEED_STALE


def test_the_send_is_refused_when_the_click_is_too_long_ago():
    act = time.time() * 1000.0
    assert gate.late_at_send(_cmd(act_ms=act), now=(act + 100.0) / 1000.0) is None
    late = gate.late_at_send(_cmd(act_ms=act), now=(act + ORDER_MAX_SEND_MS + 400.0) / 1000.0)
    assert late is not None and late.code == ORDER_LATE


def test_the_door_refuses_a_stale_view_before_anything_is_sent(monkeypatch):
    from execution import inflight, service, store, telemetry
    from execution.models import ExecutionCommand
    from sim.mode import reset_for_tests as reset_venue, set_venue

    reset_venue()
    inflight.reset_for_tests()
    telemetry.reset_for_tests()
    set_venue("paper", persist=False)

    async def boom(*_a, **_k):
        raise AssertionError("a stale order reached the broker")

    monkeypatch.setattr(service, "send_broker", boom)
    act = time.time() * 1000.0
    versions.bump(versions.BOOK, "APUS", at=act / 1000.0 - 7.0)
    versions.bump(versions.BOOK, "APUS", at=act / 1000.0 - 6.0)
    cmd = ExecutionCommand(
        operation="place", idempotency_key=f"stale-{act}", source="manual", symbol="APUS", side="SELL",
        qty=100, order_type="LMT", limit_price=6.58, skip_risk=True,
        client_timing={"action_wall_ms": act, "action_performance_ms": 1.0,
                       "request_wall_ms": act, "request_performance_ms": 1.0},
        backend_ingress_wall_ns=int((act + 20.0) * 1e6),
        view={"schema_version": 1, "symbol": "APUS", "action_wall_ms": act,
              "instance": instance_identity.INSTANCE_ID,
              "book": {"seq": 1, "at": None, "bid": 6.58, "ask": 6.65}, "quote": None, "desk": None},
    )
    receipt = asyncio.run(service.execute(cmd, wait_ack=False))
    assert receipt.ok is False and receipt.reason_code == VIEW_STALE
    row = store.get_by_id(receipt.execution_id)
    assert row["status"] == "rejected"
    assert row["payload"]["view_check"]["code"] == VIEW_STALE
    assert row["payload"]["view"]["book"]["bid"] == 6.58
    inflight.reset_for_tests()
    telemetry.reset_for_tests()
    reset_venue()
