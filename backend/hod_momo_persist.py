"""HOD Momo configuration and alert persistence imperative shell (Phase 10)."""
from __future__ import annotations

import logging
import time

import cache as _cache
import hod_momo_state as _state
from constants import (
    HOD_MOMO_ALERT_SAVE_INTERVAL_SEC,
    HOD_MOMO_CONFIG_SCHEMA_VERSION,
    HOD_MOMO_COOLDOWN_SEC,
    HOD_MOMO_FORMER_MOMO_DEFAULT_LIST,
    HOD_MOMO_FORMER_MOMO_STRATEGY_ID,
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

# Mute retired 2026-07-17 — any persisted positive cooldown is forced back to
# HOD_MOMO_COOLDOWN_SEC (0). Burst/consolidation is the only rate limit.


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
    if version < 4:
        # Former Momo has no public Warrior formula — disable until we own a fill path.
        cfg = state.configs.get(HOD_MOMO_FORMER_MOMO_STRATEGY_ID)
        if cfg is not None and cfg.enabled:
            cfg.enabled = False
            changed = True
        logger.info(
            "HOD Momo: schema v4 — Former Momo Stock (strategy %s) disabled by default",
            HOD_MOMO_FORMER_MOMO_STRATEGY_ID,
        )
        changed = True
    if version < 5:
        # Live bug: Squeeze 5%/10% had requires_hod=False so names like CNF fired
        # without a new HOD — Warrior Small-Cap HOD Momentum never would.
        # Also restore enabled=True for non-Former strategies if a accidental
        # mass-disable left only Squeeze on.
        for sid, cfg in list(state.configs.items()):
            if cfg is None:
                continue
            if sid in (10, 11) and not cfg.requires_hod:
                cfg.requires_hod = True
                changed = True
            if sid != HOD_MOMO_FORMER_MOMO_STRATEGY_ID and not cfg.enabled:
                cfg.enabled = True
                changed = True
        logger.info(
            "HOD Momo: schema v5 — Squeeze requires_hod=True; re-enable non-Former strategies"
        )
        changed = True
    if version < 6:
        # REQ-HOD-005/006: Former Momo is manual-only now (no more alert-history
        # bootstrap). Seed the default watchlist once — only if still empty, so
        # an install that already manually curated a list is never clobbered.
        cfg = state.configs.get(HOD_MOMO_FORMER_MOMO_STRATEGY_ID)
        if cfg is not None and not cfg.former_momo_list:
            cfg.former_momo_list = list(HOD_MOMO_FORMER_MOMO_DEFAULT_LIST)
            logger.info(
                "HOD Momo: schema v6 — seeded default Former Momo list %s",
                cfg.former_momo_list,
            )
            changed = True
        changed = True
    if version < 7:
        # Historical config bug: some installs persisted Squeeze #10/#11 with
        # surge_pct zeroed out while surge_window_min still matched the
        # strategy's own default window — a silent no-op filter (surge_pct=0
        # always passes) instead of Warrior's actual 10%/10m and 5%/5m gate.
        # Only repair the exact zeroed-surge/matching-window shape so a user
        # who deliberately changed the window (and thus surge_pct) is left
        # alone; never touch enabled/audio/other fields.
        squeeze_repairs = {10: (10.0, 10), 11: (5.0, 5)}
        for sid, (default_surge, default_window) in squeeze_repairs.items():
            cfg = state.configs.get(sid)
            if cfg is None:
                continue
            if (
                float(cfg.surge_pct or 0.0) == 0.0
                and int(cfg.surge_window_min or 0) == default_window
            ):
                cfg.surge_pct = default_surge
                logger.info(
                    "HOD Momo: schema v7 — restored strategy %d surge_pct to %.1f%% "
                    "(surge_window_min=%d was unchanged; surge_pct had been zeroed)",
                    sid, default_surge, default_window,
                )
                changed = True
    return changed


def _load_configs_from_disk() -> bool:
    data = _cache.load_hod_momo_configs()
    if not data:
        return False
    state = _state.get_state()
    try:
        cooldown_repaired = False
        if "master" in data:
            state.master = master_from_dict(data["master"])
            if float(state.master.cooldown_sec or 0.0) != float(HOD_MOMO_COOLDOWN_SEC):
                logger.warning(
                    "HOD Momo: anti-spam mute retired — persisted "
                    "cooldown_sec=%.2f reset to %.1f (burst/consolidation only)",
                    state.master.cooldown_sec,
                    HOD_MOMO_COOLDOWN_SEC,
                )
                state.master.cooldown_sec = HOD_MOMO_COOLDOWN_SEC
                cooldown_repaired = True
        if "strategies" in data:
            for sid_str, raw in data["strategies"].items():
                sid = int(sid_str)
                if 1 <= sid <= HOD_MOMO_STRATEGY_ID_MAX:
                    state.configs[sid] = config_from_dict(raw)
        added = cooldown_repaired
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
    _load_highs_from_disk()


def _load_highs_from_disk() -> None:
    """Restore today's HOD-high truth so a restart doesn't re-blind an already
    correctly-seeded symbol (session_date mismatch is handled by the dated
    cache file itself — a stale prior-day file is simply not returned)."""
    state = _state.get_state()
    data = _cache.load_hod_momo_highs()
    if not data:
        return
    try:
        state.session_highs = {
            str(k): float(v) for k, v in (data.get("session_highs") or {}).items()
        }
        state.day_highs = {
            str(k): float(v) for k, v in (data.get("day_highs") or {}).items()
        }
        state.session_high_source = {
            str(k): str(v) for k, v in (data.get("session_high_source") or {}).items()
        }
        state.session_high_seeded = {
            str(s) for s in (data.get("session_high_seeded") or [])
        }
        logger.info(
            "HOD Momo: restored %d session high(s) from disk", len(state.session_highs),
        )
    except Exception:
        logger.warning("HOD Momo: failed to restore session highs from disk", exc_info=True)


def save_highs(*, force: bool = False) -> None:
    """Persist current HOD-high truth fields with the established hot-session rate limit."""
    state = _state.get_state()
    now = time.monotonic()
    if (
        not force
        and (now - state.last_highs_save_mono) < HOD_MOMO_ALERT_SAVE_INTERVAL_SEC
    ):
        state.highs_dirty = True
        return
    _cache.save_hod_momo_highs({
        "session_highs": dict(state.session_highs),
        "day_highs": dict(state.day_highs),
        "session_high_source": dict(state.session_high_source),
        "session_high_seeded": sorted(state.session_high_seeded),
    })
    state.last_highs_save_mono = now
    state.highs_dirty = False


def flush_pending_highs_save() -> None:
    if _state.get_state().highs_dirty:
        save_highs(force=True)


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
