"""Runtime-tunable Large Cap lease filters (ADR 014 Step 8).

Mirrors the ``hod_momo_admin.py`` config pattern: ``GET``/``POST
/api/large-cap/config`` reads/writes a small JSON file with a
``schema_version``, refusing loud on an unknown version rather than silently
ignoring it (see ``.cursor/rules/persisted-state.mdc``).

Owner: this module (the only reader/writer of ``LARGE_CAP_CONFIG_FILE``).
Invalidation trigger: process start, or an explicit ``POST`` -- which also
changes the ``LeaseSpec`` returned by ``scanner_session.desired_leases()``,
so the next manager-loop reconcile resubscribes with the new filters.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

from constants import (
    LARGE_CAP_ABOVE_VOLUME_DEFAULT,
    LARGE_CAP_CONFIG_SCHEMA_VERSION,
    LARGE_CAP_MARKET_CAP_ABOVE_MM_DEFAULT,
    LARGE_CAP_SCAN_CODE,
    LARGE_CAP_SCORE_WEIGHTS,
    LARGE_CAP_STOCK_TYPE_FILTER,
)

logger = logging.getLogger(__name__)


@dataclass
class LargeCapConfig:
    market_cap_above: float = LARGE_CAP_MARKET_CAP_ABOVE_MM_DEFAULT  # millions of USD
    above_volume: int = LARGE_CAP_ABOVE_VOLUME_DEFAULT
    scan_code: str = LARGE_CAP_SCAN_CODE
    stock_type_filter: str = LARGE_CAP_STOCK_TYPE_FILTER
    score_weights: dict[str, float] = field(default_factory=lambda: dict(LARGE_CAP_SCORE_WEIGHTS))


_config = LargeCapConfig()
_loaded = False


def _load() -> None:
    global _config, _loaded
    if _loaded:
        return
    _loaded = True
    import cache as _cache

    data = _cache.load_large_cap_config()
    if not data:
        return
    version = int(data.get("schema_version") or 0)
    if version != LARGE_CAP_CONFIG_SCHEMA_VERSION:
        logger.warning(
            "large_cap_admin: refusing config with unknown schema_version=%s "
            "(expected %s) -- keeping defaults",
            version, LARGE_CAP_CONFIG_SCHEMA_VERSION,
        )
        return
    _config = LargeCapConfig(
        market_cap_above=float(data.get("market_cap_above", _config.market_cap_above)),
        above_volume=int(data.get("above_volume", _config.above_volume)),
        scan_code=str(data.get("scan_code", _config.scan_code)),
        stock_type_filter=str(data.get("stock_type_filter", _config.stock_type_filter)),
        score_weights=dict(data.get("score_weights") or _config.score_weights),
    )


def get_config() -> dict:
    """Full config for the GET endpoint."""
    _load()
    return asdict(_config)


def get_large_cap_filters() -> dict:
    """Read-only filter view for ``scanner_session._large_cap_lease()``."""
    _load()
    return {
        "scan_code": _config.scan_code,
        "market_cap_above": _config.market_cap_above,
        "above_volume": _config.above_volume,
        "stock_type_filter": _config.stock_type_filter,
    }


def get_score_weights() -> dict[str, float]:
    _load()
    return dict(_config.score_weights)


def update_config(patch: dict) -> dict:
    """Validate + persist a config patch. Raises ``ValueError`` on bad input."""
    _load()
    global _config
    next_config = LargeCapConfig(
        market_cap_above=float(patch.get("market_cap_above", _config.market_cap_above)),
        above_volume=int(patch.get("above_volume", _config.above_volume)),
        scan_code=str(patch.get("scan_code", _config.scan_code)),
        stock_type_filter=str(patch.get("stock_type_filter", _config.stock_type_filter)),
        score_weights=dict(patch.get("score_weights") or _config.score_weights),
    )
    if next_config.market_cap_above <= 0:
        raise ValueError("market_cap_above must be positive (millions of USD)")
    if next_config.above_volume < 0:
        raise ValueError("above_volume must be >= 0")
    if not next_config.scan_code:
        raise ValueError("scan_code must not be empty")
    _config = next_config
    _save()
    return asdict(_config)


def _save() -> None:
    import cache as _cache

    payload = {"schema_version": LARGE_CAP_CONFIG_SCHEMA_VERSION, **asdict(_config)}
    _cache.save_large_cap_config(payload)


def reset_for_testing() -> None:
    """Test-only: force a clean in-memory default without touching disk."""
    global _config, _loaded
    _config = LargeCapConfig()
    _loaded = True
