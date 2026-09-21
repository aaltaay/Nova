"""Time-in-force on the practice venues: DAY expires at the session close, GTC persists.

Paper: the matcher pass expires due orders after matching prints; a print past
the close never fills a DAY order; the expiry survives a reload as an
``expired`` event and a GTC order survives the close. Sim: the feed tick
expires at the replayed session's close (the loaded window's end) and a scrub
back before it restores the order. The execution door threads ``tif`` through
to the broker row.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from constants_practice import (
    PRACTICE_SESSION_CLOSE_HOUR_ET,
    PRACTICE_TIF_EXPIRED_CODE,
    PRACTICE_TIF_EXPIRED_REASON,
)
from practice import broker as practice_broker, matcher, tape_hold
from practice.broker import for_venue, reset_for_tests
from practice.clock import ET
from practice.ledger import EVENT_EXPIRED, EVENT_PLACED
from sim.fill_model import Reference

MORNING = datetime(2026, 9, 21, 10, 0, tzinfo=ET)
NOW = MORNING.timestamp()
CLOSE = MORNING.replace(hour=PRACTICE_SESSION_CLOSE_HOUR_ET).timestamp()


class FakeLive:
    """The live feed as the Paper venue sees it: IMCC quoted, its own clock."""

    def __init__(self) -> None:
        self.now = NOW
        self.prints: list[tuple[float, float]] = []

    def reference(self, symbol: str) -> Reference:
        return Reference(10.0, 9.98, 10.02, live=True) if symbol == "IMCC" else Reference(None, live=True)

    def admission(self, symbol: str):
        return (True, "OK", None) if symbol == "IMCC" else (False, "dark", "PRACTICE_NO_LIVE_PRINT")

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return [(ts, px) for ts, px in self.prints if after_ts < ts <= through_ts]

    def now_ts(self) -> float:
        return self.now


@pytest.fixture
def paper(monkeypatch):
    reset_for_tests()
    matcher.reset_for_tests()
    fake = FakeLive()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: fake)

    async def reconcile(wanted):
        return {}

    monkeypatch.setattr(tape_hold, "reconcile", reconcile)
    yield SimpleNamespace(broker=for_venue("paper"), ref=fake)
    reset_for_tests()
    matcher.reset_for_tests()


# ── the row and its event ────────────────────────────────────────────────────

def test_a_day_order_carries_its_session_close_and_gtc_carries_none(paper) -> None:
    day = paper.broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.5)
    gtc = paper.broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.5, tif="gtc")
    rows = {r["order_id"]: r for r in paper.broker.working_orders()}
    assert (rows[day["order_id"]]["tif"], rows[day["order_id"]]["expires_ts"]) == ("DAY", CLOSE)
    assert (rows[gtc["order_id"]]["tif"], rows[gtc["order_id"]]["expires_ts"]) == ("GTC", None)
    placed = [e for e in paper.broker.ledger.events if e["type"] == EVENT_PLACED]
    assert [(e["row"]["tif"], e["row"]["expires_ts"]) for e in placed] == [("DAY", CLOSE), ("GTC", None)]


def test_a_tif_nova_never_places_is_refused_before_the_ledger_is_touched(paper) -> None:
    raw = paper.broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.5, tif="IOC")
    assert raw["ok"] is False and raw["reason_code"] == "TIF_INVALID"
    assert paper.broker.working_orders() == [] and paper.broker.ledger.events == []


# ── expiry on the Paper venue ────────────────────────────────────────────────

def test_expire_due_closes_a_day_order_at_the_close_with_the_expired_status(paper) -> None:
    raw = paper.broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.5)
    paper.ref.now = CLOSE - 1
    assert paper.broker.expire_due() == []
    paper.ref.now = CLOSE
    expired = paper.broker.expire_due()
    assert [(r["order_id"], r["status"], r["reason_code"], r["error"]) for r in expired] == [
        (raw["order_id"], "Expired", PRACTICE_TIF_EXPIRED_CODE, PRACTICE_TIF_EXPIRED_REASON),
    ]
    assert paper.broker.working_orders() == []
    closed = paper.broker.closed_orders()[0]
    assert closed["status"] == "Expired" and closed["remaining_qty"] == 10 and closed["filled_qty"] == 0
    assert paper.broker.positions() == [] and paper.broker.account_summary()["TotalCashValue"] == 100_000
    event = paper.broker.ledger.events[-1]
    assert (event["type"], event["ts"], event["code"]) == (EVENT_EXPIRED, CLOSE, PRACTICE_TIF_EXPIRED_CODE)


def test_a_gtc_order_never_expires(paper) -> None:
    paper.broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.5, tif="GTC")
    paper.ref.now = CLOSE + 3 * 24 * 3600
    assert paper.broker.expire_due() == []
    assert [r["tif"] for r in paper.broker.working_orders()] == ["GTC"]


def test_a_print_after_the_close_never_fills_a_day_order_but_one_at_the_close_does(paper) -> None:
    day = paper.broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.5)
    gtc = paper.broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.5, tif="GTC")
    filled = paper.broker.try_fill_working("IMCC", [(CLOSE + 0.5, 9.4)])
    assert [r["order_id"] for r in filled] == [gtc["order_id"]]
    assert [r["order_id"] for r in paper.broker.working_orders()] == [day["order_id"]]
    assert [r["order_id"] for r in paper.broker.try_fill_working("IMCC", [(CLOSE, 9.4)])] == [day["order_id"]]


@pytest.mark.asyncio
async def test_the_matcher_pass_fills_up_to_the_close_then_expires_what_is_left(paper) -> None:
    filled_at_close = paper.broker.place("IMCC", "BUY", 5, "LMT", limit_price=9.5)
    left = paper.broker.place("IMCC", "BUY", 5, "LMT", limit_price=8.0)
    paper.ref.prints = [(CLOSE - 1, 9.4), (CLOSE + 1, 7.9)]  # the second print is after the close
    paper.ref.now = CLOSE + 2
    filled = await matcher.pass_once(paper.broker)
    assert [r["order_id"] for r in filled] == [filled_at_close["order_id"]]
    statuses = {r["order_id"]: r["status"] for r in paper.broker.closed_orders()}
    assert statuses == {filled_at_close["order_id"]: "Filled", left["order_id"]: "Expired"}
    assert paper.broker.working_orders() == []


def test_a_day_order_placed_after_the_close_works_the_next_session(paper) -> None:
    paper.ref.now = CLOSE + 3600
    raw = paper.broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.5)
    row = paper.broker.working_orders()[0]
    assert raw["broker_status"] == "Submitted" and row["expires_ts"] == CLOSE + 24 * 3600
    paper.ref.now = CLOSE + 24 * 3600 - 1
    assert paper.broker.expire_due() == []


# ── persistence ──────────────────────────────────────────────────────────────

def test_the_expiry_and_a_gtc_order_survive_a_reload_of_the_paper_ledger(paper) -> None:
    paper.broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.5)
    gtc = paper.broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.5, tif="GTC")
    paper.ref.now = CLOSE
    assert len(paper.broker.expire_due()) == 1
    reset_for_tests()
    again = for_venue("paper")
    assert [r["status"] for r in again.closed_orders()] == ["Expired"]
    assert [(r["order_id"], r["tif"]) for r in again.working_orders()] == [(gtc["order_id"], "GTC")]
    assert again.expire_due(CLOSE + 7 * 24 * 3600) == []


def test_a_restart_after_the_close_still_records_the_expiry_at_the_close(paper) -> None:
    raw = paper.broker.place("IMCC", "BUY", 10, "LMT", limit_price=9.5)
    reset_for_tests()
    again = for_venue("paper")
    assert [r["order_id"] for r in again.working_orders()] == [raw["order_id"]]
    paper.ref.now = CLOSE + 5 * 3600  # the process came back long after the close
    expired = again.expire_due()
    assert [r["status"] for r in expired] == ["Expired"] and again.ledger.events[-1]["ts"] == CLOSE


# ── the Sim venue: the replayed session's close, and time travel ─────────────

@pytest.fixture
def replay(monkeypatch):
    """A loaded IMCC replay whose session window closes at ``close_ts``; the clock is ours."""
    from sim import practice

    from tests.test_sim_practice import isolated  # noqa: F401 -- reset every Sim engine

    reset_for_tests()
    state = {"ts": 100.0, "close": 1000.0, "prints": []}
    monkeypatch.setattr(practice, "loaded", lambda: practice.Loaded("historical", "IMCC", ("k",)))
    monkeypatch.setattr(practice, "playhead_ts", lambda: state["ts"])
    monkeypatch.setattr(practice, "admission", lambda sym: (sym == "IMCC", "OK", None if sym == "IMCC" else "SIM_SYMBOL_MISMATCH"))
    monkeypatch.setattr(practice, "reference", lambda sym: Reference(10.0, 9.98, 10.02) if sym == "IMCC" else Reference(None))
    monkeypatch.setattr(practice, "prints_between", lambda sym, a, b: [(t, p) for t, p in state["prints"] if a < t <= b])
    from practice import reference as practice_reference

    monkeypatch.setattr(practice_reference.ReplayReference, "session_close_ts", lambda self, ts: state["close"])
    yield state
    reset_for_tests()


def test_the_sim_feed_expires_a_day_order_at_the_replayed_sessions_close(replay) -> None:
    from sim import broker, feed

    raw = broker.place("IMCC", "BUY", 5, "LMT", limit_price=9.0)
    assert broker.working_orders()[0]["expires_ts"] == 1000.0
    replay["ts"] = 999.0
    assert feed.expire_practice_orders() == []
    replay["ts"] = 1000.0
    assert [(r["order_id"], r["status"]) for r in feed.expire_practice_orders()] == [(raw["order_id"], "Expired")]
    assert broker.open_orders() == []


def test_the_sim_feed_tick_matches_prints_before_it_expires(replay) -> None:
    from sim import broker, feed
    from sim import session_clock as clock

    fills = broker.place("IMCC", "BUY", 5, "LMT", limit_price=9.5)
    rests = broker.place("IMCC", "BUY", 5, "LMT", limit_price=8.0)
    feed.match_practice_fills()  # anchors the fill cursor at the placement
    replay["prints"] = [(999.5, 9.4), (1000.5, 7.9)]
    replay["ts"] = 1001.0
    clock.set_paused(False)
    feed.tick()
    statuses = {r["order_id"]: r["status"] for r in broker.closed_orders()}
    assert statuses == {fills["order_id"]: "Filled", rests["order_id"]: "Expired"}


def test_scrubbing_back_before_the_close_restores_an_expired_sim_order(replay) -> None:
    from sim import broker, feed

    raw = broker.place("IMCC", "BUY", 5, "LMT", limit_price=9.0)
    replay["ts"] = 1000.0
    assert len(feed.expire_practice_orders()) == 1
    assert broker.unwind_to(500.0) == 1  # the expiry never happened
    assert [(r["order_id"], r["status"]) for r in broker.open_orders()] == [(raw["order_id"], "Submitted")]
    assert broker.closed_orders() == []


def test_the_replay_reference_names_the_loaded_windows_end_as_the_close() -> None:
    from practice.reference import ReplayReference
    from sim import session_clock as clock

    clock.reset_for_tests()
    try:
        clock.set_session_date("2026-09-18")
        clock.set_window("04:00", "09:30")
        inside = datetime(2026, 9, 18, 8, 0, tzinfo=ET).timestamp()
        assert ReplayReference().session_close_ts(inside) == datetime(2026, 9, 18, 9, 30, tzinfo=ET).timestamp()
    finally:
        clock.reset_for_tests()


def test_the_live_reference_names_the_desks_session_close() -> None:
    from practice.reference import LiveReference

    assert LiveReference().session_close_ts(NOW) == CLOSE
    assert LiveReference().session_close_ts(CLOSE) == (MORNING.replace(hour=PRACTICE_SESSION_CLOSE_HOUR_ET) + timedelta(days=1)).timestamp()


# ── the execution door threads tif through ───────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("tif", ["DAY", "GTC"])
async def test_send_practice_broker_threads_the_commands_tif_into_the_row(paper, tif: str) -> None:
    from execution import store
    from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
    from sim.execution import send_practice_broker

    store.init_db()

    def reject(execution_id, cmd, timings, detail, reason):
        return ExecutionReceipt(
            ok=False, execution_id=execution_id, operation=cmd.operation, source=cmd.source,
            idempotency_key=cmd.idempotency_key, error=detail, reason_code=reason, timings=timings,
        )

    cmd = ExecutionCommand(
        operation="place", idempotency_key=f"tif-{tif}", source="manual", symbol="IMCC",
        side="BUY", qty=1, order_type="LMT", limit_price=9.5, tif=tif,
    )
    receipt = await send_practice_broker(
        cmd, f"exec-{tif}", StageTimings(received_ns=0), broker=paper.broker, wait_ack=False, reject=reject,
    )
    assert receipt.ok is True and receipt.broker_status == "Submitted"
    row = paper.broker.working_orders()[0]
    assert (row["tif"], row["expires_ts"]) == (tif, CLOSE if tif == "DAY" else None)
