"""Phase K — end-to-end short_entry validate path (no broker send)."""
from __future__ import annotations

import time

import ibkr.account as account_mod
import ibkr.client as client_mod
import ibkr.safety as safety_mod
import ibkr.shortability as short_mod
import execution.validate as validate
from execution.models import ExecutionCommand


def _cmd(*, short_entry: bool = True) -> ExecutionCommand:
    return ExecutionCommand(
        operation="place",
        idempotency_key="e2e-short-1",
        source="manual",
        symbol="SMPL",
        side="SELL",
        qty=1,
        order_type="MKT",
        short_entry=short_entry,
    )


def test_e2e_short_entry_gate_matrix(monkeypatch):
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(
        account_mod,
        "get_account_summary",
        lambda: {"connected": True, "BuyingPower": 100_000.0},
    )
    monkeypatch.setattr(account_mod, "long_qty", lambda _s: 0.0)

    # 1) Env off → SHORT_DISABLED
    monkeypatch.setattr(safety_mod, "short_enabled", lambda: False)
    ok, _, reason = validate.check_account_and_position(_cmd())
    assert ok is False and reason == "SHORT_DISABLED"

    # 2) Env on + shortable → OK
    monkeypatch.setattr(safety_mod, "short_enabled", lambda: True)
    monkeypatch.setattr(
        short_mod,
        "fetch_shortability",
        lambda _s: short_mod.enrich_ibkr_listing(
            {
                "connected": True,
                "qualified": True,
                "shortable_shares": 250_000,
                "error": None,
            },
            fetched_at=time.time(),
        ),
    )
    ok, _, reason = validate.check_account_and_position(_cmd())
    assert ok is True and reason is None

    # 3) HTB → SHORT_NOT_SHORTABLE
    monkeypatch.setattr(
        short_mod,
        "fetch_shortability",
        lambda _s: short_mod.enrich_ibkr_listing(
            {
                "connected": True,
                "qualified": True,
                "shortable_shares": 0,
                "error": None,
            },
            fetched_at=time.time(),
        ),
    )
    ok, _, reason = validate.check_account_and_position(_cmd())
    assert ok is False and reason == "SHORT_NOT_SHORTABLE"

    # 4) No short_entry flag still anti-short
    ok, _, reason = validate.check_account_and_position(_cmd(short_entry=False))
    assert ok is False and reason == "NO_POSITION"
