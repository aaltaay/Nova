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

from dotenv import load_dotenv, set_key
from fastapi import APIRouter
from pydantic import BaseModel

import alpaca as _alpaca
import exchanges as _exchanges
from alpaca import _env, _get_discovery_provider, _get_feed, _set_discovery_provider, _set_feed
from constants import (
    DATA_FEED_DEFAULT,
    DATA_FEED_OPTIONS,
    DISCOVERY_PROVIDER_DEFAULT,
    DISCOVERY_PROVIDER_OPTIONS,
)
from paths import env_file_path

router = APIRouter(tags=["health"])


def _m():
    """Lazy accessor for main.py to avoid circular imports at load time."""
    import main as _main
    return _main


# ── Request models ────────────────────────────────────────────────────────────

class ConfigUpdate(BaseModel):
    api_key: str
    api_secret: str
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
def health_check():
    m = _m()
    return {
        **m._cached_health,
        "data_feed": _get_feed(),
        "feed_fell_back": _alpaca._feed_fell_back,
    }


@router.get("/api/config")
def get_config():
    m = _m()
    from ibkr import client as _ibkr_client
    return {
        "api_key": _env("APCA_API_KEY_ID") or "",
        "api_secret": _env("APCA_API_SECRET_KEY") or "",
        "base_url": _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets",
        "data_feed": _get_feed(),
        "data_feed_options": list(DATA_FEED_OPTIONS),
        "discovery_provider": _get_discovery_provider(),
        "discovery_provider_options": list(DISCOVERY_PROVIDER_OPTIONS),
        "ibkr_connected": _ibkr_client.is_connected(),
    }


@router.post("/api/config")
def update_config(config: ConfigUpdate):
    m = _m()
    env_path = str(env_file_path())
    os.makedirs(os.path.dirname(env_path) or ".", exist_ok=True)
    set_key(env_path, "APCA_API_KEY_ID", config.api_key)
    set_key(env_path, "APCA_API_SECRET_KEY", config.api_secret)
    set_key(env_path, "APCA_API_BASE_URL", config.base_url)
    set_key(env_path, "ALPACA_DATA_FEED", config.data_feed)
    set_key(env_path, "NOVA_DISCOVERY_PROVIDER", config.discovery_provider)
    load_dotenv(env_path, override=True)
    _set_feed(config.data_feed)
    _set_discovery_provider(config.discovery_provider)
    m.reset_scan_caches()
    _exchanges.clear()
    m._ws_mark_resub()
    return {
        "status": "success",
        "data_feed": _get_feed(),
        "discovery_provider": _get_discovery_provider(),
    }


@router.get("/api/mode")
def get_mode():
    m = _m()
    return {
        "mode": m._current_mode,
        "health": m._cached_health,
        "last_gapper_scan": m._gapper_cache_ts,
        "last_gainer_scan": m._gainer_cache_ts,
    }
