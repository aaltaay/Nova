"""Large Cap roster-commit hook (ADR 014) -- fundamentals warm + daily-bar prefetch."""
from __future__ import annotations

import asyncio
import threading
import time

import large_cap_hooks
from ibkr import scanner_session as _ss


def commit(table: str, rows: list[dict]) -> None:
    asyncio.run(large_cap_hooks.on_large_cap_roster_commit(table, rows))


def test_ignores_non_large_cap_tables(monkeypatch):
    called = []
    monkeypatch.setattr(threading, "Thread", lambda *a, **k: called.append(True))
    commit(_ss.TABLE_GAINERS, [{"symbol": "AAA"}])
    assert called == []


def test_ignores_empty_roster(monkeypatch):
    called = []
    monkeypatch.setattr(threading, "Thread", lambda *a, **k: called.append(True))
    commit(_ss.TABLE_LARGE_CAP, [])
    assert called == []


def test_warms_fundamentals_in_background_thread_and_schedules_daily_bars(monkeypatch):
    warmed: list[list[str]] = []
    monkeypatch.setattr(large_cap_hooks, "_warm_fundamentals", lambda syms: warmed.append(syms))

    import bars_store
    import large_cap_metrics as _metrics

    monkeypatch.setattr(bars_store, "read", lambda *a, **k: None)
    scheduled: list[str] = []
    monkeypatch.setattr(_metrics, "schedule_daily_fill", lambda sym: scheduled.append(sym))

    rows = [{"symbol": "NVDA"}, {"symbol": "AMD"}]
    commit(_ss.TABLE_LARGE_CAP, rows)

    # Background thread — give it a beat to run.
    time.sleep(0.05)
    assert warmed and set(warmed[0]) == {"NVDA", "AMD"}
    assert set(scheduled) == {"NVDA", "AMD"}


def test_skips_schedule_when_store_already_complete(monkeypatch):
    """A symbol with a full stored 1Day series must not spend an IB token."""
    monkeypatch.setattr(large_cap_hooks, "_warm_fundamentals", lambda syms: None)

    import bars_store
    import large_cap_metrics as _metrics
    from constants import LARGE_CAP_DAILY_BARS_LOOKBACK

    complete = {
        "bars": [{"t": f"d{i}", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}
                 for i in range(LARGE_CAP_DAILY_BARS_LOOKBACK + 1)],
    }
    monkeypatch.setattr(bars_store, "read", lambda *a, **k: complete)
    scheduled: list[str] = []
    monkeypatch.setattr(_metrics, "schedule_daily_fill", lambda sym: scheduled.append(sym))

    commit(_ss.TABLE_LARGE_CAP, [{"symbol": "AAPL"}])
    assert scheduled == []


def test_the_store_is_read_off_the_event_loop_and_fills_are_scheduled_on_it(monkeypatch):
    """2026-10-07: the hook read each Large Cap symbol's daily bars on the HTTP loop, 206-549 ms a commit."""
    monkeypatch.setattr(large_cap_hooks, "_warm_fundamentals", lambda syms: None)

    import bars_store
    import large_cap_metrics as _metrics

    readers: list[int] = []
    monkeypatch.setattr(bars_store, "read", lambda *a, **k: readers.append(threading.get_ident()))
    scheduled: list[tuple[str, int]] = []
    monkeypatch.setattr(_metrics, "schedule_daily_fill", lambda sym: scheduled.append((sym, threading.get_ident())))

    async def on_the_loop() -> int:
        await large_cap_hooks.on_large_cap_roster_commit(_ss.TABLE_LARGE_CAP, [{"symbol": "NVDA"}, {"symbol": "AMD"}])
        return threading.get_ident()

    loop_thread = asyncio.run(on_the_loop())
    assert len(readers) == 2 and loop_thread not in readers
    assert [sym for sym, _ in scheduled] == ["NVDA", "AMD"]
    assert {ident for _, ident in scheduled} == {loop_thread}
