"""Append-only audit schema."""
from __future__ import annotations

from bot.audit import list_entries, record
from tests.bot_helpers import set_level


def test_audit_fields_and_append():
    set_level(2)
    first = record(
        action="buy_market",
        outcome="ok",
        reason="test",
        order_id=11,
        advise_spend=0.0,
        inputs={"symbol": "ABCD", "qty": 1},
        brain_session_id="brain-9",
    )
    second = record(action="advise", outcome="book", advise_spend=0.0, inputs={"symbol": "AAPL"})
    rows = list_entries(limit=10)
    assert len(rows) >= 2
    keys = {
        "timestamp",
        "level",
        "strategy",
        "brain_session_id",
        "action",
        "inputs",
        "reason",
        "order_id",
        "advise_spend",
        "outcome",
    }
    assert keys <= set(first)
    assert first["level"] == 2
    assert first["strategy"] is None and first["venue"] == "live"     # ADR 042: no session strategy
    assert first["brain_session_id"] == "brain-9"
    assert first["order_id"] == 11
    assert rows[-1]["action"] == second["action"]
