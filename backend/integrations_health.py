"""Auxiliary integration status for the header (not price-feed chips)."""
from __future__ import annotations

import os
from typing import Any


def _chip(status: str, detail: str = "") -> dict[str, str]:
    return {"status": status, "detail": detail}


def build_integrations_status() -> dict[str, Any]:
    """Snapshot of third-party / aux APIs Nova may call.

    Status vocabulary: ok | off | error | unknown
    Never implies a chip is the live price feed. Alpaca is aux only and must
    not drive the top-level API chip (see health_status.mark_nova_process_health).
    """
    from alpaca import _alpaca_headers, _env
    from ibkr import client as _ibkr_client
    from news.ai_reasoning import _is_enabled as lincoln_enabled

    keys = bool(_alpaca_headers())
    if not keys:
        alpaca = _chip("off", "APCA keys not configured — news/listing aux unavailable")
    else:
        alpaca = _chip(
            "ok",
            "APCA keys present — news/listing/RVOL aux, not live prices or API health",
        )

    import loop_lag as _loop_lag

    if _loop_lag.ib_lag.wedged:
        ibkr = _chip("error", "IB loop wedged -- desk blocked (Gateway socket may still be up)")
    elif _ibkr_client.is_connected():
        ibkr = _chip("ok", "Gateway API connected -- live prices when discovery=ibkr")
    elif (_env("IBKR_ENABLED") or "").strip().lower() in ("1", "true", "yes"):
        ibkr = _chip("error", "IBKR enabled but Gateway offline")
    else:
        from paths import env_file_path

        env_path = env_file_path()
        # ADR 021: a process with no .env reads every key as unset -- say which
        # file is missing instead of blaming the key (2026-09-22, worktree API).
        ibkr = (
            _chip("off", "IBKR_ENABLED not set")
            if env_path.is_file()
            else _chip("error", f"no .env at {env_path} -- every integration reads as unset")
        )

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
