"""Large Cap breakout alert channel (ADR 014) -- own channel, never HOD."""
from __future__ import annotations

import large_cap_alerts as lca


def test_no_alert_below_rvol_threshold():
    event = lca.check_breakout("NVDA", price=200.0, high_20d=190.0, low_20d=150.0, rvol=1.0)
    assert event is None


def test_alert_fires_on_20d_high_break_with_rvol_confirmation(monkeypatch):
    dispatched = []
    monkeypatch.setattr(
        "alerts.dispatch.dispatch_alert", lambda event: dispatched.append(event),
    )
    event = lca.check_breakout("NVDA", price=200.0, high_20d=190.0, low_20d=150.0, rvol=2.5)
    assert event is not None
    assert event["direction"] == "up"
    assert event["symbol"] == "NVDA"
    assert dispatched and dispatched[0]["symbol"] == "NVDA"


def test_alert_fires_on_20d_low_break(monkeypatch):
    monkeypatch.setattr("alerts.dispatch.dispatch_alert", lambda event: None)
    event = lca.check_breakout("META", price=140.0, high_20d=200.0, low_20d=150.0, rvol=3.0)
    assert event is not None
    assert event["direction"] == "down"


def test_alert_dedupes_same_symbol_direction_same_session(monkeypatch):
    monkeypatch.setattr("alerts.dispatch.dispatch_alert", lambda event: None)
    first = lca.check_breakout("AMD", price=200.0, high_20d=190.0, low_20d=150.0, rvol=2.5)
    second = lca.check_breakout("AMD", price=201.0, high_20d=190.0, low_20d=150.0, rvol=2.5)
    assert first is not None
    assert second is None  # already fired this session for (AMD, up)


def test_alert_history_records_fired_events(monkeypatch):
    monkeypatch.setattr("alerts.dispatch.dispatch_alert", lambda event: None)
    lca.check_breakout("TSLA", price=300.0, high_20d=290.0, low_20d=250.0, rvol=4.0)
    history = lca.get_alert_history()
    assert history and history[0]["symbol"] == "TSLA"


def test_no_alert_when_price_within_range():
    event = lca.check_breakout("AAPL", price=175.0, high_20d=190.0, low_20d=150.0, rvol=5.0)
    assert event is None


def test_dispatch_failure_does_not_raise(monkeypatch):
    def _boom(event):
        raise RuntimeError("channel down")

    monkeypatch.setattr("alerts.dispatch.dispatch_alert", _boom)
    event = lca.check_breakout("GOOGL", price=200.0, high_20d=190.0, low_20d=150.0, rvol=2.5)
    assert event is not None  # still recorded + returned despite dispatch failure
