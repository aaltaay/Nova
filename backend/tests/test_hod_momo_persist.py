"""Tests for HOD Momo alert persistence rate-limit and full WS initial payload."""
from __future__ import annotations

import time

import hod_momo as hm


def test_save_alerts_rate_limited(monkeypatch):
    saves: list[int] = []

    def fake_save(alerts, ts):
        saves.append(len(alerts))

    monkeypatch.setattr(hm._cache, "save_hod_momo_snapshot", fake_save)
    monkeypatch.setattr(hm, "_today_alerts", [])
    monkeypatch.setattr(hm, "_alerts_dirty", False)
    monkeypatch.setattr(hm, "_last_alert_save_mono", 0.0)

    hm._save_alerts()
    assert len(saves) == 1
    hm._save_alerts()  # within interval → deferred
    assert len(saves) == 1
    assert hm._alerts_dirty is True

    monkeypatch.setattr(hm, "_last_alert_save_mono", time.monotonic() - 100)
    hm.flush_pending_alert_save()
    assert len(saves) == 2
    assert hm._alerts_dirty is False


def test_ws_initial_payload_keeps_all_alerts(monkeypatch):
    big = [{"id": f"a{i}", "ticker": "T"} for i in range(550)]
    monkeypatch.setattr(hm, "get_today_alerts", lambda: big)
    payload = hm.get_ws_initial_payload()
    assert payload["type"] == "initial"
    assert payload["total"] == 550
    assert len(payload["alerts"]) == 550


def test_session_init_does_not_wipe_loaded_alerts(monkeypatch):
    """Cold start after 4 AM ET used to treat empty _session_date as a rollover
    and wipe alerts just loaded from today's snapshot."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    class _FakeNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 15, 10, 0, 0, tzinfo=tz or ZoneInfo("America/New_York"))

    monkeypatch.setattr(hm, "datetime", _FakeNow)
    monkeypatch.setattr(hm, "_session_date", "")
    kept = [hm.AlertObject(
        id="a1",
        timestamp="2026-07-15T14:00:00Z",
        ticker="SOBR",
        strategy_id=12,
        strategy_name="Running Up",
        price=1.0,
        change_pct=1.0,
        rvol=2.0,
        float_shares=1e6,
        gap_pct=None,
        volume=1,
        momentum_pct=None,
    )]
    monkeypatch.setattr(hm, "_today_alerts", list(kept))
    assert hm._check_and_reset_session() is False
    assert len(hm._today_alerts) == 1
    assert hm._session_date == "2026-07-15"


def test_clear_today_alerts_empties_and_force_saves(monkeypatch):
    saves: list[int] = []

    def fake_save(alerts, ts):
        saves.append(len(alerts))

    monkeypatch.setattr(hm._cache, "save_hod_momo_snapshot", fake_save)
    monkeypatch.setattr(hm, "_today_alerts", [
        hm.AlertObject(
            id="a1",
            timestamp="2026-07-15T14:00:00Z",
            ticker="SOBR",
            strategy_id=12,
            strategy_name="Running Up",
            price=1.0,
            change_pct=1.0,
            rvol=2.0,
            float_shares=1e6,
            gap_pct=None,
            volume=1,
            momentum_pct=None,
        ),
    ])
    monkeypatch.setattr(hm, "_alerts_dirty", False)
    monkeypatch.setattr(hm, "_last_alert_save_mono", 0.0)
    out = hm.clear_today_alerts()
    assert out["cleared"] == 1
    assert out["total"] == 0
    assert hm._today_alerts == []
    assert saves and saves[-1] == 0
