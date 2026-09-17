"""Append-only audit schema."""
from __future__ import annotations

from bot.audit import list_entries, record
from bot.autonomy import apply_desk_level
from bot.session import require_l2_brain


def test_audit_fields_and_append():
    apply_desk_level(2)
    require_l2_brain("brain-9", claim=True)
    first = record(
        action="buy_market",
        outcome="ok",
        reason="test",
        order_id=11,
        advise_spend=0.0,
        inputs={"symbol": "ABCD", "qty": 1},
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
    assert first["strategy"] == "small-cap"
    assert first["brain_session_id"] == "brain-9"
    assert first["order_id"] == 11
    assert rows[-1]["action"] == second["action"]
