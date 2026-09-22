"""No shorts on the practice venues: a SELL is only ever risk-reducing (operator decision, 2026-09-21).

An opening short -- a SELL beyond the held quantity, or any ``short_entry`` --
is refused ``PRACTICE_NO_SHORTS`` with one message, at admission in the
execution door (``execution.validate`` via ``execution.practice_checks``) and
again in ``PracticeBroker.place``, on every source. Closing and trimming
sells are untouched.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from constants_practice import PRACTICE_NO_SHORTS_CODE, PRACTICE_NO_SHORTS_REASON
from execution.models import ExecutionCommand
from execution.validate import validate_command
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests
from ibkr import safety as _safety
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue

NOW = 1_700_000_000.0
MESSAGE = "Nova does not support short entries yet"


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

def test_the_message_is_the_operators_words() -> None:
    assert PRACTICE_NO_SHORTS_REASON == MESSAGE and PRACTICE_NO_SHORTS_CODE == "PRACTICE_NO_SHORTS"


def test_a_sell_from_flat_is_refused_and_never_touches_the_ledger(paper) -> None:
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


def test_short_entry_is_refused_whatever_is_held_and_on_any_side(paper) -> None:
    paper.broker.place("IMCC", "BUY", 10, "MKT")
    for side in ("SELL", "BUY"):
        raw = paper.broker.place("IMCC", side, 1, "MKT", short_entry=True)
        assert (raw["ok"], raw["reason_code"]) == (False, PRACTICE_NO_SHORTS_CODE), side
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
def test_validate_refuses_an_opening_short_on_every_practice_venue(monkeypatch, target: str) -> None:
    fake = SimpleNamespace(
        reference=SimpleNamespace(admission=lambda symbol: (True, "OK", None)),
        ledger=SimpleNamespace(held_qty=lambda symbol: 10.0),
    )
    monkeypatch.setattr(practice_broker, "for_venue", lambda label: fake)
    _on(target)
    assert validate_command(_cmd(qty=11)) == (False, MESSAGE, PRACTICE_NO_SHORTS_CODE)
    assert validate_command(_cmd(qty=1, short_entry=True)) == (False, MESSAGE, PRACTICE_NO_SHORTS_CODE)
    assert validate_command(_cmd(qty=10)) == (True, "OK", None)
    assert validate_command(_cmd(qty=3)) == (True, "OK", None)
    assert validate_command(_cmd(side="BUY", qty=500)) == (True, "OK", None)


def test_validate_refuses_a_short_bracket_and_a_protective_oversell(monkeypatch) -> None:
    fake = SimpleNamespace(
        reference=SimpleNamespace(admission=lambda symbol: (True, "OK", None)),
        ledger=SimpleNamespace(held_qty=lambda symbol: 10.0),
    )
    monkeypatch.setattr(practice_broker, "for_venue", lambda label: fake)
    _on("paper")
    bracket = _cmd(
        operation="bracket", side=None, qty=5, short_entry=True,
        entry_price=10.0, stop_price=11.0, target_price=9.0,
    )
    assert validate_command(bracket) == (False, MESSAGE, PRACTICE_NO_SHORTS_CODE)
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
