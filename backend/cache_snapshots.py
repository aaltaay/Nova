"""Dated scanner / HOD snapshot save+load. Callers keep importing ``cache``.

Scanner boards are dated by their exchange session (``_session_date_et``), so a
weekend re-persist lands on Friday's file (#483); HOD Momo files keep the
calendar session key their rollover and archive paths read.
"""
from __future__ import annotations

import json
import logging
import os

import cache as _cache
from cache_schema import (
    HOD_MOMO_BLOCKLIST_SCHEMA_VERSION,
    accept_schema,
    stamp_schema,
)
# Paths live on ``cache`` so conftest / tests can monkeypatch them.

logger = logging.getLogger("cache")


def _load_today_list(
    prefix: str, key: str, *, normalize: bool = False, session: bool = True,
) -> tuple[list, float]:
    """Today's list; a scanner board's day is its exchange session (#483)."""
    day = _cache._session_date_et() if session else _cache._today_et()
    data = _cache._read_dated_json(prefix, day)
    if data.get("date") != day:
        return [], 0.0
    raw = data.get(key, [])
    if not isinstance(raw, list):
        return [], 0.0
    rows = [_cache._normalize_gapper_row(g) for g in raw] if normalize else raw
    return rows, float(data.get("ts", 0.0))


def save_gapper_snapshot(gappers: list[dict], ts: float) -> None:
    """Atomically persist the gapper cache to today's dated file.

    Empty payloads are refused: a transient zero projection (names-first
    Gainers replace, last name dropping below the floor) must not wipe the
    day's history file.
    """
    if not gappers:
        return
    try:
        _cache._write_dated(
            "gappers",
            _cache._session_date_et(),
            {"date": _cache._session_date_et(), "ts": ts, "gappers": gappers},
        )
    except Exception:
        logger.warning("cache: save_gapper_snapshot failed to persist to disk", exc_info=True)


def load_gapper_snapshot() -> tuple[list[dict], float]:
    try:
        return _load_today_list("gappers", "gappers", normalize=True)
    except Exception:
        return [], 0.0


def save_afterhours_snapshot(rows: list[dict], ts: float) -> None:
    if not rows:
        return
    try:
        _cache._write_dated(
            "afterhours",
            _cache._session_date_et(),
            {"date": _cache._session_date_et(), "ts": ts, "afterhours": rows},
        )
    except Exception:
        logger.warning("cache: save_afterhours_snapshot failed to persist to disk", exc_info=True)


def save_large_cap_snapshot(rows: list[dict], ts: float) -> None:
    if not rows:
        return
    try:
        existing = _cache._read_dated_json("large_cap", _cache._session_date_et())
        _cache._write_dated(
            "large_cap",
            _cache._session_date_et(),
            {
                "date": _cache._session_date_et(),
                "ts": ts,
                "large_cap": rows,
                "fired_today": existing.get("fired_today") or {},
            },
        )
    except Exception:
        logger.warning("cache: save_large_cap_snapshot failed to persist to disk", exc_info=True)


def load_afterhours_snapshot() -> tuple[list[dict], float]:
    try:
        return _load_today_list("afterhours", "afterhours", normalize=True)
    except Exception:
        return [], 0.0


def save_gainer_snapshot(gainers: list[dict], ts: float) -> None:
    if not gainers:
        return
    try:
        _cache._write_dated(
            "gainers",
            _cache._session_date_et(),
            {"date": _cache._session_date_et(), "ts": ts, "gainers": gainers},
        )
    except Exception:
        logger.warning("cache: save_gainer_snapshot failed to persist to disk", exc_info=True)


def load_gainer_snapshot() -> tuple[list[dict], float]:
    try:
        return _load_today_list("gainers", "gainers")
    except Exception:
        return [], 0.0


def save_loser_snapshot(losers: list[dict], ts: float) -> None:
    if not losers:
        return
    try:
        _cache._write_dated(
            "losers",
            _cache._session_date_et(),
            {"date": _cache._session_date_et(), "ts": ts, "losers": losers},
        )
    except Exception:
        logger.warning("cache: save_loser_snapshot failed to persist to disk", exc_info=True)


