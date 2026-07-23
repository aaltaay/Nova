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


def test_rebound_state_replaces_websocket_client_set():
    old_state = hm.replace_state(HodMomoState())
    old_client = object()
    hm.add_ws_client(old_client)

    current_state = hm.replace_state(HodMomoState())
    current_client = object()
    hm.add_ws_client(current_client)

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


def test_save_highs_rate_limited_and_flushed(monkeypatch):
    """Mirrors test_save_alerts_rate_limited — same throttle pattern for highs."""
    saved: list[dict] = []
    state = hm.replace_state(HodMomoState())

    monkeypatch.setattr(persist._cache, "save_hod_momo_highs", saved.append)
    state.session_highs = {"AAA": 5.0}
    state.highs_dirty = False
    state.last_highs_save_mono = 0.0

    persist.save_highs()
    assert len(saved) == 1
    persist.save_highs()  # within interval → deferred
    assert len(saved) == 1
    assert state.highs_dirty is True

    state.last_highs_save_mono = time.monotonic() - 100
    persist.flush_pending_highs_save()
    assert len(saved) == 2
    assert state.highs_dirty is False


def test_session_highs_survive_a_restart(monkeypatch):
    """Regression for PROBLEM_LOG 2026-07-23: session_highs/day_highs/source/
    seeded used to be in-memory only, so a restart wiped already-caught highs.
    Persisting + reloading must restore them onto a brand-new state owner."""
    state = hm.replace_state(HodMomoState())
    state.session_highs = {"WLDS": 3.21}
    state.day_highs = {"WLDS": 3.25}
    state.session_high_source = {"WLDS": "tick6"}
    state.session_high_seeded = {"WLDS"}

    stored: dict = {}
    monkeypatch.setattr(
        persist._cache, "save_hod_momo_highs", lambda data: stored.update(data),
    )
    persist.save_highs(force=True)

    # Simulate a restart: a brand-new state owner with nothing in memory.
    hm.replace_state(HodMomoState())
    monkeypatch.setattr(persist._cache, "load_hod_momo_highs", lambda: dict(stored))
    monkeypatch.setattr(persist._cache, "load_hod_momo_blocklist", lambda: [])
    monkeypatch.setattr(persist._cache, "load_hod_momo_snapshot", lambda: ([], None))

    persist.load_persisted_state()
    new_state = hm.get_state()
    assert new_state.session_highs == {"WLDS": 3.21}
    assert new_state.day_highs == {"WLDS": 3.25}
    assert new_state.session_high_source == {"WLDS": "tick6"}
    assert new_state.session_high_seeded == {"WLDS"}


def test_schema_v4_disables_former_momo(monkeypatch):
    """Persisted Former Momo enabled=True must turn off once on schema v4 load."""
    state = hm.replace_state(HodMomoState())
    monkeypatch.setattr(
        persist._cache,
        "load_hod_momo_configs",
        lambda: {
            "schema_version": 3,
            "master": {},
            "strategies": {
                "1": {
                    "strategy_id": 1,
                    "name": "Former Momo Stock",
                    "color": "#FF9100",
                    "enabled": True,
                    "former_momo_list": ["BIYA"],
                }
            },
        },
    )
    saved: list[dict] = []
    monkeypatch.setattr(persist._cache, "save_hod_momo_configs", saved.append)
    monkeypatch.setattr(persist._cache, "load_hod_momo_blocklist", lambda: [])
    monkeypatch.setattr(persist._cache, "load_hod_momo_snapshot", lambda: ([], None))

    persist.load_persisted_state()

    assert state.configs[1].enabled is False
    assert "BIYA" in state.configs[1].former_momo_list
    assert saved and saved[-1]["schema_version"] == persist.HOD_MOMO_CONFIG_SCHEMA_VERSION
    assert saved[-1]["strategies"]["1"]["enabled"] is False


def test_schema_v5_squeeze_requires_hod_and_reenables(monkeypatch):
    """CNF-class false positives: Squeeze without HOD + mass-disabled floats."""
    state = hm.replace_state(HodMomoState())
    monkeypatch.setattr(
        persist._cache,
        "load_hod_momo_configs",
        lambda: {
            "schema_version": 4,
            "master": {},
            "strategies": {
                "1": {
                    "strategy_id": 1,
                    "name": "Former Momo Stock",
                    "color": "#FF9100",
                    "enabled": False,
                },
                "7": {
                    "strategy_id": 7,
                    "name": "Low Float - High Rel Vol",
                    "color": "#00E676",
                    "enabled": False,
                    "requires_hod": True,
                },
                "10": {
                    "strategy_id": 10,
                    "name": "Squeeze Alert - Up 10% in 10min",
                    "color": "#00E5FF",
                    "enabled": True,
                    "requires_hod": False,
                    "surge_pct": 10.0,
                    "surge_window_min": 10,
                },
                "11": {
                    "strategy_id": 11,
                    "name": "Squeeze Alert - Up 5% in 5min",
                    "color": "#40C4FF",
                    "enabled": True,
                    "requires_hod": False,
                    "surge_pct": 5.0,
                    "surge_window_min": 5,
                },
            },
        },
    )
    saved: list[dict] = []
    monkeypatch.setattr(persist._cache, "save_hod_momo_configs", saved.append)
    monkeypatch.setattr(persist._cache, "load_hod_momo_blocklist", lambda: [])
    monkeypatch.setattr(persist._cache, "load_hod_momo_snapshot", lambda: ([], None))

    persist.load_persisted_state()

    assert state.configs[1].enabled is False
    assert state.configs[7].enabled is True
    assert state.configs[10].requires_hod is True
    assert state.configs[11].requires_hod is True
    assert saved[-1]["schema_version"] == persist.HOD_MOMO_CONFIG_SCHEMA_VERSION


