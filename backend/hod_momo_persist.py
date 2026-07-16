"""HOD Momo configuration and alert persistence imperative shell (Phase 10)."""
from __future__ import annotations

import logging
import time

import cache as _cache
import hod_momo_state as _state
from constants import (
    HOD_MOMO_ALERT_SAVE_INTERVAL_SEC,
    HOD_MOMO_CONFIG_SCHEMA_VERSION,
    HOD_MOMO_MASTER_SURGE_PCT,
    HOD_MOMO_STRATEGY_ID_MAX,
)
from hod_momo_models import (
    alert_from_dict,
    alert_to_dict,
    build_default_config,
    build_default_configs,
    config_from_dict,
    config_to_dict,
    master_from_dict,
    master_to_dict,
)

logger = logging.getLogger(__name__)


def save_configs() -> None:
    state = _state.get_state()
    payload = {
        "schema_version": HOD_MOMO_CONFIG_SCHEMA_VERSION,
        "master": master_to_dict(state.master),
        "strategies": {
            str(sid): config_to_dict(cfg) for sid, cfg in state.configs.items()
        },
    }
    _cache.save_hod_momo_configs(payload)


def _migrate_loaded_configs(data: dict) -> bool:
    state = _state.get_state()
    version = int(data.get("schema_version") or 1)
    changed = False
    if version < 2 and abs(float(state.master.surge_pct) - 3.0) < 1e-9:
        state.master.surge_pct = HOD_MOMO_MASTER_SURGE_PCT
        changed = True
        logger.info(
            "HOD Momo: migrated master surge_pct 3.0 → %s "
            "(schema v2 Warrior parity)",
            HOD_MOMO_MASTER_SURGE_PCT,
        )
    if version < 3:
        if 12 not in state.configs:
            state.configs[12] = build_default_config(12)
        logger.info("HOD Momo: schema v3 — Running Up Alert + 5-min RVOL fields")
        changed = True
    return changed


def _load_configs_from_disk() -> bool:
    data = _cache.load_hod_momo_configs()
    if not data:
        return False
    state = _state.get_state()
    try:
        if "master" in data:
            state.master = master_from_dict(data["master"])
        if "strategies" in data:
            for sid_str, raw in data["strategies"].items():
                sid = int(sid_str)
                if 1 <= sid <= HOD_MOMO_STRATEGY_ID_MAX:
                    state.configs[sid] = config_from_dict(raw)
        added = False
        for sid in range(1, HOD_MOMO_STRATEGY_ID_MAX + 1):
            if sid not in state.configs:
                state.configs[sid] = build_default_config(sid)
                added = True
        if _migrate_loaded_configs(data) or added:
            save_configs()
        return True
    except Exception:
        logger.warning("HOD Momo: failed to load configs from disk — using defaults")
        return False


def load_persisted_state() -> None:
    """Load persisted values into the current state owner."""
    state = _state.get_state()
    state.startup_ts = time.monotonic()
    state.configs = build_default_configs()
    _load_configs_from_disk()
    state.blocklist = {s.upper() for s in _cache.load_hod_momo_blocklist()}
    alerts_raw, _ = _cache.load_hod_momo_snapshot()
    state.today_alerts = [alert_from_dict(alert) for alert in alerts_raw]


def save_alerts(*, force: bool = False) -> None:
    """Persist current alerts with the established hot-session rate limit."""
    state = _state.get_state()
    now = time.monotonic()
    if (
        not force
        and (now - state.last_alert_save_mono)
        < HOD_MOMO_ALERT_SAVE_INTERVAL_SEC
    ):
        state.alerts_dirty = True
        return
    _cache.save_hod_momo_snapshot(
        [alert_to_dict(alert) for alert in state.today_alerts],
        time.time(),
    )
    state.last_alert_save_mono = now
    state.alerts_dirty = False


def flush_pending_alert_save() -> None:
    if _state.get_state().alerts_dirty:
        save_alerts(force=True)


def archive_session_alerts(date_str: str) -> None:
    state = _state.get_state()
    if not state.today_alerts:
        return
    _cache.save_hod_momo_snapshot_for_date(
        date_str,
        [alert_to_dict(alert) for alert in state.today_alerts],
        time.time(),
    )


def get_history_alerts(date_str: str) -> list[dict]:
    data = _cache.load_hod_momo_snapshot_for_date(date_str)
    return data.get("alerts", [])
