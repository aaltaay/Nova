"""Background fundamentals warm for the Earnings tab -- single-flight semantics."""
from __future__ import annotations

import time

import earnings_enrich_hooks as hooks


def test_warm_ignores_empty_input():
    hooks.reset_for_testing()
    hooks.warm([])
    hooks.warm(None or [])


def test_warm_runs_in_background_thread(monkeypatch):
    hooks.reset_for_testing()
    calls: list[list[str]] = []
    monkeypatch.setattr("fundamentals.fetch_fundamentals_batch", lambda syms: calls.append(list(syms)))

    hooks.warm(["nvda", " amd "])
    time.sleep(0.05)

    assert calls and set(calls[0]) == {"NVDA", "AMD"}


def test_warm_second_call_while_running_coalesces(monkeypatch):
    hooks.reset_for_testing()
    calls: list[list[str]] = []

    def _slow_batch(syms):
        calls.append(list(syms))
        time.sleep(0.05)

    monkeypatch.setattr("fundamentals.fetch_fundamentals_batch", _slow_batch)

    hooks.warm(["NVDA"])
    hooks.warm(["AMD"])  # arrives while the worker may still be draining
    time.sleep(0.2)

    all_seen = {sym for batch in calls for sym in batch}
    assert {"NVDA", "AMD"} <= all_seen
