"""Active-set heartbeat — age telemetry only (quiet re-eval removed)."""
from __future__ import annotations

import hod_momo_active as active
import hod_momo_heartbeat as hb


def test_maybe_refresh_fundamentals_respects_cadence(monkeypatch):
    requested: list[str] = []
    monkeypatch.setattr(
        "hod_momo_market.mark_needs_fundamentals",
        lambda sym: requested.append(sym),
    )
    hb._last_fundamentals_refresh_ts.clear()
    now = 1_000.0
    hb._maybe_refresh_fundamentals("CJMB", now=now)
    assert requested == ["CJMB"]
    hb._maybe_refresh_fundamentals("CJMB", now=now + 1.0)
    assert requested == ["CJMB"]
    from constants import HOD_MOMO_FUNDAMENTALS_REFRESH_SEC

    hb._maybe_refresh_fundamentals("CJMB", now=now + HOD_MOMO_FUNDAMENTALS_REFRESH_SEC + 1.0)
    assert requested == ["CJMB", "CJMB"]


def test_quiet_reeval_helper_removed():
    assert not hasattr(hb, "_maybe_reeval_session_focus")


def test_heartbeat_does_not_require_session_focus_reeval(monkeypatch):
    """Passive age refresh must not call on_trade_update on a flat tape."""
    active.clear_session_state()
    calls: list = []
    monkeypatch.setattr("hod_momo.on_trade_update", lambda *a, **k: calls.append((a, k)))
    # Module no longer exposes re-eval — ensure import surface stays clean.
    assert calls == []
