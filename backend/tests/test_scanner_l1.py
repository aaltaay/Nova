"""Tests for active-tab + reserved HOD L1 planner."""
from __future__ import annotations

import asyncio

import ibkr.scanner_l1 as scanner_l1
from ibkr import ticks as _ticks
from ibkr.scanner_l1 import plan_stream_symbols
from metrics import op_metrics


def _stub_owner_symbols(monkeypatch) -> dict[str, list[str]]:
    """Record set_owner_symbols calls without touching IBKR."""
    calls: dict[str, list[str]] = {}

    async def fake_set_owner_symbols(owner, symbols):
        calls[owner] = list(symbols)
        return {"owner": owner, "active": list(symbols), "failed": []}

    monkeypatch.setattr(_ticks, "set_owner_symbols", fake_set_owner_symbols)
    monkeypatch.setattr(_ticks, "subscribed_symbols", lambda: [])
    return calls


def _reset_reconcile_state() -> None:
    scanner_l1._active_tab_tables.clear()
    scanner_l1._prev_tab_symbols = []
    scanner_l1._tab_grace_until = 0.0


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


def test_frozen_requested_table_does_not_zero_the_other_live_table(monkeypatch):
    """Regression: the desk shows Gappers (frozen after 09:30) in the main tab
    and Gainers (live) in the scanner dock. A single dominant hint of "gappers"
    made symbols_for_tab return [] (ADR 008), which emptied the active-tab set
    and silently stopped *every* price_patch — the whole scanner column froze.
    Requesting both tables must still stream the live one."""
    _stub_owner_symbols(monkeypatch)
    _reset_reconcile_state()

    def tab_symbols(table):
        # ADR 008: frozen Gappers legitimately yields nothing.
        return [] if table == "gappers" else ["PFSA", "IPST"]

    asyncio.run(scanner_l1._reconcile_once(
        lambda: "ibkr",
        lambda: ["gappers", "gainers"],
        tab_symbols,
        lambda: [],
    ))

    assert scanner_l1._active_tab_tables == {"PFSA": "gainers", "IPST": "gainers"}
    state = scanner_l1.get_subscription_state()
    assert state["active_tab"] == 2
    assert state["tables"] == ["gappers", "gainers"]


def test_no_requested_table_streams_nothing(monkeypatch):
    """A desk showing only alert modes (HOD Momo) needs no active-tab L1."""
    _stub_owner_symbols(monkeypatch)
    _reset_reconcile_state()

    asyncio.run(scanner_l1._reconcile_once(
        lambda: "ibkr",
        lambda: [],
        lambda _t: ["NOPE"],
        lambda: [],
    ))

    assert scanner_l1._active_tab_tables == {}
    assert scanner_l1.get_subscription_state()["active_tab"] == 0


def test_flush_emits_one_patch_per_displayed_table(monkeypatch):
    """Two tables on screen at once must not cross-tag rows — a Gainers tick
    tagged "gappers" would mutate a frozen Gappers row on the frontend."""
    scanner_l1._pending.clear()
    scanner_l1._pending_started_ns = None
    scanner_l1._active_tab_tables.clear()
    scanner_l1._active_tab_tables.update({"GAINSYM": "gainers", "LOSESYM": "losers"})
    scanner_l1._pending["GAINSYM"] = {"symbol": "GAINSYM", "price": 1.0}
    scanner_l1._pending["LOSESYM"] = {"symbol": "LOSESYM", "price": 2.0}
    scanner_l1._pending["ORPHAN"] = {"symbol": "ORPHAN", "price": 3.0}
    monkeypatch.setattr(scanner_l1, "IBKR_L1_BATCH_FLUSH_SEC", 0.01)

    pushed: list[dict] = []

    async def push(payload):
        pushed.append(payload)

    async def run():
        task = asyncio.create_task(scanner_l1.flush_loop(push))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())

    by_table = {p["table"]: p for p in pushed}
    assert set(by_table) == {"gainers", "losers"}
    assert [r["symbol"] for r in by_table["gainers"]["rows"]] == ["GAINSYM"]
    assert [r["symbol"] for r in by_table["losers"]["rows"]] == ["LOSESYM"]


def test_flush_loop_drops_hod_only_ticks_for_a_frozen_table(monkeypatch):
    """ADR 008: a HOD-reserved-pool tick for a symbol retained from a frozen
    table (e.g. Gappers after 09:30) must never reach the WS as a table-
    tagged price_patch — that would silently mutate the "frozen" row on the
    frontend. Only symbols actually subscribed under OWNER_SCANNER (the
    active tab) are forwarded."""
    scanner_l1._pending.clear()
    scanner_l1._active_tab_tables.clear()
    scanner_l1._active_tab_tables["GAINSYM"] = "gainers"
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
    scanner_l1._active_tab_tables.clear()
    scanner_l1._active_tab_tables["AAPL"] = "gainers"
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
    scanner_l1._active_tab_tables.clear()
    scanner_l1._active_tab_tables["AAPL"] = "gainers"
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
