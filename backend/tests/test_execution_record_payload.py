"""Ledger reserve payload must snapshot qty, gates, and short_entry."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from execution.models import ExecutionCommand
from execution.record_payload import build_reserve_payload


def test_reserve_payload_keeps_requested_and_sent_qty(monkeypatch):
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setenv("IBKR_ORDERS_ENABLED", "true")
    monkeypatch.setenv("IBKR_LIVE_TRADING_CONFIRMED", "false")
    monkeypatch.setenv("IBKR_SHORT_ENABLED", "false")
    cmd = ExecutionCommand(
        operation="place",
        idempotency_key="p1",
        source="manual",
        symbol="IVF",
        side="BUY",
        qty=1,
        order_type="MKT",
        short_entry=False,
    )
    payload = build_reserve_payload(
        cmd,
        requested_qty=1000.0,
        sent_qty=1.0,
        requested_price=None,
        measurement={"backend_ingress_wall_ns": 1},
        forced_one_share=True,
    )
    assert payload["requested_qty"] == 1000.0
    assert payload["sent_qty"] == 1.0
    assert payload["qty"] == 1.0
    assert payload["forced_one_share"] is True
    assert payload["short_entry"] is False
    assert payload["orders_enabled"] is True
    assert payload["live_trading_confirmed"] is False
    assert payload["short_enabled"] is False
    assert payload["gateway_mode"] == "paper"
    assert payload["side"] == "BUY"


def test_reserve_payload_records_short_entry(monkeypatch):
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setenv("IBKR_ORDERS_ENABLED", "true")
    monkeypatch.setenv("IBKR_SHORT_ENABLED", "true")
    cmd = ExecutionCommand(
        operation="place",
        idempotency_key="s1",
        source="manual",
        symbol="NOMA",
        side="SELL",
        qty=1,
        order_type="MKT",
        short_entry=True,
    )
    payload = build_reserve_payload(
        cmd,
        requested_qty=1.0,
        sent_qty=1.0,
        requested_price=2.5,
        measurement={},
        forced_one_share=True,
    )
    assert payload["short_entry"] is True
    assert payload["short_enabled"] is True
    assert payload["requested_price"] == 2.5
