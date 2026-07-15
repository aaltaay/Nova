"""Optional Sentry init — no-op when SENTRY_DSN is unset."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_sentry_enabled: bool = False


def sentry_enabled() -> bool:
    return _sentry_enabled


def init_sentry() -> bool:
    """Initialize sentry-sdk when SENTRY_DSN is set. Returns True if enabled."""
    global _sentry_enabled
    dsn = (os.environ.get("SENTRY_DSN") or "").strip()
    if not dsn:
        _sentry_enabled = False
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        traces = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE") or "0")
        sentry_sdk.init(
            dsn=dsn,
            integrations=[
                StarletteIntegration(transaction_style="endpoint"),
                FastApiIntegration(transaction_style="endpoint"),
            ],
            traces_sample_rate=max(0.0, min(1.0, traces)),
            send_default_pii=False,
        )
        _sentry_enabled = True
        logger.info("Sentry enabled (traces_sample_rate=%.3f)", traces)
        return True
    except Exception:
        _sentry_enabled = False
        logger.exception("Sentry init failed — continuing without telemetry")
        return False
