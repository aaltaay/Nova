"""Large Cap roster-commit hook (ADR 014) -- fundamentals warm + daily-bar prefetch."""
from __future__ import annotations

import threading
import time

import large_cap_hooks
from ibkr import scanner_session as _ss


def test_ignores_non_large_cap_tables(monkeypatch):
    called = []
    monkeypatch.setattr(threading, "Thread", lambda *a, **k: called.append(True))
    large_cap_hooks.on_large_cap_roster_commit(_ss.TABLE_GAINERS, [{"symbol": "AAA"}])
    assert called == []


def test_ignores_empty_roster(monkeypatch):
    called = []
    monkeypatch.setattr(threading, "Thread", lambda *a, **k: called.append(True))
    large_cap_hooks.on_large_cap_roster_commit(_ss.TABLE_LARGE_CAP, [])
    assert called == []


def test_warms_fundamentals_in_background_thread_and_schedules_daily_bars(monkeypatch):
    warmed: list[list[str]] = []
    monkeypatch.setattr(large_cap_hooks, "_warm_fundamentals", lambda syms: warmed.append(syms))

    import large_cap_metrics as _metrics

    scheduled: list[str] = []
    monkeypatch.setattr(_metrics, "schedule_daily_fill", lambda sym: scheduled.append(sym))

    rows = [{"symbol": "NVDA"}, {"symbol": "AMD"}]
    large_cap_hooks.on_large_cap_roster_commit(_ss.TABLE_LARGE_CAP, rows)

    # Background thread — give it a beat to run.
    time.sleep(0.05)
    assert warmed and set(warmed[0]) == {"NVDA", "AMD"}
    assert set(scheduled) == {"NVDA", "AMD"}
