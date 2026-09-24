"""tools/order_timing.py -- where each order's time went (operator ask, 2026-09-24).

"I also want full transparency with the live orders ... so we measure things."
The readout reads the backend's own stage stamps and never mixes clocks.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import order_timing  # noqa: E402

MS = 1_000_000
RECEIVED = 40_000_000 * MS


def _row(**over) -> dict:
    row = {
        "id": "exec-1", "operation": "place", "source": "manual", "symbol": "FOFO",
        "mode": "live", "order_id": 7, "status": "filled", "broker_status": "PreSubmitted",
        "error": None, "created_ts": 1_790_280_733.5,
        "received_ns": RECEIVED,
        "persisted_ns": RECEIVED + 5 * MS,
        "validation_completed_ns": RECEIVED + 11 * MS,
        "broker_sent_ns": RECEIVED + 17 * MS,
        "broker_ack_ns": RECEIVED + 173 * MS,
        "filled_ns": RECEIVED + 410 * MS,
        "payload": {
            "side": "BUY", "sent_qty": 1.0, "order_type": "LMT", "requested_price": 3.1,
            "measurement": {
                "backend": {"response_ready_perf_ns": RECEIVED + 190 * MS},
                "browser": {"valid": True, "action_to_request_ms": 0.3},
            },
        },
        "complete_fill": {
            "average_fill_price": 3.09, "exchange_ts_utc": "2026-09-24T20:12:14.500Z",
            "exchange_to_callback_ms": 42.0,
        },
    }
    row.update(over)
    return row


def test_a_live_order_reads_as_stages_in_time_order_with_the_ibkr_round_trip() -> None:
    tl = order_timing.timeline(_row())

    assert [s["stage"] for s in tl["steps"]] == [
        "recorded in the ledger", "checks passed", "sent to the venue",
        "venue answered", "reply ready (the ticket unlocks on it)", "filled",
    ]
    assert [s["at_ms"] for s in tl["steps"]] == [5.0, 11.0, 17.0, 173.0, 190.0, 410.0]
    assert tl["slowest"] == "filled"  # 220 ms after the reply: the order worked, then filled
    assert tl["venue_leg_ms"] == 156.0
    assert tl["venue_is_local"] is False
    text = order_timing.render(tl)
    assert "venue answered: PreSubmitted" in text
    assert "156.0 ms -- IBKR round trip through IB Gateway" in text
    assert "IBKR execution time: 2026-09-24T20:12:14.500Z" in text
    assert "click -> request left the window: 0.3 ms (browser clock)" in text


def test_a_paper_order_that_waited_out_the_ack_names_the_wait() -> None:
    """The 2026-09-24 shape: filled at 50 ms, replied at 5.1 s, no answer recorded."""
    tl = order_timing.timeline(_row(
        mode="paper", broker_status="Filled", broker_ack_ns=None,
        filled_ns=RECEIVED + 50 * MS,
        payload={"side": "SELL", "sent_qty": 100.0, "order_type": "LMT", "requested_price": 3.02,
                 "measurement": {"backend": {"ingress_to_response_ready_ms": 5108.8}}},
        complete_fill=None, first_fill=None,
    ))

    assert tl["slowest"] == "reply ready (the ticket unlocks on it)"
    assert tl["steps"][-1]["step_ms"] == 5058.8
    assert tl["missing"] == ["venue answered"]
    text = order_timing.render(tl)
    assert "<- slowest step" in text.splitlines()[-2]
    assert "not recorded: venue answered" in text
    assert "venue leg" not in text


def test_a_refused_order_keeps_its_reason_and_no_invented_stages() -> None:
    tl = order_timing.timeline(_row(
        mode="paper", status="rejected", broker_status=None, error="Not enough buying power",
        broker_sent_ns=None, broker_ack_ns=None, filled_ns=None, order_id=None,
    ))

    assert [s["stage"] for s in tl["steps"]] == [
        "recorded in the ledger", "checks passed", "reply ready (the ticket unlocks on it)",
    ]
    text = order_timing.render(tl)
    assert "error: Not enough buying power" in text
    assert "order -" in text.splitlines()[0]
