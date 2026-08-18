"""Shaped execution-ledger rows for the Activity trail."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import execution.store as store
from execution.activity import recent_activity, shape_activity_row


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "cache_dir", lambda: tmp_path)
    store.init_db()
    yield


def _place(symbol: str, *, key: str, side: str = "BUY", requested=10, sent=1) -> str:
    execution_id, _ = store.reserve(
        idempotency_key=key,
        operation="place",
        source="manual",
        symbol=symbol,
        received_ns=1_000_000,
        payload={
            "side": side,
            "requested_qty": requested,
            "sent_qty": sent,
            "forced_one_share": True,
            "orders_enabled": True,
            "live_trading_confirmed": False,
            "short_enabled": False,
            "gateway_mode": "paper",
        },
    )
    store.update_stages(
        execution_id,
        status="filled",
        order_id=19112,
        broker_status="Filled",
        validation_completed_ns=1_500_000,
        persisted_ns=2_000_000,
        broker_sent_ns=3_000_000,
        broker_ack_ns=4_000_000,
        filled_ns=5_000_000,
    )
    return execution_id


def test_shape_activity_row_exposes_qty_gates_and_timings():
    execution_id = _place("IVF", key="act-1")
    row = store.get_by_id(execution_id)
    assert row is not None
    shaped = shape_activity_row(row)
    assert shaped["id"] == execution_id
    assert shaped["symbol"] == "IVF"
    assert shaped["side"] == "BUY"
    assert shaped["requested_qty"] == 10
    assert shaped["sent_qty"] == 1
    assert shaped["forced_one_share"] is True
    assert shaped["order_id"] == 19112
    assert shaped["timings"]["validation_ms"] == pytest.approx(0.5)
    assert shaped["timings"]["filled_ms"] == pytest.approx(4.0)
    assert shaped["gateway_mode"] == "paper"


def test_recent_activity_filters_symbol_and_respects_limit():
    _place("IVF", key="act-ivf")
    _place("AAPL", key="act-aapl")
    rows = recent_activity(limit=50, symbol="ivf")
    assert [r["symbol"] for r in rows] == ["IVF"]
    assert recent_activity(limit=1, symbol=None)
    assert len(recent_activity(limit=1)) == 1
