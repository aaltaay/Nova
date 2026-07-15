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
