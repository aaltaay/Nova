"""
Health, config, and mode REST routes.

Extracted from ``main.py`` — thin handlers with no blocking I/O.

Endpoints:
  GET  /
  GET  /api/health
  GET  /api/config
  POST /api/config
  GET  /api/mode
"""
from __future__ import annotations

import os
import time

from dotenv import load_dotenv, set_key
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import alpaca as _alpaca
import exchanges as _exchanges
import instance_identity
import loop_lag as _loop_lag
from alerts.channels_store import mask_secret
from alpaca import _env, _get_discovery_provider, _get_feed, _set_discovery_provider, _set_feed
from constants import (
    DATA_FEED_DEFAULT,
    DATA_FEED_OPTIONS,
    DISCOVERY_PROVIDER_DEFAULT,
    DISCOVERY_PROVIDER_OPTIONS,
)
from websocket import mark_resub
from paths import env_file_path
from runtime_state import get_runtime_state
from universe import reset_scan_caches

router = APIRouter(tags=["health"])


def _is_secret_placeholder(value: str | None) -> bool:
    """True when the client sent an empty or masked value (keep existing secret)."""
    if value is None:
        return True
    stripped = value.strip()
    if not stripped:
        return True
    return set(stripped) <= {"*"}


# ── Request models ────────────────────────────────────────────────────────────

class ConfigUpdate(BaseModel):
    api_key: str = ""
    api_secret: str = ""
    base_url: str
    data_feed: str = DATA_FEED_DEFAULT
    discovery_provider: str = DISCOVERY_PROVIDER_DEFAULT


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
def root():
    """Human-friendly root when someone opens the API host in a browser."""
    return {
        "service": "Nova API",
        "ok": True,
        "health": "/api/health",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "note": "REST routes live under /api/… Use /api/health to verify connectivity.",
    }


@router.get("/api/health")
async def health_check():
    """Full status — must never wait on IBKR bridges or the default thread pool.

    Kept ``async`` so Starlette parks this on AnyIO's own worker pool, never
    the default ``ThreadPoolExecutor`` scan_loop's ``run_coro`` waits use
    (see PROBLEM_LOG 2026-07-23 — those two pools were never actually shared,
    but this stays async so that remains true going forward).
    """
    from integrations_health import build_integrations_status
    from observability import sentry_enabled

    state = get_runtime_state()
    return {
        **state.cached_health,
        "market_data_source": _get_discovery_provider(),
        "data_feed": _get_feed(),
        "feed_fell_back": _alpaca._feed_fell_back,
        "sentry_enabled": sentry_enabled(),
        "integrations": build_integrations_status(),
        "loop_lag_ms": _loop_lag.snapshot(),
        **instance_identity.snapshot(),
    }


@router.get("/livez")
def liveness_check():
    """Minimal loop-liveness probe — no IBKR/cache/network dependency so a
    degraded broker session can never make this hang or error."""
    return {
        "status": "alive",
        "uptime_sec": round(time.time() - instance_identity.STARTED_AT, 1),
        **instance_identity.snapshot(),
    }


@router.get("/readyz")
def readiness_check():
    """Application readiness — bootstrap-complete + IBKR session state.

    Observability only: restart tooling gates on ``/api/health`` (see
    frontend/scripts/vite-nova-start-api.ts), not this endpoint, so a broker
    that is intentionally disabled or still reconnecting never blocks a
    healthy Alpaca-only restart.
    """
    from app_lifespan import is_bootstrap_complete
    from ibkr import client as _ibkr_client

    bootstrap_complete = is_bootstrap_complete()
    payload = {
        "ready": bootstrap_complete,
        "bootstrap_complete": bootstrap_complete,
        "ibkr": _ibkr_client.session_snapshot(),
        **instance_identity.snapshot(),
    }
    return JSONResponse(payload, status_code=200 if bootstrap_complete else 503)


@router.get("/api/config")
def get_config():
    from ibkr import client as _ibkr_client
    from ibkr import scanner_session as _scanner_session

    api_key = _env("APCA_API_KEY_ID") or ""
    api_secret = _env("APCA_API_SECRET_KEY") or ""
    return {
        # Never return plaintext broker secrets (SEC-001).
        "api_key_masked": mask_secret(api_key),
        "api_key_set": bool(api_key),
        "api_secret_masked": mask_secret(api_secret),
        "api_secret_set": bool(api_secret),
        "base_url": _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets",
        "data_feed": _get_feed(),
        "data_feed_options": list(DATA_FEED_OPTIONS),
        "discovery_provider": _get_discovery_provider(),
        "discovery_provider_options": list(DISCOVERY_PROVIDER_OPTIONS),
        "ibkr_connected": _ibkr_client.is_connected(),
        "scanner_persistent_enabled": _scanner_session.is_persistent_enabled(),
        "scanner_persistent_authoritative": _scanner_session.is_persistent_authoritative(),
    }


@router.post("/api/config")
def update_config(config: ConfigUpdate):
    env_path = str(env_file_path())
    os.makedirs(os.path.dirname(env_path) or ".", exist_ok=True)
    if not _is_secret_placeholder(config.api_key):
        set_key(env_path, "APCA_API_KEY_ID", config.api_key)
    if not _is_secret_placeholder(config.api_secret):
        set_key(env_path, "APCA_API_SECRET_KEY", config.api_secret)
    set_key(env_path, "APCA_API_BASE_URL", config.base_url)
    set_key(env_path, "ALPACA_DATA_FEED", config.data_feed)
    # Product lock: always persist IBKR — ignore client attempts to set alpaca.
    locked_discovery = DISCOVERY_PROVIDER_DEFAULT
    set_key(env_path, "NOVA_DISCOVERY_PROVIDER", locked_discovery)
    load_dotenv(env_path, override=True)
    _set_feed(config.data_feed)
    _set_discovery_provider(locked_discovery)
    reset_scan_caches()
    _exchanges.clear()
    mark_resub()
    return {
        "status": "success",
        "data_feed": _get_feed(),
        "discovery_provider": _get_discovery_provider(),
    }


@router.get("/api/mode")
def get_mode():
    state = get_runtime_state()
    return {
        "mode": state.current_mode,
        "health": state.cached_health,
        "last_gapper_scan": state.gapper_cache_ts,
        "last_gainer_scan": state.gainer_cache_ts,
    }
