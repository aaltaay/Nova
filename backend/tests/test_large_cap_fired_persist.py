"""D-028: Large Cap breakout dedupe survives process restart."""
from __future__ import annotations

import json
from pathlib import Path

import cache as cache_mod
import large_cap_alerts as lca
from cache_schema import LARGE_CAP_SCHEMA_VERSION
from market import session_key_et


def test_fired_today_survives_memory_reset(monkeypatch):
    monkeypatch.setattr("alerts.dispatch.dispatch_alert", lambda event: None)
    first = lca.check_breakout("NVDA", price=200.0, high_20d=190.0, low_20d=150.0, rvol=2.5)
    assert first is not None
    lca.reset_for_testing()
    second = lca.check_breakout("NVDA", price=201.0, high_20d=190.0, low_20d=150.0, rvol=2.5)
    assert second is None


def test_unknown_schema_does_not_restore_fired(monkeypatch):
    monkeypatch.setattr("alerts.dispatch.dispatch_alert", lambda event: None)
    today = cache_mod._today_et()
    path = Path(cache_mod._CACHE_DIR) / f"large_cap-{today}.json"
    path.write_text(
        json.dumps({
            "schema_version": LARGE_CAP_SCHEMA_VERSION + 9,
            "date": today,
            "fired_today": {"NVDA:up": session_key_et()},
        }),
        encoding="utf-8",
    )
    event = lca.check_breakout("NVDA", price=200.0, high_20d=190.0, low_20d=150.0, rvol=2.5)
    assert event is not None