def test_schema_v7_restores_zeroed_squeeze_surge(monkeypatch):
    """Historical bug: Squeeze #10/#11 persisted with surge_pct=0 while
    surge_window_min still matched the strategy's own default window — a
    silent no-op filter instead of Warrior's 10%/10m and 5%/5m gate."""
    state = hm.replace_state(HodMomoState())
    monkeypatch.setattr(
        persist._cache,
        "load_hod_momo_configs",
        lambda: {
            "schema_version": 5,
            "master": {},
            "strategies": {
                "10": {
                    "strategy_id": 10,
                    "name": "Squeeze Alert - Up 10% in 10min",
                    "color": "#00E5FF",
                    "enabled": True,
                    "requires_hod": True,
                    "surge_pct": 0.0,
                    "surge_window_min": 10,
                },
                "11": {
                    "strategy_id": 11,
                    "name": "Squeeze Alert - Up 5% in 5min",
                    "color": "#40C4FF",
                    "enabled": True,
                    "requires_hod": True,
                    "surge_pct": 0.0,
                    "surge_window_min": 5,
                },
            },
        },
    )
    saved: list[dict] = []
    monkeypatch.setattr(persist._cache, "save_hod_momo_configs", saved.append)
    monkeypatch.setattr(persist._cache, "load_hod_momo_blocklist", lambda: [])
    monkeypatch.setattr(persist._cache, "load_hod_momo_snapshot", lambda: ([], None))

    persist.load_persisted_state()

    assert state.configs[10].surge_pct == 10.0
    assert state.configs[10].surge_window_min == 10
    assert state.configs[11].surge_pct == 5.0
    assert state.configs[11].surge_window_min == 5
    assert saved[-1]["schema_version"] == persist.HOD_MOMO_CONFIG_SCHEMA_VERSION


def test_schema_v7_leaves_deliberately_changed_window_alone(monkeypatch):
    """A user who changed surge_window_min away from the default (and thus
    has surge_pct=0 for an unrelated reason) must not be silently repaired."""
    state = hm.replace_state(HodMomoState())
    monkeypatch.setattr(
        persist._cache,
        "load_hod_momo_configs",
        lambda: {
            "schema_version": 5,
            "master": {},
            "strategies": {
                "11": {
                    "strategy_id": 11,
                    "name": "Squeeze Alert - Up 5% in 5min",
                    "color": "#40C4FF",
                    "enabled": True,
                    "requires_hod": True,
                    "surge_pct": 0.0,
                    "surge_window_min": 7,
                },
            },
        },
    )
    monkeypatch.setattr(persist._cache, "save_hod_momo_configs", lambda payload: None)
    monkeypatch.setattr(persist._cache, "load_hod_momo_blocklist", lambda: [])
    monkeypatch.setattr(persist._cache, "load_hod_momo_snapshot", lambda: ([], None))

    persist.load_persisted_state()

    assert state.configs[11].surge_pct == 0.0
    assert state.configs[11].surge_window_min == 7


def test_load_configs_retires_positive_cooldown_mute(monkeypatch):
    """Anti-spam mute retired — persisted cooldown_sec>0 resets to 0 (burst only)."""
    from constants import HOD_MOMO_COOLDOWN_SEC

    state = hm.replace_state(HodMomoState())
    monkeypatch.setattr(
        persist._cache,
        "load_hod_momo_configs",
        lambda: {
            "schema_version": persist.HOD_MOMO_CONFIG_SCHEMA_VERSION,
            "master": {"cooldown_sec": 60.0},
            "strategies": {},
        },
    )
    saved: list[dict] = []
    monkeypatch.setattr(persist._cache, "save_hod_momo_configs", saved.append)

    persist.load_persisted_state()

    assert HOD_MOMO_COOLDOWN_SEC == 0.0
    assert state.master.cooldown_sec == HOD_MOMO_COOLDOWN_SEC
    assert saved and saved[-1]["master"]["cooldown_sec"] == HOD_MOMO_COOLDOWN_SEC


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
