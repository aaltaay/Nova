"""A practice order its venue closes ends its execution rows at that moment (TNMG, 2026-10-02).

At 09:47:18 ET Nova's bot sent TNMG's first pullback as a Paper bracket: entry 77, a
BUY limit at 4.64 that rested (the venue answered ``Submitted``), and exits 78 and 79.
At 09:47:22 the bot cancelled the entry unfilled; the venue cancelled 77 and both exits.
Yet the bracket's row and the cancel's row stayed ``acked`` until the backend restarted
at 10:36, when the startup sweep read the venue's Cancelled as ``failed``. Three causes:
the practice broker skipped the notice for an order Nova cancelled, the cancel path set
only the place row's ``broker_status``, and no callback follows a practice venue's first
answer -- so a resting Paper order it filled later read ``acked`` too (AIFF, NXL, CNTB).
The bracket row's ``perm_id`` read 79: each exit leg's watch wrote its own over the entry's.

These run the real door on a Paper broker with each sender's own commands: Nova's bot,
Who trades the stock (Approve's bracket, Auto-entry's limit) and the ticket.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from constants_practice import (
    PRACTICE_BUYING_POWER_CODE,
    PRACTICE_ORDER_STATUS_EXPIRED,
    PRACTICE_TIF_EXPIRED_CODE,
)
from execution import inflight, service, store, telemetry
from execution.models import ExecutionCommand
from execution.order_outcome import ledger_close
from execution.store_facts import close_venue_order, mark_place_cancelled
from ibkr import safety as _safety
from practice import broker as practice_broker
from practice import order_rules
from practice.broker import for_venue, reset_for_tests
from routes import trading_execution as route
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue

NOW = 1_700_000_000.0
SYM = "IMCC"


class FakeLive:
    """A live market that prices IMCC at 9.98 x 10.02 and never prints on its own."""

    def reference(self, symbol: str) -> Reference:
        return Reference(10.0, 9.98, 10.02, live=True) if symbol == SYM else Reference(None, live=True)

    def admission(self, symbol: str):
        return (True, "OK", None) if symbol == SYM else (False, "dark", "PRACTICE_NO_LIVE_PRINT")

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return NOW

    def session_close_ts(self, ts: float) -> float:
        return ts + 86_400


@pytest.fixture
def paper(monkeypatch):
    reset_venue()
    reset_for_tests()
    service.reset_for_tests()
    store.init_db()
    monkeypatch.setattr(practice_broker, "LiveReference", FakeLive)
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    yield SimpleNamespace(broker=for_venue("paper"))
    service.reset_for_tests()
    inflight.reset_for_tests()
    reset_for_tests()
    reset_venue()


def _open_ids() -> set[str]:
    """Every row a startup sweep would still have to resolve, this run's included."""
    return {row["id"] for row in store.non_terminal_rows(exclude_current_boot=False)}


# -- each sender's own bracket and cancel ---------------------------------------
async def _bot(attempt: str):
    from bot.first_pullback import orders

    trade = {"venue": "paper", "setup_id": f"IMCC-{attempt}", "symbol": SYM, "qty": 1,
             "entry_planned": 9.90, "target1": 10.50, "stop": 9.50, "setup_type": "first_pullback"}
    placed = await orders.place_entry(trade)
    return placed, lambda oid: orders.cancel(trade, oid)


async def _approve(attempt: str):
    from stock_mode import orders

    trade = {"kind": "approve", "venue": "paper", "symbol": SYM, "attempt": attempt, "qty": 1,
             "entry": 9.90, "stop": 9.50, "target": 10.50, "setup_type": "first_pullback"}
    placed = await orders.send_bracket(trade)
    return placed, lambda oid: orders.cancel(trade, oid, source="manual")


async def _ticket(attempt: str):
    req = route.OrderRequest(symbol=SYM, side="BUY", qty=1, order_type="LMT", limit_price=9.90,
                             take_profit_price=10.50, stop_loss_price=9.50)
    placed = await service.execute(route._manual_order_command(req, f"ticket-{attempt}", None, 0))

    def cancel(oid: int):  # the ticket's Cancel waits for the venue's answer (the route's own call)
        return service.execute(ExecutionCommand(
            operation="cancel", idempotency_key=f"ticket-cancel-{attempt}", source="manual",
            order_id=oid, skip_risk=True, expected_venue="paper",
        ))

    return placed, cancel


