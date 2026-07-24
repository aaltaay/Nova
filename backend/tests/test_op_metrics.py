"""Focused tests for process-local operation metrics."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from constants_metrics import OP_METRICS_RING_SIZE
from metrics import op_metrics
from routes.metrics import router


@pytest.fixture(autouse=True)
def reset_metrics():
    op_metrics.reset_for_tests()
    yield
    op_metrics.reset_for_tests()


def test_percentiles_use_nearest_rank_milliseconds():
    for value_ms in range(1, 101):
        op_metrics.record("unit.percentiles", value_ms * 1_000_000)

    stats = op_metrics.snapshot()["operations"]["unit.percentiles"]
    assert stats["p50_ms"] == 50
    assert stats["p95_ms"] == 95
    assert stats["p99_ms"] == 99
    assert stats["max_ms"] == 100


def test_ring_is_bounded_but_counts_are_process_lifetime():
    for index in range(OP_METRICS_RING_SIZE + 5):
        op_metrics.record("unit.ring", index + 1)

    stats = op_metrics.snapshot()["operations"]["unit.ring"]
    assert stats["count"] == OP_METRICS_RING_SIZE + 5
    assert stats["sample_count"] == OP_METRICS_RING_SIZE
    assert stats["max_ms"] == (OP_METRICS_RING_SIZE + 5) / 1_000_000


def test_errors_and_last_sample_age(monkeypatch):
    ticks = iter((1_000_000_000, 1_250_000_000))
    monkeypatch.setattr(op_metrics.time, "perf_counter_ns", lambda: next(ticks))

    op_metrics.record("unit.error", 2_000_000, ok=False)
    stats = op_metrics.snapshot()["operations"]["unit.error"]

    assert stats["count"] == 1
    assert stats["error_count"] == 1
    assert stats["last_sample_age_ms"] == 250


def test_timed_records_async_concurrency_and_exception():
    async def run() -> None:
        async def one() -> None:
            async with op_metrics.timed("unit.concurrent"):
                await asyncio.sleep(0)

        await asyncio.gather(*(one() for _ in range(20)))
        with pytest.raises(RuntimeError):
            async with op_metrics.timed("unit.failure"):
                raise RuntimeError("expected")

    asyncio.run(run())
    operations = op_metrics.snapshot()["operations"]
    assert operations["unit.concurrent"]["count"] == 20
    assert operations["unit.concurrent"]["error_count"] == 0
    assert operations["unit.failure"]["error_count"] == 1


def test_timed_sync_and_record_since_account_for_errors(monkeypatch):
    ticks = iter((1_000, 2_000, 3_000, 5_000, 6_000, 7_000))
    monkeypatch.setattr(op_metrics.time, "perf_counter_ns", lambda: next(ticks))

    with pytest.raises(RuntimeError):
        with op_metrics.timed_sync("unit.sync"):
            raise RuntimeError("expected")
    op_metrics.record_since("unit.elapsed", 1_000)

    operations = op_metrics.snapshot()["operations"]
    assert operations["unit.sync"]["error_count"] == 1
    assert operations["unit.elapsed"]["count"] == 1


def test_metrics_route_returns_snapshot():
    app = FastAPI()
    app.include_router(router)
    op_metrics.record("unit.route", 1_500_000)

    response = TestClient(app).get("/api/metrics/ops")

    assert response.status_code == 200
    assert response.json()["operations"]["unit.route"]["p50_ms"] == 1.5
    assert response.json()["execution"]["clock_contract"][
        "cross_clock_arithmetic"
    ] == "forbidden"
