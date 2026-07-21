"""Auxiliary integration status for the header (not price-feed chips)."""
from __future__ import annotations

import os
from typing import Any


def _chip(status: str, detail: str = "") -> dict[str, str]:
    return {"status": status, "detail": detail}


def build_integrations_status() -> dict[str, Any]:
    """Snapshot of third-party / aux APIs Nova may call.

    Status vocabulary: ok | off | error | unknown
    Never implies a chip is the live price feed.
    """
    from alpaca import _alpaca_headers, _env
    from ibkr import client as _ibkr_client
    from news.ai_reasoning import _is_enabled as lincoln_enabled
    from runtime_state import get_runtime_state

    state = get_runtime_state()
    health = state.cached_health or {}
    h_status = str(health.get("status") or "")
    keys = bool(_alpaca_headers())

    if not keys:
        alpaca = _chip("off", "APCA keys not configured")
    elif h_status == "connected":
        lat = health.get("latency_ms")
        alpaca = _chip(
            "ok",
            f"Account ping ok{f' · {lat}ms' if lat else ''} — news/listing/RVOL aux, not live prices",
        )
    elif h_status in ("error", "disconnected"):
        alpaca = _chip("error", str(health.get("message") or h_status))
    else:
        alpaca = _chip("unknown", "Alpaca health not checked yet")

    if _ibkr_client.is_connected():
        ibkr = _chip("ok", "Gateway API connected — live prices when discovery=ibkr")
    elif (_env("IBKR_ENABLED") or "").strip().lower() in ("1", "true", "yes"):
        ibkr = _chip("error", "IBKR enabled but Gateway offline")
    else:
        ibkr = _chip("off", "IBKR_ENABLED not set")

    openai_key = bool(os.environ.get("OPENAI_API_KEY"))
    if not lincoln_enabled():
        openai = _chip(
            "off",
            "Lincoln AI off (LINCOLN_AI_ENABLED) — no OpenAI calls",
        )
    elif not openai_key:
        openai = _chip("error", "Lincoln on but OPENAI_API_KEY missing")
    else:
        openai = _chip("ok", "Lincoln enabled — OpenAI key present (no live ping)")

    try:
        import yfinance  # noqa: F401

        yf = _chip("ok", "yfinance importable (HOD avg volume / fundamentals)")
    except Exception as exc:
        yf = _chip("error", f"yfinance unavailable: {exc}")

    # Light R2/config probe only — never walk cold archive on every health poll.
    try:
        from archive.r2 import r2_enabled, r2_status

        st = r2_status()
        if not r2_enabled():
            archive = _chip("off", "Archive R2 disabled")
        elif st.get("configured"):
            archive = _chip("ok", str(st.get("message") or "R2 configured"))
        else:
            archive = _chip("error", str(st.get("message") or "R2 not configured"))
    except Exception as exc:
        archive = _chip("unknown", f"archive probe failed: {exc}")

    return {
        "alpaca": alpaca,
        "ibkr": ibkr,
        "openai": openai,
        "yfinance": yf,
        "archive": archive,
    }


def health_with_integrations(cached: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach ``integrations`` to a cached health payload for scanner/header chips."""
    base = dict(cached or {})
    base["integrations"] = build_integrations_status()
    return base
