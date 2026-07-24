"""CI-safe end-to-end execution measurement regressions."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from execution import broker_send, evidence_store, service, store, telemetry, timing
from execution.latency import latency_summary
from execution.models import ExecutionCommand, StageTimings
from ibkr import client as client_mod
from ibkr import orders as orders_mod


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "cache_dir", lambda: tmp_path)
    telemetry.reset_for_tests()
    store.init_db()
    yield
    telemetry.reset_for_tests()


def _execution(
    key: str,
    *,
    order_id: int,
    side: str = "BUY",
    reference_price: float = 10.0,
) -> str:
    execution_id, _ = store.reserve(
        idempotency_key=key,
        operation="place",
        source="manual",
        symbol="AAPL",
        received_ns=1_000_000,
        payload={
            "side": side,
            "qty": 5,
            "requested_price": reference_price,
            "reference_price": reference_price,
        },
    )
    store.update_stages(
        execution_id,
        order_id=order_id,
        status="sent",
        broker_sent_ns=2_000_000,
    )
    return execution_id


def test_browser_and_backend_clock_domains_never_cross_subtract(monkeypatch):
    browser = {
        "action_wall_ms": 1_000.0,
        "action_performance_ms": 10.0,
        "request_wall_ms": 1_025.0,
        "request_performance_ms": 35.0,
    }
    measurement = timing.initial_measurement(
        browser_timing=browser,
        backend_ingress_perf_ns=500_000_000,
        backend_ingress_wall_ns=1_100_000_000,
    )
    assert measurement["browser"]["action_to_request_ms"] == 25.0
    wall = measurement["browser_to_backend_wall_observation"]
    assert wall["latency_usable"] is False
    assert measurement["cross_clock_arithmetic"] == "forbidden"

    ticks = iter((525_000_000, 1_150_000_000))
    monkeypatch.setattr(timing.time, "perf_counter_ns", lambda: next(ticks))
    monkeypatch.setattr(timing.time, "time_ns", lambda: next(ticks))
    ready = timing.response_ready_measurement(measurement)
    assert ready["backend"]["ingress_to_response_ready_ms"] == 25.0
    assert "not_socket_or_frontend_render" in ready["backend"]["response_mark"]


def test_partial_then_complete_fill_persists_bounded_evidence():
    execution_id = _execution("partial-complete", order_id=101)
    watch = telemetry.watch_order(101, execution_id, fresh=True)
    watch.note_execution(
        avg_price=10.10,
        price=10.10,
        shares=2,
        cumulative_shares=2,
        remaining=3,
        complete=False,
        callback_wall_ns=2_000_000_000,
        callback_perf_ns=3_000_000,
    )
    watch.note_execution(
        avg_price=10.16,
        price=10.20,
        shares=3,
        cumulative_shares=5,
        remaining=0,
        complete=True,
        callback_wall_ns=2_100_000_000,
        callback_perf_ns=4_000_000,
    )
    watch.note_filled()

    evidence = evidence_store.list_for_execution(execution_id)
    assert [item["fill_state"] for item in evidence] == ["partial", "complete"]
    assert evidence[0]["provenance"] == "execDetails"
    assert evidence[1]["average_fill_price"] == pytest.approx(10.16)
    assert store.get_by_id(execution_id)["status"] == "filled"


@pytest.mark.parametrize(
    ("side", "average", "expected"),
    (("BUY", 10.20, 0.20), ("SELL", 9.80, 0.20)),
)
def test_slippage_is_side_aware(side, average, expected):
    execution_id = _execution(
        f"slippage-{side}", order_id=110 if side == "BUY" else 111, side=side,
    )
    assert evidence_store.record_fill(
        execution_id=execution_id,
        order_id=110 if side == "BUY" else 111,
        provenance="execDetails",
        complete=True,
        average_fill_price=average,
        cumulative_shares=5,
    )
    item = evidence_store.list_for_execution(execution_id)[0]
    assert item["slippage_per_share"] == pytest.approx(expected)
    assert item["slippage_total"] == pytest.approx(expected * 5)
    assert item["slippage_bps"] == pytest.approx(200.0)


def test_exchange_callback_delay_is_labeled_and_negative_is_excluded():
    execution_id = _execution("exchange-delay", order_id=120)
    exchange = datetime(2026, 7, 24, tzinfo=timezone.utc)
    callback = int(exchange.timestamp() * 1e9) + 50_000_000
    evidence_store.record_fill(
        execution_id=execution_id,
        order_id=120,
        provenance="execDetails",
        complete=False,
        exchange_time=exchange,
        callback_wall_ns=callback,
    )
    evidence_store.record_fill(
        execution_id=execution_id,
        order_id=120,
        provenance="execDetails",
        complete=True,
        exchange_time=exchange,
        callback_wall_ns=callback - 100_000_000,
    )
    first, second = evidence_store.list_for_execution(execution_id)
    assert first["exchange_to_callback_ms"] == 50.0
    assert second["exchange_to_callback_ms"] is None
    assert (
        second["exchange_delay_excluded_reason"]
        == "negative_exchange_to_callback_wall_delta"
    )


def test_existing_reconciliation_poll_records_provenance_once():
    execution_id = _execution("reconcile", order_id=130)
    telemetry.watch_order(130, execution_id, fresh=True)
    fill = SimpleNamespace(
        execution=SimpleNamespace(
            orderId=130,
            time=datetime(2026, 7, 24, tzinfo=timezone.utc),
            price=10.0,
            shares=5,
            cumQty=5,
            avgPrice=10.0,
        )
    )
    assert telemetry.note_reconciliation_fill(fill) is True
    assert telemetry.note_reconciliation_fill(fill) is False
    evidence = evidence_store.list_for_execution(execution_id)
    assert len(evidence) == 1
    assert evidence[0]["provenance"] == "reconciliation_poll"


def test_fill_evidence_is_bounded_and_reports_drops():
    execution_id = _execution("bounded-evidence", order_id=135)
    for index in range(70):
        evidence_store.record_fill(
            execution_id=execution_id,
            order_id=135,
            provenance="execDetails",
            complete=index == 69,
            price=10.0,
            shares=1,
            cumulative_shares=index + 1,
        )
    assert len(evidence_store.list_for_execution(execution_id)) == 64
    assert store.get_by_id(execution_id)["payload"][
        "fill_evidence_dropped_count"
    ] == 6


def test_fresh_cancel_watch_cannot_reuse_original_order_ack():
    original_id = _execution("original", order_id=140)
    original = telemetry.watch_order(140, original_id, fresh=True)
    original.note_status("Submitted", callback_perf_ns=3_000_000)

    cancel_id, _ = store.reserve(
        idempotency_key="cancel",
        operation="cancel",
        source="manual",
        symbol=None,
        received_ns=4_000_000,
    )
    store.update_stages(
        cancel_id, order_id=140, status="sent", broker_sent_ns=5_000_000,
    )
    cancel = telemetry.watch_order(140, cancel_id, fresh=True)
    assert cancel.ack_ns is None
    cancel.note_status("Cancelled", callback_perf_ns=6_000_000)

    assert store.get_by_id(original_id)["broker_ack_ns"] == 3_000_000
    assert store.get_by_id(cancel_id)["broker_ack_ns"] == 6_000_000
    summary = latency_summary()
    excluded = summary["broker_ack_ms"]["excluded_reasons"]
    assert "negative_broker_ack_ns_minus_received_ns" not in excluded


def test_negative_legacy_ack_is_excluded_with_reason():
    execution_id = _execution("negative-legacy", order_id=150)
    store.update_stages(execution_id, broker_ack_ns=500_000)
    summary = latency_summary(idempotency_prefix="negative-legacy")
    broker_ack = summary["broker_ack_ms"]
    assert broker_ack["count"] == 0
    assert broker_ack["excluded_reasons"] == {
        "negative_broker_ack_ns_minus_received_ns": 1,
    }


def test_synthetic_and_paper_benchmarks_suppress_aggregate_sla():
    for key, ack_ms in (
        ("bench:synth:mixed:place", 10),
        ("bench:paper:mixed:place", 100),
    ):
        execution_id, _ = store.reserve(
            idempotency_key=key,
            operation="place",
            source="benchmark",
            symbol="AAPL",
            received_ns=1_000_000,
        )
        store.update_stages(
            execution_id,
            status="acked",
            mode="paper",
            broker_sent_ns=2_000_000,
            broker_ack_ns=1_000_000 + ack_ms * 1_000_000,
        )

    summary = latency_summary(idempotency_prefix="bench:")
    assert summary["normalized_populations"] == [
        "benchmark_paper", "benchmark_synthetic",
    ]
    assert summary["mixed_population"] is True
    assert summary["aggregate_scope"] == "mixed_diagnostic_only"
    assert summary["broker_ack_ms"]["count"] == 2
    assert summary["sla_pass"] is None
    assert summary["sla_status"] == "suppressed_mixed_population"
    assert summary["aggregate_warning"]
    assert "sla" not in summary["segments"]["mode"]["paper"]
    assert "sla" not in summary["segments"]["source"]["benchmark"]
    for population in ("benchmark_paper", "benchmark_synthetic"):
        segment = summary["segments"]["population"][population]
        assert segment["distributions"]["broker_ack_ms"]["count"] == 1
        assert segment["sla"]["pass"] is None
        assert segment["sla"]["status"] == "insufficient_samples"


def test_bracket_children_cannot_corrupt_parent_fill_or_slippage(monkeypatch):
    received = time.perf_counter_ns()
    execution_id, _ = store.reserve(
        idempotency_key="bracket-leg-attribution",
        operation="bracket",
        source="approve",
        symbol="AAPL",
        received_ns=received,
        payload={
            "side": None,
            "qty": 5,
            "requested_price": 10.0,
            "reference_price": 10.0,
        },
    )
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    monkeypatch.setattr(
        orders_mod,
        "place_bracket_order",
        lambda **_kwargs: {
            "ok": True,
            "parent_order_id": 201,
            "target_order_id": 202,
            "stop_order_id": 203,
            "error": None,
            "mode": "paper",
        },
    )
    cmd = ExecutionCommand(
        operation="bracket",
        idempotency_key="bracket-leg-attribution",
        source="approve",
        symbol="AAPL",
        shares=5,
        entry_price=10.0,
        target_price=12.0,
        stop_price=9.0,
    )
    timings = StageTimings(received_ns=received)
    receipt = asyncio.run(
        broker_send.send_broker(
            cmd,
            execution_id,
            timings,
            wait_ack=False,
            reject=lambda *_args: pytest.fail("unexpected reject"),
        )
    )
    assert receipt.ok is True
    assert timings.broker_sent_ns is not None
    sent = timings.broker_sent_ns

    target = telemetry.watch_order(202)
    stop = telemetry.watch_order(203)
    parent = telemetry.watch_order(201)
    target.note_execution(
        avg_price=12.1, price=12.1, shares=5, cumulative_shares=5,
        remaining=0, complete=True, callback_perf_ns=sent + 1_000_000,
    )
    target.note_filled()
    stop.note_execution(
        avg_price=8.9, price=8.9, shares=5, cumulative_shares=5,
        remaining=0, complete=True, callback_perf_ns=sent + 2_000_000,
    )
    stop.note_filled()
    assert store.get_by_id(execution_id)["filled_ns"] is None
    assert store.get_by_id(execution_id)["broker_ack_ns"] is None

    parent.note_status(
        "Filled", filled=5, remaining=0, average_fill_price=10.1,
        callback_perf_ns=sent + 3_000_000,
    )
    parent.note_filled()

    row = service.get_execution(execution_id)
    assert row is not None
    evidence = {item["leg_role"]: item for item in row["fill_evidence"]}
    assert evidence["parent"]["evidence_side"] == "BUY"
    assert evidence["parent"]["reference_price"] == 10.0
    assert evidence["parent"]["slippage_bps"] == pytest.approx(100.0)
    assert evidence["parent"]["aggregate_eligible"] is True
    assert evidence["target"]["evidence_side"] == "SELL"
    assert evidence["target"]["reference_price"] == 12.0
    assert evidence["target"]["slippage_bps"] == pytest.approx(-1000 / 12)
    assert evidence["target"]["aggregate_eligible"] is False
    assert evidence["stop"]["evidence_side"] == "SELL"
    assert evidence["stop"]["reference_price"] == 9.0
    assert evidence["stop"]["slippage_bps"] == pytest.approx(1000 / 9)
    assert evidence["stop"]["aggregate_eligible"] is False
    assert row["first_fill"]["leg_role"] == "parent"
    assert row["complete_fill"]["leg_role"] == "parent"

    summary = latency_summary(idempotency_prefix="bracket-leg-attribution")
    assert summary["fill_ms"]["send_to_fill"]["p50"] == 3.0
    assert summary["segments"]["fill_leg"]["target"][
        "aggregate_eligible_count"
    ] == 0
    assert summary["segments"]["fill_provenance"]["execDetails"][
        "callback_from_send_ms"
    ]["excluded_reasons"] == {"child_leg_not_parent_aggregate": 2}