def load_loser_snapshot() -> tuple[list[dict], float]:
    try:
        return _load_today_list("losers", "losers")
    except Exception:
        return [], 0.0


def save_movers_snapshot(gainers: list[dict], losers: list[dict], ts: float) -> None:
    try:
        _cache._write_dated(
            "movers",
            _cache._session_date_et(),
            {"date": _cache._session_date_et(), "ts": ts, "gainers": gainers, "losers": losers},
        )
    except Exception:
        logger.warning("cache: save_movers_snapshot failed to persist to disk", exc_info=True)


def load_movers_snapshot() -> tuple[list[dict], list[dict], float]:
    gainers, gainers_ts = load_gainer_snapshot()
    losers, losers_ts = load_loser_snapshot()
    if gainers and losers:
        return gainers, losers, max(gainers_ts, losers_ts)
    try:
        data = _cache._read_dated_json("movers", _cache._session_date_et())
        if data.get("date") == _cache._session_date_et():
            legacy_gainers = data.get("gainers", [])
            legacy_losers = data.get("losers", [])
            legacy_ts = float(data.get("ts", 0.0))
            if not gainers and isinstance(legacy_gainers, list):
                gainers, gainers_ts = legacy_gainers, legacy_ts
            if not losers and isinstance(legacy_losers, list):
                losers, losers_ts = legacy_losers, legacy_ts
    except Exception:
        pass
    return gainers, losers, max(gainers_ts, losers_ts)


def save_hod_momo_snapshot(alerts: list[dict], ts: float) -> None:
    save_hod_momo_snapshot_for_date(_cache._today_et(), alerts, ts)


def save_hod_momo_snapshot_for_date(date_str: str, alerts: list[dict], ts: float) -> None:
    try:
        _cache._write_dated(
            _cache.HOD_MOMO_ALERTS_PREFIX,
            date_str,
            {"date": date_str, "ts": ts, "alerts": alerts},
        )
    except Exception:
        logger.warning(
            "cache: save_hod_momo_snapshot_for_date(%s) failed to persist to disk",
            date_str,
            exc_info=True,
        )


def load_hod_momo_snapshot() -> tuple[list[dict], float]:
    try:
        return _load_today_list(_cache.HOD_MOMO_ALERTS_PREFIX, "alerts", session=False)
    except Exception:
        return [], 0.0


def load_hod_momo_snapshot_for_date(date_str: str) -> dict:
    return _cache._read_dated_json(_cache.HOD_MOMO_ALERTS_PREFIX, date_str)


def save_hod_momo_highs(data: dict) -> None:
    save_hod_momo_highs_for_date(_cache._today_et(), data)


def save_hod_momo_highs_for_date(date_str: str, data: dict) -> None:
    """``date_str`` is the day the snapshot was taken (HOD Momo's writer, #553)."""
    try:
        _cache._write_dated(
            _cache.HOD_MOMO_HIGHS_PREFIX,
            date_str,
            {"date": date_str, **data},
        )
    except Exception:
        logger.warning("cache: save_hod_momo_highs failed to persist to disk", exc_info=True)


def load_hod_momo_highs() -> dict:
    try:
        data = _cache._read_dated_json(_cache.HOD_MOMO_HIGHS_PREFIX, _cache._today_et())
        if data.get("date") != _cache._today_et():
            return {}
        return data
    except Exception:
        return {}


def save_hod_momo_configs(payload: dict) -> None:
    try:
        os.makedirs(_cache._CACHE_DIR, exist_ok=True)
        _cache._atomic_write(_cache.HOD_MOMO_CONFIG_FILE, payload)
    except Exception:
        logger.warning("cache: save_hod_momo_configs failed to persist to disk", exc_info=True)


