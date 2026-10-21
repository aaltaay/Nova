"""The daily loss limit's No new buys at the execution door (ADR 056): yours and the bots' alike."""
from __future__ import annotations

import asyncio
import time

import execution.service as exec_svc
import execution.store as store
import execution.telemetry as telemetry
import ibkr.orders as orders_mod
from execution.models import ExecutionCommand


def _cmd(source: str, key: str, side: str = "BUY", **extra) -> ExecutionCommand:
    return ExecutionCommand(operation="place", idempotency_key=key, source=source,  # type: ignore[arg-type]
                            symbol="AAPL", side=side, qty=1, order_type="MKT", skip_risk=True, **extra)


def _trip(account: str, *, loss: float = 451.03, limit: int = 405) -> None:
    from loss_limit import state

    state.write(account, {"tripped_at": time.time(), "tripped_loss": loss, "limit_usd": limit})


def _paper_desk(monkeypatch) -> list[int]:
    store.init_db()
    telemetry.reset_for_tests()
    called: list[int] = []
    monkeypatch.setattr(orders_mod, "place_order", lambda **k: called.append(1) or {"ok": True})
    monkeypatch.setattr("ibkr.client.is_enabled", lambda: True)
    monkeypatch.setattr("ibkr.client.is_connected", lambda: True)
    monkeypatch.setattr("ibkr.client.account_mode", lambda: "paper")
    monkeypatch.setattr("ibkr.client.broker_account_kind", lambda: "paper")
    monkeypatch.setattr("ibkr.safety.orders_enabled", lambda: True)
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setattr("ibkr.account.get_account_summary",
                        lambda: {"connected": True, "BuyingPower": 100_000, "pending": False})
    monkeypatch.setattr("ibkr.account.get_positions", lambda: [])
    return called


def test_no_new_buys_refuses_your_buy_and_the_bots_but_never_a_flatten(monkeypatch):
    called = _paper_desk(monkeypatch)
    from sim.mode import venue

    _trip(venue())
    manual = asyncio.run(exec_svc.execute(_cmd("manual", "ll-manual"), wait_ack=False))
    assert manual.ok is False and manual.reason_code == "LOSS_LIMIT_NO_NEW_BUYS"
    assert "Daily loss limit reached" in manual.error and "$451.03" in manual.error and "$405" in manual.error
    assert "Settings > Loss limits" in manual.error
    bot = asyncio.run(exec_svc.execute(_cmd("bot", "ll-bot"), wait_ack=False))
    assert bot.ok is False and bot.reason_code == "LOSS_LIMIT_NO_NEW_BUYS"
    flatten = asyncio.run(exec_svc.execute(_cmd("flatten", "ll-flat"), wait_ack=False))
    assert flatten.reason_code != "LOSS_LIMIT_NO_NEW_BUYS"
    assert called == [1]


def test_unchecking_no_new_buys_opens_buys_again(monkeypatch):
    called = _paper_desk(monkeypatch)
    from loss_limit import settings, state
    from sim.mode import venue

    _trip(venue())
    settings.update({"no_new_buys": False})
    state.clear()
    again = asyncio.run(exec_svc.execute(_cmd("manual", "ll-open"), wait_ack=False))
    assert again.reason_code != "LOSS_LIMIT_NO_NEW_BUYS"
    assert called == [1]


def test_the_door_reads_its_own_venues_limit(monkeypatch):
    """Paper's trip holds Paper's buys only: Live has none of its own."""
    from execution.models import ExecutionReceipt
    from sim.mode import reset_for_tests as reset_venue, set_venue

    store.init_db()
    telemetry.reset_for_tests()
    reset_venue()
    monkeypatch.setattr("bot.venue_levels.venue_changed", lambda old, new: None)
    try:
        _trip("paper", loss=312.5, limit=300)
        sent: list[str] = []

        async def record(cmd, execution_id, timings, *, wait_ack=True, reject, venue=None):
            sent.append(venue)
            return ExecutionReceipt(ok=True, execution_id=execution_id, operation=cmd.operation, source=cmd.source,
                                    idempotency_key=cmd.idempotency_key, order_id=1, mode=venue, timings=timings)

        monkeypatch.setattr(exec_svc, "send_broker", record)
        monkeypatch.setattr("execution.validate.validate_command", lambda cmd, venue=None: (True, "OK", None))
        monkeypatch.setattr("execution.validate.check_account_and_position", lambda cmd, **_kw: (True, "OK", None))
        set_venue("live", persist=False)
        live = asyncio.run(exec_svc.execute(_cmd("manual", "live-buy"), wait_ack=False))
        assert live.ok is True and sent == ["live"]

        set_venue("paper", persist=False)
        paper = asyncio.run(exec_svc.execute(_cmd("manual", "paper-buy"), wait_ack=False))
        assert paper.ok is False and paper.reason_code == "LOSS_LIMIT_NO_NEW_BUYS"
        assert "on Paper" in paper.error and "$312.50" in paper.error and "$300" in paper.error
        sell = asyncio.run(exec_svc.execute(_cmd("manual", "paper-sell", side="SELL"), wait_ack=False))
        assert sell.reason_code != "LOSS_LIMIT_NO_NEW_BUYS"           # selling what is held always works
        short = asyncio.run(exec_svc.execute(_cmd("manual", "paper-short", side="SELL", short_entry=True),
                                             wait_ack=False))
        assert short.ok is False and short.reason_code == "LOSS_LIMIT_NO_NEW_BUYS"   # a new short is a new position
    finally:
        reset_venue()


def test_the_bots_line_refuses_a_bot_buy_and_lets_yours_through(monkeypatch):
    """ADR 061: the side comes from the order's own source; the Bots line holds only source ``bot``."""
    called = _paper_desk(monkeypatch)
    from loss_limit import settings, state
    from sim.mode import venue

    settings.update({"bots_usd": 500})
    state.write(venue(), {"tripped_at": time.time(), "tripped_loss": 510.0, "limit_usd": 500}, line="bots")
    bot = asyncio.run(exec_svc.execute(_cmd("bot", "ll-bots-line-bot"), wait_ack=False))
    assert bot.ok is False and bot.reason_code == "LOSS_LIMIT_NO_NEW_BUYS"
    assert "The bots' daily loss limit reached" in bot.error and "$510" in bot.error
    manual = asyncio.run(exec_svc.execute(_cmd("manual", "ll-bots-line-manual"), wait_ack=False))
    assert manual.reason_code != "LOSS_LIMIT_NO_NEW_BUYS"
    assert called == [1]
