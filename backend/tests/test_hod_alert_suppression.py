"""One late quote fails the HOD banner but never mutes every other name's alerts (2026-10-13)."""
from __future__ import annotations

import integrity_live as live
from hod_momo_integrity_common import age_gate


def _gate(p95: float, mx: float) -> dict:
    return age_gate(cid="hod_active_quote_age", p95=p95, mx=mx, p95_limit=2.0, max_limit=3.0,
                    label="active quote age")


def test_age_gate_says_whether_one_name_or_the_feed_is_late():
    one = _gate(0.57, 3.23)  # 08:15:22's fail: one name 0.23 s past the line
    assert (one["status"], one["breadth"]) == ("fail", "one_symbol")
    feed = _gate(2.4, 9.0)
    assert (feed["status"], feed["breadth"]) == ("fail", "feed")
    assert "breadth" not in _gate(0.5, 1.0)


def _report(*checks: dict) -> dict:
    return {"status": "fail", "hod": {"status": "fail", "checks": list(checks)}, "scanner": {"status": "pass"}}


def test_one_late_name_fails_the_banner_but_does_not_mute_alerts(monkeypatch):
    monkeypatch.setattr(live, "_last_report", _report(_gate(0.57, 93.3)), raising=False)
    assert live.hod_integrity_is_failing() is True
    assert live.hod_alerts_suppressed() is False


def test_a_late_feed_or_dead_ticks_still_mute_alerts(monkeypatch):
    monkeypatch.setattr(live, "_last_report", _report(_gate(2.4, 9.0)), raising=False)
    assert live.hod_alerts_suppressed() is True
    dead = {"id": "hod_ticks_flowing", "status": "fail", "detail": "no ticks for 30s"}
    monkeypatch.setattr(live, "_last_report", _report(_gate(0.5, 1.0), dead), raising=False)
    assert live.hod_alerts_suppressed() is True


def test_nothing_known_or_a_scanner_only_fail_mutes_nothing(monkeypatch):
    monkeypatch.setattr(live, "_last_report", None, raising=False)
    assert live.hod_alerts_suppressed() is False
    monkeypatch.setattr(live, "_last_report",
                        {"status": "fail", "hod": {"status": "pass", "checks": []}, "scanner": {"status": "fail"}},
                        raising=False)
    assert live.hod_alerts_suppressed() is False
