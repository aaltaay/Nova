"""The practice venues' own short rules (ADR 048; until then "no shorts", operator decision 2026-09-21).

A short is never inferred: a SELL past the held quantity without ``short_entry`` is refused
``PRACTICE_NO_SHORTS`` -- at admission in the execution door (``execution.validate`` via
``execution.practice_checks``) and again in ``PracticeBroker.place``, on every source. A short entry is
a SELL that opens from flat or adds to a short; while the account holds the stock long it is refused
``PRACTICE_SHORT_WHILE_LONG``, at placement and at the fill. Everything else a short needs -- its buy
stop, the hours, halts, SSR, borrow, margin and the cushion -- is the short check's
(``short_sale``; ``test_practice_shorts.py``). Closing and trimming sells are untouched.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from constants_practice import (
    PRACTICE_NO_SHORTS_CODE,
    PRACTICE_NO_SHORTS_REASON,
    PRACTICE_SHORT_WHILE_LONG_CODE,
)
from execution.models import ExecutionCommand
from execution.validate import validate_command
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests
from ibkr import safety as _safety
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue

NOW = 1_700_000_000.0
MESSAGE = PRACTICE_NO_SHORTS_REASON


class FakeLive:
    def __init__(self) -> None:
        self.now = NOW
        self.dark = False

    def reference(self, symbol: str) -> Reference:
        return Reference(10.0, 9.98, 10.02, live=True) if symbol == "IMCC" and not self.dark else Reference(None, live=True)

    def admission(self, symbol: str):
        if symbol == "IMCC" and not self.dark:
            return True, "OK", None
        return False, "dark", "PRACTICE_NO_LIVE_PRINT"

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return self.now


@pytest.fixture
def paper(monkeypatch):
    reset_venue()
    reset_for_tests()
    fake = FakeLive()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: fake)
    yield SimpleNamespace(broker=for_venue("paper"), ref=fake)
    reset_for_tests()
    reset_venue()


def _on(target: str) -> None:
    """Settle the venue and arm: a venue change disarms (ADR 018), and these tests are about shorts, not the latch."""
    set_venue(target)
    _safety.set_armed(True, reason="test")


def _cmd(**overrides) -> ExecutionCommand:
    fields = {
        "operation": "place", "idempotency_key": "no-shorts", "source": "manual",
        "symbol": "IMCC", "side": "SELL", "qty": 1, "order_type": "MKT",
    }
    fields.update(overrides)
    return ExecutionCommand(**fields)


# ── the broker ───────────────────────────────────────────────────────────────

def test_the_message_says_how_a_short_goes_out() -> None:
    assert PRACTICE_NO_SHORTS_CODE == "PRACTICE_NO_SHORTS"
    assert "short entry" in MESSAGE and "buy stop" in MESSAGE
    assert "not support" not in MESSAGE   # "Nova does not support short entries yet" ended with ADR 048


def test_a_plain_sell_from_flat_is_refused_and_never_touches_the_ledger(paper) -> None:
    raw = paper.broker.place("IMCC", "SELL", 1, "MKT")
    assert (raw["ok"], raw["reason_code"], raw["error"]) == (False, PRACTICE_NO_SHORTS_CODE, MESSAGE)
    assert paper.broker.ledger.events == [] and paper.broker.positions() == []


def test_a_sell_beyond_the_held_quantity_is_refused_but_closing_and_trimming_are_not(paper) -> None:
    assert paper.broker.place("IMCC", "BUY", 10, "MKT")["broker_status"] == "Filled"
    refused = paper.broker.place("IMCC", "SELL", 11, "MKT")
    assert refused["ok"] is False and refused["reason_code"] == PRACTICE_NO_SHORTS_CODE
    assert paper.broker.place("IMCC", "SELL", 3, "MKT")["broker_status"] == "Filled"
    assert paper.broker.place("IMCC", "SELL", 7, "LMT", limit_price=10.5)["broker_status"] == "Submitted"
    assert paper.broker.positions()[0]["qty"] == 7


def test_a_short_entry_opens_from_flat_and_adds_to_a_short(paper, short_market_open) -> None:
    first = paper.broker.place("IMCC", "SELL", 5, "LMT", limit_price=9.98, short_entry=True)
    assert (first["ok"], first["broker_status"], first["avg_fill_price"]) == (True, "Filled", 9.98)
    more = paper.broker.place("IMCC", "SELL", 3, "LMT", limit_price=9.98, short_entry=True)
    assert more["broker_status"] == "Filled"
    assert paper.broker.positions()[0]["qty"] == -8
    row = {int(r["order_id"]): r for r in paper.broker.closed_orders()}[first["order_id"]]
    assert (row["short_entry"], row["position_side"], row["effect"]) == (True, "short", "opens")


def test_a_short_entry_never_flips_a_long_and_is_never_a_buy(paper) -> None:
    paper.broker.place("IMCC", "BUY", 10, "MKT")
    raw = paper.broker.place("IMCC", "SELL", 1, "LMT", limit_price=9.98, short_entry=True)
    assert (raw["ok"], raw["reason_code"]) == (False, PRACTICE_SHORT_WHILE_LONG_CODE)
    assert "10 held" in raw["error"]
    raw = paper.broker.place("IMCC", "BUY", 1, "LMT", limit_price=9.98, short_entry=True)
    assert (raw["ok"], raw["reason_code"]) == (False, "SIDE_INVALID")
    assert paper.broker.positions()[0]["qty"] == 10


def test_a_resting_short_is_cancelled_at_the_fill_when_a_long_opened_since(paper, short_market_open) -> None:
    short = paper.broker.place("IMCC", "SELL", 5, "LMT", limit_price=10.40, short_entry=True)
    assert short["broker_status"] == "Submitted"
    paper.broker.place("IMCC", "BUY", 10, "MKT")
    paper.ref.now = NOW + 5
    assert paper.broker.try_fill_working("IMCC", [(NOW + 5, 10.45)]) == []
    row = {int(r["order_id"]): r for r in paper.broker.closed_orders()}[short["order_id"]]
    assert (row["status"], row["reason_code"]) == ("Cancelled", PRACTICE_SHORT_WHILE_LONG_CODE)
    assert paper.broker.positions()[0]["qty"] == 10


def test_admission_is_asked_before_the_no_shorts_rule_matching_the_execution_door(paper) -> None:
    paper.ref.dark = True
    assert paper.broker.place("IMCC", "SELL", 1, "MKT")["reason_code"] == "PRACTICE_NO_LIVE_PRINT"
    paper.ref.dark = False
    assert paper.broker.place("IMCC", "SELL", 1, "MKT")["reason_code"] == PRACTICE_NO_SHORTS_CODE


def test_a_protective_sell_may_close_a_position_but_never_open_a_short(paper) -> None:
    paper.broker.place("IMCC", "BUY", 10, "MKT")
    refused = paper.broker.place("IMCC", "SELL", 11, "MKT", protective=True, source="flatten")
    assert refused["reason_code"] == PRACTICE_NO_SHORTS_CODE
    paper.ref.dark = True  # the at-mark path closes a held position; an oversell neither closes nor is admitted
    assert paper.broker.place("IMCC", "SELL", 11, "MKT", protective=True, source="flatten")["ok"] is False
    closed = paper.broker.place("IMCC", "SELL", 10, "MKT", protective=True, source="flatten")
    assert closed["broker_status"] == "Filled" and paper.broker.positions() == []


def test_the_sim_broker_enforces_it_too(monkeypatch) -> None:
    from sim import practice

    monkeypatch.setattr(practice, "playhead_ts", lambda: 100.0)
    monkeypatch.setattr(practice, "admission", lambda sym: (True, "OK", None))
    monkeypatch.setattr(practice, "reference", lambda sym: Reference(10.0, 9.98, 10.02))
    reset_for_tests()
    sim = for_venue("sim")
    assert sim.place("IMCC", "SELL", 1, "MKT")["reason_code"] == PRACTICE_NO_SHORTS_CODE
    assert sim.place("IMCC", "BUY", 1, "MKT")["broker_status"] == "Filled"
    assert sim.place("IMCC", "SELL", 1, "MKT")["broker_status"] == "Filled"
    reset_for_tests()


# ── the execution door ───────────────────────────────────────────────────────

@pytest.mark.parametrize("target", ["paper", "sim"])
def test_validate_refuses_an_implicit_short_on_every_practice_venue(monkeypatch, target: str) -> None:
    fake = SimpleNamespace(
        reference=SimpleNamespace(admission=lambda symbol: (True, "OK", None)),
        ledger=SimpleNamespace(held_qty=lambda symbol: 10.0),
    )
    monkeypatch.setattr(practice_broker, "for_venue", lambda label: fake)
    _on(target)
    assert validate_command(_cmd(qty=11)) == (False, MESSAGE, PRACTICE_NO_SHORTS_CODE)
    assert validate_command(_cmd(qty=10)) == (True, "OK", None)
    assert validate_command(_cmd(qty=3)) == (True, "OK", None)
    assert validate_command(_cmd(side="BUY", qty=500)) == (True, "OK", None)
    # A short entry passes admission to the short check, which the door runs under its lock.
    short = _cmd(operation="bracket", qty=5, order_type="LMT", limit_price=10.0, entry_price=10.0,
                 stop_price=10.4, target_price=9.6, short_entry=True)
    assert validate_command(short) == (True, "OK", None)


def test_validate_refuses_a_protective_oversell(monkeypatch) -> None:
    fake = SimpleNamespace(
        reference=SimpleNamespace(admission=lambda symbol: (True, "OK", None)),
        ledger=SimpleNamespace(held_qty=lambda symbol: 10.0),
    )
    monkeypatch.setattr(practice_broker, "for_venue", lambda label: fake)
    _on("paper")
    assert validate_command(_cmd(source="flatten", qty=11)) == (False, MESSAGE, PRACTICE_NO_SHORTS_CODE)
    assert validate_command(_cmd(source="flatten", qty=10)) == (True, "OK", None)


def test_admission_is_still_asked_first_for_ordinary_sources(monkeypatch) -> None:
    fake = SimpleNamespace(
        reference=SimpleNamespace(admission=lambda symbol: (False, "no live print", "PRACTICE_NO_LIVE_PRINT")),
        ledger=SimpleNamespace(held_qty=lambda symbol: 0.0),
    )
    monkeypatch.setattr(practice_broker, "for_venue", lambda label: fake)
    _on("paper")
    assert validate_command(_cmd(side="BUY")) == (False, "no live print", "PRACTICE_NO_LIVE_PRINT")


def test_a_broker_without_a_ledger_reads_flat_so_a_sell_fails_closed(monkeypatch) -> None:
    fake = SimpleNamespace(reference=SimpleNamespace(admission=lambda symbol: (True, "OK", None)))
    monkeypatch.setattr(practice_broker, "for_venue", lambda label: fake)
    _on("paper")
    assert validate_command(_cmd(qty=1))[2] == PRACTICE_NO_SHORTS_CODE
    assert validate_command(_cmd(side="BUY", qty=1)) == (True, "OK", None)


@pytest.mark.asyncio
async def test_the_send_path_keeps_the_venues_code_on_the_receipt(paper) -> None:
    from execution import store
    from execution.models import ExecutionReceipt, StageTimings
    from sim.execution import send_practice_broker

    store.init_db()

    def reject(execution_id, cmd, timings, detail, reason):
        return ExecutionReceipt(
            ok=False, execution_id=execution_id, operation=cmd.operation, source=cmd.source,
            idempotency_key=cmd.idempotency_key, error=detail, reason_code=reason, timings=timings,
        )

    receipt = await send_practice_broker(
        _cmd(qty=1), "exec-no-shorts", StageTimings(received_ns=0), broker=paper.broker,
        wait_ack=False, reject=reject,
    )
    assert receipt.ok is False and receipt.reason_code == PRACTICE_NO_SHORTS_CODE and receipt.error == MESSAGE
    assert paper.broker.ledger.events == []
