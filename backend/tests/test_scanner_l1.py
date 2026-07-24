"""Tests for active-tab + reserved HOD L1 planner."""
from __future__ import annotations

import asyncio

import ibkr.scanner_l1 as scanner_l1
from ibkr.scanner_l1 import plan_stream_symbols
from metrics import op_metrics


def test_plan_reserves_tab_then_hod_with_dedupe():
    plan = plan_stream_symbols(
        [f"G{i:02d}" for i in range(50)],
        [f"G{i:02d}" for i in range(10)] + [f"H{i:02d}" for i in range(40)],
        budget=90,
        tab_max=50,
    )
    assert len(plan["tab"]) == 50
    # Overlap G00-G09 already on tab — HOD slots fill with H** only for unique
    assert all(s.startswith("H") or s.startswith("G") for s in plan["hod"])
    assert len(plan["combined"]) <= 90
    assert "G00" in plan["tab"]


def test_plan_rejects_overflow_when_budget_tight():
    plan = plan_stream_symbols(
        [f"T{i:02d}" for i in range(40)],
        [f"H{i:02d}" for i in range(40)],
        budget=50,
        tab_max=40,
    )
    assert len(plan["tab"]) == 40
    assert len(plan["hod"]) == 10
    assert len(plan["rejected"]) >= 30


def test_empty_tab_gives_full_budget_to_hod():
    plan = plan_stream_symbols(
        [],
        [f"H{i:02d}" for i in range(40)],
        budget=95,
        tab_max=50,
    )
    assert plan["tab"] == []
    assert len(plan["hod"]) == 40
    assert plan["rejected"] == []


def test_flush_loop_drops_hod_only_ticks_for_a_frozen_table(monkeypatch):
    """ADR 008: a HOD-reserved-pool tick for a symbol retained from a frozen
    table (e.g. Gappers after 09:30) must never reach the WS as a table-
    tagged price_patch — that would silently mutate the "frozen" row on the
    frontend. Only symbols actually subscribed under OWNER_SCANNER (the
    active tab) are forwarded."""
    scanner_l1._pending.clear()
    scanner_l1._active_tab_symbols.clear()
    scanner_l1._active_tab_symbols.update({"GAINSYM"})
    scanner_l1._subscription_state["tab"] = "gainers"
    scanner_l1._pending["GAINSYM"] = {"symbol": "GAINSYM", "price": 1.0}
    # HOD-only tick for a symbol retained from a frozen Gappers table.
    scanner_l1._pending["FROZENSYM"] = {"symbol": "FROZENSYM", "price": 2.0}

    pushed: list[dict] = []

    async def fake_push(payload):
        pushed.append(payload)

    async def run_one_flush():
        task = asyncio.ensure_future(scanner_l1.flush_loop(fake_push))
        await asyncio.sleep(scanner_l1.IBKR_L1_BATCH_FLUSH_SEC + 0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run_one_flush())

    assert len(pushed) == 1
    symbols = {r["symbol"] for r in pushed[0]["rows"]}
    assert symbols == {"GAINSYM"}
    assert pushed[0]["table"] == "gainers"


def test_flush_measures_first_buffered_tick_through_broadcast(monkeypatch):
    scanner_l1._pending.clear()
    scanner_l1._pending_started_ns = None
    scanner_l1._active_tab_symbols.clear()
    scanner_l1._active_tab_symbols.add("AAPL")
    scanner_l1._subscription_state["tab"] = "gainers"
    monkeypatch.setattr(scanner_l1, "_apply_quote", None)
    monkeypatch.setattr(scanner_l1, "IBKR_L1_BATCH_FLUSH_SEC", 0.01)
    op_metrics.reset_for_tests()
    pushed: list[dict] = []

    async def push(payload):
        pushed.append(payload)

    async def run():
        scanner_l1.on_l1_quote("AAPL", 10.0, 100, 9.0, 1.0)
        task = asyncio.create_task(scanner_l1.flush_loop(push))
        await asyncio.sleep(0.03)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())

    assert len(pushed) == 1
    stats = op_metrics.snapshot()["operations"]["ws.scanner.price_patch_buffer_to_broadcast"]
    assert stats["count"] == 1
    assert stats["error_count"] == 0


def test_flush_broadcast_failure_is_recorded(monkeypatch):
    scanner_l1._pending.clear()
    scanner_l1._pending_started_ns = None
    scanner_l1._active_tab_symbols.clear()
    scanner_l1._active_tab_symbols.add("AAPL")
    scanner_l1._subscription_state["tab"] = "gainers"
    monkeypatch.setattr(scanner_l1, "_apply_quote", None)
    monkeypatch.setattr(scanner_l1, "IBKR_L1_BATCH_FLUSH_SEC", 0.01)
    op_metrics.reset_for_tests()

    async def fail_push(_payload):
        raise RuntimeError("broadcast failed")

    async def run():
        scanner_l1.on_l1_quote("AAPL", 10.0, 100, 9.0, 1.0)
        task = asyncio.create_task(scanner_l1.flush_loop(fail_push))
        await asyncio.sleep(0.03)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())

    stats = op_metrics.snapshot()["operations"]["ws.scanner.price_patch_buffer_to_broadcast"]
    assert stats["count"] == 1
    assert stats["error_count"] == 1
