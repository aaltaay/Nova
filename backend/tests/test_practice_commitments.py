"""Practice orders free their in-flight shares when they resolve (QA R7 / R14 / C30, 2026-09-22).

R7: the practice matcher filled resting orders through ``practice.watch`` but
never released the ``execution.inflight`` commitment the execution door took
at placement, so every filled resting SELL stayed "already sent" and the last
shares could not be sold until a restart ("SELL qty 1.0 exceeds 0.0 available
(long 1.0, 1.0 already sent)"). The IBKR callbacks release on Filled /
Cancelled; the practice venue now does too -- and for an expiry, an unwind and
a reset, which have no broker callback at all.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from execution import inflight
from execution.models import ExecutionCommand
from execution.validate import validate_command
from ibkr import safety as _safety
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests
from practice.ledger import Ledger
from practice.watch import release_commitment
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue

NOW = 1_700_000_000.0


class FakeLive:
    """A live market that always prices IMCC and never prints on its own."""

    def __init__(self) -> None:
        self.now = NOW

    def reference(self, symbol: str) -> Reference:
        return Reference(10.0, 9.98, 10.02, live=True) if symbol == "IMCC" else Reference(None, live=True)

    def admission(self, symbol: str):
        return (True, "OK", None) if symbol == "IMCC" else (False, "dark", "PRACTICE_NO_LIVE_PRINT")

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return self.now

    def session_close_ts(self, ts: float) -> float:
        return ts + 86_400


@pytest.fixture
def paper(monkeypatch):
    reset_venue()
    reset_for_tests()
    inflight.reset_for_tests()
    fake = FakeLive()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: fake)
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    yield SimpleNamespace(broker=for_venue("paper"), ref=fake)
    inflight.reset_for_tests()
    reset_for_tests()
    reset_venue()


def _sell(qty: float, key: str) -> ExecutionCommand:
    return ExecutionCommand(
        operation="place", idempotency_key=key, source="manual",
        symbol="IMCC", side="SELL", qty=qty, order_type="MKT",
    )


def _rest_sell(paper, execution_id: str, qty: float = 1.0) -> int:
    """What the execution door does for a resting SELL: commit, place, attach the order id."""
    inflight.commit(execution_id, symbol="IMCC", side="SELL", qty=qty)
    raw = paper.broker.place("IMCC", "SELL", qty, "LMT", limit_price=10.5)
    assert raw["broker_status"] == "Submitted"
    inflight.attach_order(execution_id, raw["order_id"])
    return int(raw["order_id"])


def test_a_filled_resting_sell_frees_its_shares_so_the_rest_can_be_sold(paper) -> None:
    assert paper.broker.place("IMCC", "BUY", 2, "MKT")["broker_status"] == "Filled"
    _rest_sell(paper, "exec-rest-1")
    assert inflight.committed_qty("IMCC", "SELL") == 1.0

    filled = paper.broker.try_fill_working("IMCC", [(NOW + 5, 10.6)])

    assert [row["status"] for row in filled] == ["Filled"]
    assert inflight.committed_qty("IMCC", "SELL") == 0.0
    assert paper.broker.positions()[0]["qty"] == 1
    ok, detail, code = validate_command(_sell(1, "sell-the-rest"))
    assert (ok, code) == (True, None), detail


def test_two_filled_resting_sells_leave_nothing_already_sent(paper) -> None:
    paper.broker.place("IMCC", "BUY", 3, "MKT")
    _rest_sell(paper, "exec-rest-a")
    _rest_sell(paper, "exec-rest-b")
    paper.broker.try_fill_working("IMCC", [(NOW + 5, 10.6)])
    assert inflight.committed_qty("IMCC", "SELL") == 0.0
    ok, detail, _ = validate_command(_sell(1, "last-share"))
    assert ok, detail


def test_an_expired_resting_sell_frees_its_shares(paper) -> None:
    paper.broker.place("IMCC", "BUY", 1, "MKT")
    _rest_sell(paper, "exec-rest-day")
    expired = paper.broker.expire_due(NOW + 90_000)
    assert [row["status"] for row in expired] == ["Expired"]
    assert inflight.committed_qty("IMCC", "SELL") == 0.0


def test_an_unwound_resting_order_frees_its_shares(paper) -> None:
    paper.broker.place("IMCC", "BUY", 1, "MKT")
    paper.ref.now = NOW + 10
    _rest_sell(paper, "exec-rest-late")
    assert paper.broker.unwind_to(NOW + 5) > 0  # the sell was placed after the playhead
    assert paper.broker.working_orders() == []
    assert inflight.committed_qty("IMCC", "SELL") == 0.0


def test_a_reset_frees_every_working_orders_shares(paper) -> None:
    paper.broker.place("IMCC", "BUY", 2, "MKT")
    _rest_sell(paper, "exec-rest-reset")
    paper.broker.reset()
    assert inflight.committed_qty("IMCC", "SELL") == 0.0


def test_a_still_working_order_keeps_its_commitment(paper) -> None:
    paper.broker.place("IMCC", "BUY", 2, "MKT")
    _rest_sell(paper, "exec-rest-open")
    paper.broker.try_fill_working("IMCC", [(NOW + 5, 10.4)])  # below the sell limit
    assert inflight.committed_qty("IMCC", "SELL") == 1.0


def test_an_order_id_alone_never_frees_another_symbols_commitment() -> None:
    inflight.reset_for_tests()
    inflight.commit("exec-other-venue", symbol="GRML", side="SELL", qty=1)
    inflight.attach_order("exec-other-venue", 3)
    assert release_commitment(3, {"symbol": "IMCC", "side": "SELL"}) is False
    assert inflight.committed_qty("GRML", "SELL") == 1.0
    assert release_commitment(3, {"symbol": "GRML", "side": "SELL"}) is True
    inflight.reset_for_tests()


# ── R14: an unwound order's id is never handed out again ─────────────────────

def test_an_unwind_never_reuses_an_order_id() -> None:
    ledger = Ledger(100_000, created_ts=NOW)
    first = ledger.alloc_id()
    ledger.place(_row(first), ts=NOW + 10, source="manual")
    ledger.unwind_to(NOW + 5)
    assert ledger.working_orders() == []
    assert ledger.alloc_id() == first + 1


# ── C30: a working or cancelled practice order shows no commission ───────────

def test_a_working_row_has_no_commission_until_it_fills(paper) -> None:
    paper.broker.place("IMCC", "BUY", 2, "MKT")
    paper.broker.place("IMCC", "SELL", 1, "LMT", limit_price=10.5)
    working = paper.broker.working_orders()
    assert [row["commission"] for row in working] == [None]
    paper.broker.try_fill_working("IMCC", [(NOW + 5, 10.6)])
    filled = [row for row in paper.broker.closed_orders() if row["side"] == "SELL"]
    assert filled and filled[0]["commission"] is not None


def test_a_cancelled_row_and_an_older_ledgers_zero_stay_blank() -> None:
    legacy = _row(1)
    legacy["commission"] = 0.0  # what placed events carried before the fix
    ledger = Ledger(100_000, created_ts=NOW)
    ledger.place(legacy, ts=NOW + 1, source="manual")
    assert ledger.working_orders()[0]["commission"] is None
    ledger.cancel(1, ts=NOW + 2)
    assert ledger.closed_orders()[0]["commission"] is None


def _row(oid: int) -> dict:
    return {
        "order_id": oid, "perm_id": oid, "symbol": "IMCC", "side": "BUY", "qty": 1.0,
        "filled_qty": 0.0, "remaining_qty": 1.0, "order_type": "LMT", "limit_price": 9.0,
        "stop_price": None, "avg_fill_price": None, "outside_rth": True, "status": "Submitted",
        "commission": None, "placed_ts": NOW, "tif": "GTC", "expires_ts": None,
    }