@pytest.mark.asyncio
@pytest.mark.parametrize("send", [_bot, _approve, _ticket], ids=["bot", "approve", "ticket"])
async def test_a_bracket_cancelled_unfilled_ends_both_rows_cancelled_at_once(paper, send) -> None:
    placed, cancel = await send("tnmg")
    p = placed.parent_order_id
    assert (placed.ok, placed.operation, placed.broker_status) == (True, "bracket", "Submitted"), placed.error
    assert store.get_by_id(placed.execution_id)["status"] == "acked"  # resting, like TNMG's 77

    done = await cancel(p)

    assert (done.ok, done.broker_status, done.error) == (True, "Cancelled", None)
    bracket = store.get_by_id(placed.execution_id)
    assert (bracket["status"], bracket["broker_status"], bracket["error"]) == ("cancelled", "Cancelled", None)
    assert bracket["perm_id"] == p  # the entry's, never an exit leg's (TNMG's row read 79)
    cancel_row = store.get_by_id(done.execution_id)
    assert (cancel_row["status"], cancel_row["broker_status"], cancel_row["error"]) == (
        "cancelled", "Cancelled", None,
    )
    assert _open_ids().isdisjoint({placed.execution_id, done.execution_id})
    assert paper.broker.working_orders() == []  # the exits went with their entry
    assert inflight.committed_qty(SYM, "BUY") == 0.0


@pytest.mark.asyncio
async def test_auto_entrys_limit_cancelled_unfilled_ends_both_rows_cancelled(paper) -> None:
    from stock_mode import orders

    trade = {"kind": "auto_entry", "venue": "paper", "symbol": SYM, "attempt": 1, "qty": 1,
             "entry": 9.90, "setup_type": "first_pullback"}
    placed = await orders.place_entry(trade)
    assert (placed.ok, placed.broker_status) == (True, "Submitted"), placed.error

    done = await orders.cancel(trade, placed.order_id)

    assert store.get_by_id(placed.execution_id)["status"] == "cancelled"
    assert store.get_by_id(done.execution_id)["status"] == "cancelled"


# -- what the venue closes by itself, after its first answer --------------------
def _limit_buy(key: str, price: float = 9.90) -> ExecutionCommand:
    return ExecutionCommand(
        operation="place", idempotency_key=key, source="manual", symbol=SYM, side="BUY",
        qty=1, order_type="LMT", limit_price=price, skip_risk=True,
    )


@pytest.mark.asyncio
async def test_a_resting_order_the_venue_fills_later_reads_filled_then(paper) -> None:
    """AIFF, NXL and CNTB read ``acked`` until a restart's sweep, hours or days later."""
    placed = await service.execute(_limit_buy("rest-then-fill"))
    assert store.get_by_id(placed.execution_id)["status"] == "acked"

    paper.broker.try_fill_working(SYM, [(NOW + 5, 9.89)])

    row = store.get_by_id(placed.execution_id)
    assert (row["status"], row["broker_status"], row["error"]) == ("filled", "Filled", None)
    assert row["filled_ns"] is not None
    assert placed.execution_id not in _open_ids()


@pytest.mark.asyncio
async def test_a_bracket_that_fills_and_exits_keeps_the_entrys_row_and_perm_id(paper) -> None:
    placed = await service.execute(route._manual_order_command(route.OrderRequest(
        symbol=SYM, side="BUY", qty=1, order_type="LMT", limit_price=9.90,
        take_profit_price=10.50, stop_loss_price=9.50,
    ), "fill-and-exit", None, 0))
    p = placed.parent_order_id

    paper.broker.try_fill_working(SYM, [(NOW + 5, 9.89)])     # the entry fills; its exits wake
    paper.broker.try_fill_working(SYM, [(NOW + 9, 10.51)])    # the target fills; the stop is cancelled

    row = store.get_by_id(placed.execution_id)
    assert (row["status"], row["broker_status"], row["perm_id"]) == ("filled", "Filled", p)
    assert paper.broker.working_orders() == []
    stop = telemetry.watch_order(p + 2, venue="paper")
    assert (stop.leg_role, stop.latest_status) == ("stop", "Cancelled")  # the exit's own watch heard it


