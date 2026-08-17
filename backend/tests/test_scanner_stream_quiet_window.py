"""Quiet window must not starve one-shot discovery on empty shadow."""
from __future__ import annotations

import time

from ibkr import scanner_stream as stream


def test_quiet_window_ends_after_deadline_even_when_shadow_empty(monkeypatch):
    """Regression 2026-08-07: ``not []`` kept quiet True forever."""
    stream._shadow.clear()
    stream._shadow["gainers"] = []
    stream._shadow["losers"] = []
    # Deadline already in the past.
    stream._ready_quiet_until_mono = time.monotonic() - 1.0
    monkeypatch.setattr(
        stream._session,
        "desired_leases",
        lambda: [("gainers", "TOP_PERC_GAIN"), ("losers", "TOP_PERC_LOSE")],
    )
    monkeypatch.setattr(stream._session, "table_is_live", lambda _t, now=None: True)

    assert stream.in_ready_quiet_window() is False


def test_quiet_window_true_only_before_deadline(monkeypatch):
    stream._shadow.clear()
    stream._ready_quiet_until_mono = time.monotonic() + 60.0
    assert stream.in_ready_quiet_window() is True
    stream._ready_quiet_until_mono = time.monotonic() - 0.1
    assert stream.in_ready_quiet_window() is False
