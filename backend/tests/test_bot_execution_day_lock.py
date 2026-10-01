"""-$200 day lock refuses bot and manual BUY through the order SSOT."""
from __future__ import annotations

import asyncio

import execution.store as store
import execution.telemetry as telemetry
import execution.service as exec_svc
import ibkr.orders as orders_mod
from bot.persist import load_session, save_session
from execution.models import ExecutionCommand


def _buy(source: str, key: str) -> ExecutionCommand:
    return ExecutionCommand(
        operation="place",
        idempotency_key=key,
        source=source,  # type: ignore[arg-type]
        symbol="AAPL",
        side="BUY",
        qty=1,
        order_type="MKT",
        skip_risk=True,
    )


def test_day_lock_blocks_manual_and_bot_buy(monkeypatch):
    store.init_db()
    telemetry.reset_for_tests()
    row = load_session()
    row["hard_lock_until_date"] = "2099-01-01"
    save_session(row)
    called = []
    monkeypatch.setattr(orders_mod, "place_order", lambda **k: called.append(1) or {"ok": True})
    monkeypatch.setattr("ibkr.client.is_enabled", lambda: True)
    monkeypatch.setattr("ibkr.client.is_connected", lambda: True)
    monkeypatch.setattr("ibkr.client.account_mode", lambda: "paper")
    monkeypatch.setattr("ibkr.client.broker_account_kind", lambda: "paper")
    monkeypatch.setattr("ibkr.safety.orders_enabled", lambda: True)
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setattr(
        "ibkr.account.get_account_summary",
        lambda: {"connected": True, "BuyingPower": 100_000, "pending": False},
    )
    monkeypatch.setattr("ibkr.account.get_positions", lambda: [])

    manual = asyncio.run(exec_svc.execute(_buy("manual", "lock-manual"), wait_ack=False))
    assert manual.ok is False
    assert manual.reason_code == "BOT_DAY_LOCK"
    bot = asyncio.run(exec_svc.execute(_buy("bot", "lock-bot"), wait_ack=False))
    assert bot.ok is False
    assert bot.reason_code == "BOT_DAY_LOCK"
    flatten = asyncio.run(
        exec_svc.execute(
            ExecutionCommand(
                operation="place",
                idempotency_key="lock-flat",
                source="flatten",
                symbol="AAPL",
                side="BUY",
                qty=1,
                order_type="MKT",
                skip_risk=True,
            ),
            wait_ack=False,
        )
    )
    assert flatten.reason_code != "BOT_DAY_LOCK"
    assert called == [1]


def test_the_door_reads_its_own_venues_lock_and_says_whose(monkeypatch):
    """Spec D: Paper's all-stop locks Paper's buys only, in its own words -- never "-$200"."""
    from execution.models import ExecutionReceipt
    from sim.mode import reset_for_tests as reset_venue, set_venue

    store.init_db()
    telemetry.reset_for_tests()
    reset_venue()
    # The dials stay where they are written: which dial a venue change swaps in is bot.venue_levels'.
    monkeypatch.setattr("bot.venue_levels.venue_changed", lambda old, new: None)
    try:
        set_venue("live", persist=False)
        row = load_session()
        row["level_venue"] = "live"
        row["hard_lock_until_date"] = None
        row["venue_levels"] = {"paper": {"hard_lock_until_date": "2099-01-01T04:00:00-05:00",
                                         "hard_lock_at": 1_790_000_000.0, "hard_lock_pnl": -312.5,
                                         "hard_lock_usd": -300.0}}
        save_session(row)
        sent: list[str] = []

        async def record(cmd, execution_id, timings, *, wait_ack=True, reject, venue=None):
            sent.append(venue)
            return ExecutionReceipt(ok=True, execution_id=execution_id, operation=cmd.operation, source=cmd.source,
                                    idempotency_key=cmd.idempotency_key, order_id=1, mode=venue, timings=timings)

        monkeypatch.setattr(exec_svc, "send_broker", record)
        monkeypatch.setattr("execution.validate.validate_command", lambda cmd, venue=None: (True, "OK", None))
        monkeypatch.setattr("execution.validate.check_account_and_position", lambda cmd: (True, "OK", None))
        live = asyncio.run(exec_svc.execute(_buy("manual", "live-buy"), wait_ack=False))
        assert live.ok is True and sent == ["live"]                       # Live has no lock of its own

        set_venue("paper", persist=False)
        paper = asyncio.run(exec_svc.execute(_buy("manual", "paper-buy"), wait_ack=False))
        assert paper.ok is False and paper.reason_code == "BOT_DAY_LOCK"
        assert "Paper's all-stop" in paper.error and "-$312.50" in paper.error and "-$300" in paper.error
        assert "-$200" not in paper.error and sent == ["live"]
    finally:
        reset_venue()