@pytest.mark.asyncio
async def test_a_day_order_that_expires_reads_cancelled_with_its_reason(paper) -> None:
    placed = await service.execute(_limit_buy("rest-then-expire"))

    paper.broker.expire_due(now=NOW + 86_400 + 1)

    row = store.get_by_id(placed.execution_id)
    assert (row["status"], row["broker_status"], row["reason_code"], row["error"]) == (
        "cancelled", PRACTICE_ORDER_STATUS_EXPIRED, PRACTICE_TIF_EXPIRED_CODE, None,
    )


@pytest.mark.asyncio
async def test_a_resting_order_refused_at_its_fill_reads_failed_in_the_venues_words(paper, monkeypatch) -> None:
    placed = await service.execute(_limit_buy("rest-then-refused"))
    monkeypatch.setattr(
        order_rules, "fill_refusal",
        lambda *_a, **_k: ("Not enough buying power at the fill", PRACTICE_BUYING_POWER_CODE),
    )

    paper.broker.try_fill_working(SYM, [(NOW + 5, 9.89)])

    row = store.get_by_id(placed.execution_id)
    assert (row["status"], row["broker_status"], row["reason_code"], row["error"]) == (
        "failed", "Cancelled", PRACTICE_BUYING_POWER_CODE, "Not enough buying power at the fill",
    )


# -- the ledger writes themselves -----------------------------------------------
def _row(key: str, *, mode: str, order_id: int, operation: str = "place", status: str = "acked") -> str:
    execution_id, _ = store.reserve(
        idempotency_key=key, operation=operation, source="manual", symbol=SYM, received_ns=1,
    )
    store.update_stages(execution_id, status=status, order_id=order_id, mode=mode, broker_status="Submitted")
    return execution_id


def test_one_venues_close_never_closes_anothers_order_with_the_same_id() -> None:
    """Practice ids restart at 1 per venue: Sim's order 5 is not Paper's."""
    store.init_db()
    paper_row = _row("ids-paper", mode="paper", order_id=5)
    sim_row = _row("ids-sim", mode="sim", order_id=5)
    cancel_row = _row("ids-sim-cancel", mode="sim", order_id=5, operation="cancel")

    assert close_venue_order(5, mode="sim", status="cancelled", broker_status="Cancelled") == [sim_row]

    assert store.get_by_id(sim_row)["status"] == "cancelled"
    assert store.get_by_id(paper_row)["status"] == "acked"
    assert store.get_by_id(cancel_row)["status"] == "acked"  # a cancel row is its send path's
    assert mark_place_cancelled(order_id=5, perm_id=5, mode="paper", close=True) == paper_row
    assert (store.get_by_id(paper_row)["status"], store.get_by_id(paper_row)["broker_status"]) == (
        "cancelled", "Cancelled",
    )


@pytest.mark.parametrize("status, code, error, want", [
    ("Filled", None, None, ("filled", None, None)),
    ("Cancelled", None, None, ("cancelled", None, None)),
    ("Cancelled", "PRACTICE_PARENT_CANCELLED", "Bracket exit cancelled: its entry was cancelled",
     ("cancelled", "PRACTICE_PARENT_CANCELLED", None)),
    ("Expired", PRACTICE_TIF_EXPIRED_CODE, "DAY order expired at the session close",
     ("cancelled", PRACTICE_TIF_EXPIRED_CODE, None)),
    ("Cancelled", PRACTICE_BUYING_POWER_CODE, "Not enough buying power at the fill",
     ("failed", PRACTICE_BUYING_POWER_CODE, "Not enough buying power at the fill")),
    ("Inactive", None, None, ("failed", None, "The venue closed the order (Inactive)")),
])
def test_ledger_close_reads_a_cancel_as_cancelled_and_a_refusal_as_failed(status, code, error, want) -> None:
    out = ledger_close(status, reason_code=code, error=error)
    assert (out["status"], out["reason_code"], out["error"]) == want
    assert out["broker_status"] == status


def test_ledger_close_leaves_a_working_order_alone() -> None:
    assert ledger_close("Submitted") is None and ledger_close("PreSubmitted") is None and ledger_close(None) is None