def load_hod_momo_configs() -> dict:
    try:
        with open(_cache.HOD_MOMO_CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_large_cap_config(payload: dict) -> None:
    try:
        os.makedirs(_cache._CACHE_DIR, exist_ok=True)
        _cache._atomic_write(_cache.LARGE_CAP_CONFIG_FILE, payload)
    except Exception:
        logger.warning("cache: save_large_cap_config failed to persist to disk", exc_info=True)


def load_large_cap_config() -> dict:
    try:
        with open(_cache.LARGE_CAP_CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_desk_venue(payload: dict) -> bool:
    """Owner: sim/mode.py. Invalidation: operator venue click. Version stamped.

    Returns whether the write landed -- the caller reports ``persisted`` to the
    operator, and a venue that silently failed to persist is exactly the state
    ADR 018 exists to make visible.
    """
    try:
        os.makedirs(_cache._CACHE_DIR, exist_ok=True)
        _cache._atomic_write(_cache.DESK_VENUE_FILE, payload)
        return True
    except Exception:
        logger.warning("cache: save_desk_venue failed to persist to disk", exc_info=True)
        return False


def load_desk_venue() -> dict:
    """Missing is normal and silent; unreadable is not (AGENTS.md 6.3).

    Corruption and a missing file both fall back to the ``NOVA_BROKER``
    bootstrap venue, which can move a settled Sim desk to IBKR. Only one of
    those is expected, so the other must say so in the log rather than look
    like a first run.
    """
    try:
        with open(_cache.DESK_VENUE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning(
            "cache: desk venue file at %s is unreadable -- falling back to the "
            "NOVA_BROKER bootstrap venue (the desk stays disarmed either way)",
            _cache.DESK_VENUE_FILE,
            exc_info=True,
        )
        return {}


def save_chart_drawings(payload: dict) -> None:
    try:
        os.makedirs(_cache._CACHE_DIR, exist_ok=True)
        _cache._atomic_write(_cache.CHART_DRAWINGS_FILE, payload)
    except Exception:
        logger.warning("cache: save_chart_drawings failed to persist to disk", exc_info=True)


def load_chart_drawings() -> dict:
    try:
        with open(_cache.CHART_DRAWINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_hod_momo_blocklist(symbols: list[str]) -> None:
    """Owner: hod_momo. Invalidation: operator edit. schema_version stamped."""
    try:
        os.makedirs(_cache._CACHE_DIR, exist_ok=True)
        _cache._atomic_write(
            _cache.HOD_MOMO_BLOCKLIST_FILE,
            stamp_schema({"symbols": symbols}, HOD_MOMO_BLOCKLIST_SCHEMA_VERSION),
        )
    except Exception:
        logger.warning("cache: save_hod_momo_blocklist failed to persist to disk", exc_info=True)


def load_hod_momo_blocklist() -> list[str]:
    try:
        with open(_cache.HOD_MOMO_BLOCKLIST_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return []
        accepted = accept_schema(
            data, HOD_MOMO_BLOCKLIST_SCHEMA_VERSION, name="hod-momo-blocklist",
        )
        if accepted is None:
            return []
        raw = accepted.get("symbols", [])
        if not isinstance(raw, list):
            return []
        return [str(s) for s in raw]
    except Exception:
        return []


def load_large_cap_fired() -> dict[str, str]:
    data = _cache._read_dated_json("large_cap", _cache._session_date_et())
    if data.get("date") != _cache._session_date_et():
        return {}
    raw = data.get("fired_today")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def save_large_cap_fired(fired: dict[str, str]) -> None:
    try:
        existing = _cache._read_dated_json("large_cap", _cache._session_date_et())
        rows = existing.get("large_cap")
        _cache._write_dated(
            "large_cap",
            _cache._session_date_et(),
            {
                "date": _cache._session_date_et(),
                "ts": existing.get("ts", 0.0),
                "large_cap": rows if isinstance(rows, list) else [],
                "fired_today": fired,
            },
        )
    except Exception:
        logger.warning("cache: save_large_cap_fired failed to persist to disk", exc_info=True)
