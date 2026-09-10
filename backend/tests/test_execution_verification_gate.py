"""IBKR Client Portal verification rejects latch entries but never exits."""
from __future__ import annotations

import asyncio

from execution import broker_send
from execution.models import ExecutionCommand
from execution import verification_gate
from execution.telemetry import OrderWatch
from execution.models import StageTimings


def _command(
    *,
    side: str = "BUY",
    source: str = "manual",
    short_entry: bool = False,
) -> ExecutionCommand:
    return ExecutionCommand(
        operation="place",
        idempotency_key=f"{side}-{source}-{short_entry}",
        source=source,  # type: ignore[arg-type]
        symbol="AAPL",
        side=side,
        qty=1,
        order_type="MKT",
        short_entry=short_entry,
    )


def setup_function() -> None:
    verification_gate.reset_for_tests()


def teardown_function() -> None:
    verification_gate.reset_for_tests()


def test_error_201_token_message_latches_symbol() -> None:
    message = (
        "Order rejected - reason:BEFORE WE CAN ACCEPT YOUR ORDER IN THIS "
        "SECURITY, PLEASE LOGIN TO CLIENT PORTAL AND VERIFY USING THE TOKEN "
        "WE <br>EMAILED TO YOU."
    )

    detail = verification_gate.classify_reject(201, message, "aapl")

    assert detail.reason_code == "IBKR_VERIFICATION_REQUIRED"
    assert detail.message == (
        "Order was not placed. IBKR requires Client Portal verification "
        "before accepting a new AAPL order."
    )
    assert verification_gate.blocked_symbols() == ("AAPL",)


def test_latched_symbol_blocks_entry_until_operator_acknowledges() -> None:
    verification_gate.latch("AAPL")

    blocked = verification_gate.entry_block(_command())
    acknowledged = verification_gate.acknowledge("AAPL")

    assert blocked is not None
    assert blocked.reason_code == "IBKR_VERIFICATION_REQUIRED"
    assert acknowledged is True
    assert verification_gate.entry_block(_command()) is None
    assert verification_gate.blocked_symbols() == ()


def test_latch_never_blocks_long_exit_cancel_replace_or_flatten(monkeypatch) -> None:
    verification_gate.latch("AAPL")
    monkeypatch.setattr(verification_gate._account, "short_qty", lambda _symbol: 0.0)

    long_exit = _command(side="SELL")
    cancel = ExecutionCommand(
        operation="cancel",
        idempotency_key="cancel",
        source="manual",
        order_id=1,
        symbol="AAPL",
    )
    replace = ExecutionCommand(
        operation="replace",
        idempotency_key="replace",
        source="manual",
        order_id=1,
        symbol="AAPL",
        limit_price=100,
    )
    flatten = _command(source="flatten")

    assert verification_gate.entry_block(long_exit) is None
    assert verification_gate.entry_block(cancel) is None
    assert verification_gate.entry_block(replace) is None
    assert verification_gate.entry_block(flatten) is None


def test_latch_allows_short_cover_but_blocks_new_short(monkeypatch) -> None:
    verification_gate.latch("AAPL")
    monkeypatch.setattr(verification_gate._account, "short_qty", lambda _symbol: 2.0)

    assert verification_gate.entry_block(_command(side="BUY")) is None
    assert verification_gate.entry_block(
        _command(side="SELL", short_entry=True)
    ) is not None


def test_finish_place_returns_typed_verification_reject(monkeypatch) -> None:
    monkeypatch.setattr(broker_send.store, "update_stages", lambda *_a, **_k: None)
    import execution.place_reject_guard as guard

    monkeypatch.setattr(guard, "EXECUTION_CANCEL_ACK_GRACE_SEC", 0.0)
    monkeypatch.setattr(guard, "order_still_open", lambda _oid: False)
    watch = OrderWatch(96902)
    watch.note_error(
        201,
        "BEFORE WE CAN ACCEPT YOUR ORDER IN THIS SECURITY, PLEASE LOGIN TO "
        "CLIENT PORTAL AND VERIFY USING THE TOKEN WE EMAILED TO YOU.",
    )
    watch.note_status("Inactive")

    receipt = asyncio.run(
        broker_send.finish_place(
            "exec-verification",
            _command(),
            StageTimings(received_ns=1),
            {"ok": True, "order_id": 96902},
            watch,
            "live",
            wait_ack=True,
        )
    )

    assert receipt.ok is False
    assert receipt.reason_code == "IBKR_VERIFICATION_REQUIRED"
    assert receipt.error is not None and "<br>" not in receipt.error
    assert verification_gate.blocked_symbols() == ("AAPL",)
