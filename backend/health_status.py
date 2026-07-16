"""Alpaca account health ping against the explicit runtime-state owner."""
from __future__ import annotations

import math
from datetime import datetime

import requests

from runtime_state import get_runtime_state


def set_health_broker_keys_missing() -> None:
    """Alpaca headers unavailable — avoid leaving /api/health stuck on 'loading'."""
    state = get_runtime_state()
    state.cached_health = {
        "status": "error",
        "latency_ms": 0,
        "message": (
            "Broker API keys are not set on this server. "
            "In Railway (Backend service → Variables), add APCA_API_KEY_ID and "
            "APCA_API_SECRET_KEY, then redeploy or restart. "
            "Until then, /api/health stays in this state instead of 'loading'."
        ),
    }


def ping_health(base_url: str, headers: dict) -> bool:
    state = get_runtime_state()
    start = datetime.now()
    try:
        r = requests.get(f"{base_url}/v2/account", headers=headers, timeout=5)
        latency = math.floor((datetime.now() - start).total_seconds() * 1000)
        if r.status_code == 200:
            state.cached_health = {"status": "connected", "latency_ms": latency}
            return True
        state.cached_health = {
            "status": "error",
            "latency_ms": latency,
            "message": f"Alpaca HTTP {r.status_code}: {(r.text or '')[:200]}",
        }
        return False
    except Exception as e:
        state.cached_health = {"status": "disconnected", "latency_ms": 0, "message": str(e)}
        return False
