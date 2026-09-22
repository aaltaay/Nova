"""Bots learn about Sim time travel (ADR 020 decision 3, second pass 2026-09-21).

When the scratch account unwinds behind a backward scrub, a ``practice_rewind``
event -- ``{venue, playhead_ts, dropped_orders, dropped_fills}`` -- goes out on
the bot audit stream (the channel breaker and TTL events already use) and is
kept as ``last_rewind`` on the session payload for pollers. A forward move, or
a backward move that dropped nothing, tells nobody: the ledger did not change.
"""
from __future__ import annotations

from bot import audit, rewind
from bot.session import get_session
from sim import broker, feed
from sim import session_clock as clock
from tests.test_sim_practice import TAPE, historical, isolated  # noqa: F401 -- autouse fixture

T0 = 1_700_000_000.0


# ── the notice itself ─────────────────────────────────────────────────────────

def test_publish_records_last_and_pushes_an_audit_entry() -> None:
    queue = audit.subscribe()
    try:
        assert rewind.last() is None
        event = rewind.publish(venue="sim", playhead_ts=T0, dropped_orders=2, dropped_fills=1)
        assert event["venue"] == "sim" and event["playhead_ts"] == T0
        assert (event["dropped_orders"], event["dropped_fills"]) == (2, 1)
        assert rewind.last() == event
        pushed = queue.get_nowait()
    finally:
        audit.unsubscribe(queue)
    assert pushed["action"] == "practice_rewind" and pushed["outcome"] == "ok"
    assert {k: pushed["inputs"][k] for k in ("venue", "playhead_ts", "dropped_orders", "dropped_fills")} == {
        "venue": "sim", "playhead_ts": T0, "dropped_orders": 2, "dropped_fills": 1,
    }
    assert audit.list_entries(limit=5)[-1]["action"] == "practice_rewind"


def test_session_payload_exposes_last_rewind_for_pollers() -> None:
    assert get_session()["last_rewind"] is None
    rewind.publish(venue="sim", playhead_ts=T0, dropped_orders=1, dropped_fills=0)
    assert get_session()["last_rewind"]["dropped_orders"] == 1


def test_reset_forgets_the_notice() -> None:
    rewind.publish(venue="sim", playhead_ts=T0, dropped_orders=1, dropped_fills=0)
    rewind.reset_for_tests()
    assert rewind.last() is None


def test_publish_never_raises_when_the_audit_stream_fails(monkeypatch) -> None:
    def boom(**_kw):
        raise OSError("audit file locked")

    monkeypatch.setattr("bot.audit.record", boom)
    event = rewind.publish(venue="sim", playhead_ts=T0, dropped_orders=1, dropped_fills=1)
    assert rewind.last() == event


# ── through the Sim venue: a backward scrub publishes, forward does not ──────

def test_scrubbing_back_over_a_fill_publishes_practice_rewind() -> None:
    historical(TAPE)
    clock.scrub_to_second(30)
    assert broker.place("IMCC", "BUY", 10, "MKT")["broker_status"] == "Filled"
    assert rewind.last() is None

    clock.scrub_to_second(20)

    seen = rewind.last()
    assert seen is not None
    assert seen["venue"] == "sim"
    assert seen["playhead_ts"] == clock.now_et().timestamp()
    assert (seen["dropped_orders"], seen["dropped_fills"]) == (1, 1)
    assert get_session()["last_rewind"] == seen


def test_a_resting_order_dropped_before_its_fill_counts_as_an_order_only() -> None:
    historical(TAPE)
    clock.scrub_to_second(30)
    broker.place("IMCC", "BUY", 5, "LMT", limit_price=10.5)
    feed.match_practice_fills()

    clock.scrub_to_second(20)

    assert (rewind.last()["dropped_orders"], rewind.last()["dropped_fills"]) == (1, 0)


def test_a_forward_move_or_an_empty_unwind_publishes_nothing() -> None:
    historical(TAPE)
    clock.scrub_to_second(30)
    broker.place("IMCC", "BUY", 10, "MKT")

    clock.scrub_to_second(80)  # forward: nothing is re-placed, nothing is dropped
    assert rewind.last() is None

    clock.scrub_to_second(40)  # back, but still after the fill: the ledger did not change
    assert rewind.last() is None


def test_the_unwind_stands_even_if_the_notice_fails(monkeypatch) -> None:
    historical(TAPE)
    clock.scrub_to_second(30)
    broker.place("IMCC", "BUY", 10, "MKT")

    def boom(**_kw):
        raise RuntimeError("bots unreachable")

    monkeypatch.setattr(rewind, "publish", boom)
    clock.scrub_to_second(20)

    assert broker.positions() == [] and broker.closed_orders() == []
