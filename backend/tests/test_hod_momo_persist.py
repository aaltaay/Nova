"""Tests for HOD Momo alert persistence rate-limit and full WS initial payload."""
from __future__ import annotations

import time

import hod_momo as hm
import hod_momo_persist as persist
import hod_momo_session as session
from hod_momo_state import HodMomoState


def test_save_alerts_rate_limited(monkeypatch):
    saves: list[int] = []
    state = hm.replace_state(HodMomoState())

    def fake_save(alerts, ts):
        saves.append(len(alerts))

    monkeypatch.setattr(persist._cache, "save_hod_momo_snapshot", fake_save)
    state.today_alerts = []
    state.alerts_dirty = False
    state.last_alert_save_mono = 0.0

    hm._save_alerts()
    assert len(saves) == 1
    hm._save_alerts()  # within interval → deferred
    assert len(saves) == 1
    assert state.alerts_dirty is True

    state.last_alert_save_mono = time.monotonic() - 100
    hm.flush_pending_alert_save()
    assert len(saves) == 2
    assert state.alerts_dirty is False


def test_ws_initial_payload_keeps_all_alerts():
    state = hm.replace_state(HodMomoState())
    state.today_alerts = [_alert(f"a{i}") for i in range(550)]
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

    monkeypatch.setattr(session, "datetime", _FakeNow)
    state = hm.replace_state(HodMomoState())
    state.session_date = ""
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
    state.today_alerts = list(kept)
    assert hm._check_and_reset_session() is False
    assert len(state.today_alerts) == 1
    assert state.session_date == "2026-07-15"


def test_clear_today_alerts_empties_and_force_saves(monkeypatch):
    saves: list[int] = []
    state = hm.replace_state(HodMomoState())

    def fake_save(alerts, ts):
        saves.append(len(alerts))

    monkeypatch.setattr(persist._cache, "save_hod_momo_snapshot", fake_save)
    state.today_alerts = [
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
    ]
    state.alerts_dirty = False
    state.last_alert_save_mono = 0.0
    out = hm.clear_today_alerts()
    assert out["cleared"] == 1
    assert out["total"] == 0
    assert state.today_alerts == []
    assert saves and saves[-1] == 0


def test_rebound_state_is_seen_by_persistence_and_alert_queries(monkeypatch):
    """A consumer retaining a mutable module alias would save the old owner."""
    old_state = HodMomoState()
    old_state.today_alerts = [_alert("old")]
    hm.replace_state(old_state)

    current_state = HodMomoState()
    current_state.today_alerts = [_alert("current")]
    hm.replace_state(current_state)
    saved_ids: list[list[str]] = []

    monkeypatch.setattr(
        persist._cache,
        "save_hod_momo_snapshot",
        lambda alerts, ts: saved_ids.append([alert["id"] for alert in alerts]),
    )
    hm._save_alerts(force=True)

    assert saved_ids == [["current"]]
    assert [alert["id"] for alert in hm.get_today_alerts()] == ["current"]


def test_rebound_state_replaces_queue_and_websocket_client_set():
    old_state = hm.replace_state(HodMomoState())
    old_queue = hm.get_broadcast_queue()
    old_client = object()
    hm.add_ws_client(old_client)

    current_state = hm.replace_state(HodMomoState())
    current_queue = hm.get_broadcast_queue()
    current_client = object()
    hm.add_ws_client(current_client)

    assert current_queue is not old_queue
    assert hm.get_ws_clients() == {current_client}
    assert old_state.hod_ws_clients == {old_client}
    assert current_state.hod_ws_clients == {current_client}


def test_session_rollover_rebinds_every_session_collection(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    class _FakeNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(
                2026,
                7,
                16,
                10,
                0,
                0,
                tzinfo=tz or ZoneInfo("America/New_York"),
            )

    state = hm.replace_state(HodMomoState())
    state.session_date = "2026-07-15"
    state.today_alerts = [_alert("previous")]
    state.session_highs = {"OLD": 10.0}
    state.cooldown = {("OLD", 11): 1.0}
    state.pending_consolidation = {"OLD": []}
    state.price_buffer = {"OLD": []}
    state.surge_seeded = {"OLD"}
    state.pending_surge_seed = {"OLD"}
    state.last_trade_ts = 1.0
    archived: list[str] = []

    monkeypatch.setattr(session, "datetime", _FakeNow)
    monkeypatch.setattr(
        persist,
        "archive_session_alerts",
        lambda date_str: archived.append(date_str),
    )
    monkeypatch.setattr(persist, "save_alerts", lambda *, force=False: None)

    assert hm._check_and_reset_session() is True
    assert archived == ["2026-07-15"]
    assert state.session_date == "2026-07-16"
    assert state.today_alerts == []
    assert state.session_highs == {}
    assert state.cooldown == {}
    assert state.pending_consolidation == {}
    assert state.price_buffer == {}
    assert state.surge_seeded == set()
    assert state.pending_surge_seed == set()
    assert state.last_trade_ts is None


def _alert(alert_id: str) -> hm.AlertObject:
    return hm.AlertObject(
        id=alert_id,
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
    )
