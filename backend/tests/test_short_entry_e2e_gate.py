"""Phase K — end-to-end short_entry validate path (no broker send)."""
from __future__ import annotations

import time

import ibkr.account as account_mod
import ibkr.client as client_mod
import ibkr.safety as safety_mod
import ibkr.shortability as short_mod
import execution.validate as validate
from execution.models import ExecutionCommand


def _cmd(*, short_entry: bool = True, operation: str = "bracket") -> ExecutionCommand:
    """ADR 048: a short entry is a limit order, sent as a bracket with its buy stop."""
    legs = {"entry_price": 4.0, "stop_price": 4.2, "target_price": 3.6} if operation == "bracket" else {}
    return ExecutionCommand(
        operation=operation,
        idempotency_key="e2e-short-1",
        source="manual",
        symbol="SMPL",
        side="SELL",
        qty=1,
        order_type="LMT",
        limit_price=4.0,
        short_entry=short_entry,
        **legs,
    )


def _listing(shares: float) -> dict:
    return short_mod.enrich_ibkr_listing(
        {"connected": True, "qualified": True, "shortable_shares": shares, "error": None},
        fetched_at=time.time(),
    )


def test_e2e_short_entry_gate_matrix(monkeypatch, short_market_open):
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(
        account_mod,
        "get_account_summary",
        lambda: {"connected": True, "BuyingPower": 100_000.0, "NetLiquidation": 25_000.0,
                 "ExcessLiquidity": 25_000.0, "account_class": "margin"},
    )
    monkeypatch.setattr(account_mod, "get_positions", lambda: [])

    # 1) Env off → SHORT_DISABLED
    monkeypatch.setattr(safety_mod, "short_enabled", lambda: False)
    ok, _, reason = validate.check_account_and_position(_cmd(), borrow=_listing(250_000))
    assert ok is False and reason == "SHORT_DISABLED"

    # 2) Env on + shortable (read from the cache, ADR 048) → OK
    monkeypatch.setattr(safety_mod, "short_enabled", lambda: True)
    ok, _, reason = validate.check_account_and_position(_cmd(), borrow=_listing(250_000))
    assert ok is True and reason is None

    # 3) HTB → SHORT_NOT_SHORTABLE
    ok, _, reason = validate.check_account_and_position(_cmd(), borrow=_listing(0))
    assert ok is False and reason == "SHORT_NOT_SHORTABLE"

    # 4) A short with no buy stop (a plain limit) -> SHORT_NEEDS_STOP
    ok, _, reason = validate.check_account_and_position(_cmd(operation="place"), borrow=_listing(250_000))
    assert ok is False and reason == "SHORT_NEEDS_STOP"

    # 5) No short_entry flag still anti-short
    ok, _, reason = validate.check_account_and_position(_cmd(short_entry=False, operation="place"))
    assert ok is False and reason == "NO_POSITION"
