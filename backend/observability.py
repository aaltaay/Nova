"""Optional Sentry init -- no-op when SENTRY_DSN is unset."""
from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

_sentry_enabled: bool = False
_last_session_unusable_capture_mono: float = 0.0
_last_max_tickers_capture_mono: float = 0.0


def sentry_enabled() -> bool:
    return _sentry_enabled


def _resolve_environment() -> str:
    return (os.environ.get("SENTRY_ENVIRONMENT") or "local").strip() or "local"


def _resolve_release() -> str | None:
    explicit = (os.environ.get("SENTRY_RELEASE") or "").strip()
    if explicit:
        return explicit
    # Prefer short SHA when present (CI / desktop launcher); else omit.
    for key in ("GIT_COMMIT", "GITHUB_SHA", "NOVA_GIT_SHA"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw[:40]
    return None


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
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        from observability_filters import before_send

        traces = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE") or "0")
        environment = _resolve_environment()
        release = _resolve_release()
        init_kwargs: dict = {
            "dsn": dsn,
            "integrations": [
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
                StarletteIntegration(transaction_style="endpoint"),
                FastApiIntegration(transaction_style="endpoint"),
            ],
            "traces_sample_rate": max(0.0, min(1.0, traces)),
            "send_default_pii": False,
            "environment": environment,
            "before_send": before_send,
        }
        if release:
            init_kwargs["release"] = release
        sentry_sdk.init(**init_kwargs)
        _sentry_enabled = True
        logger.info(
            "Sentry enabled (environment=%s release=%s traces_sample_rate=%.3f)",
            environment,
            release or "-",
            traces,
        )
        return True
    except Exception:
        _sentry_enabled = False
        logger.exception("Sentry init failed -- continuing without telemetry")
        return False


def capture_session_unusable(*, code: int | None = None, detail: str = "") -> None:
    """Ops-once: one fingerprinted Sentry event per unusable episode (cooldown)."""
    global _last_session_unusable_capture_mono
    if not _sentry_enabled:
        return
    try:
        from constants import SENTRY_SESSION_UNUSABLE_COOLDOWN_SEC
    except Exception:
        cooldown = 300.0
    else:
        cooldown = float(SENTRY_SESSION_UNUSABLE_COOLDOWN_SEC)
    now = time.monotonic()
    if (now - _last_session_unusable_capture_mono) < cooldown:
        return
    _last_session_unusable_capture_mono = now
    try:
        import sentry_sdk

        if not sentry_sdk.is_initialized():
            return
        with sentry_sdk.push_scope() as scope:
            scope.fingerprint = ["ibkr-session-unusable"]
            scope.set_tag("subsystem", "ibkr_session")
            if code is not None:
                scope.set_tag("ibkr_error_code", str(code))
            if detail:
                scope.set_extra("detail", detail[:500])
            sentry_sdk.capture_message(
                "ibkr.session.unusable",
                level="error",
            )
    except Exception:
        logger.debug("Sentry session_unusable capture skipped", exc_info=True)


def capture_max_tickers(*, detail: str = "") -> None:
    """Ops-once fingerprint for Error 101 capacity oversubscription."""
    global _last_max_tickers_capture_mono
    if not _sentry_enabled:
        return
    try:
        from constants import SENTRY_SESSION_UNUSABLE_COOLDOWN_SEC
    except Exception:
        cooldown = 300.0
    else:
        cooldown = float(SENTRY_SESSION_UNUSABLE_COOLDOWN_SEC)
    now = time.monotonic()
    if (now - _last_max_tickers_capture_mono) < cooldown:
        return
    _last_max_tickers_capture_mono = now
    try:
        import sentry_sdk

        if not sentry_sdk.is_initialized():
            return
        with sentry_sdk.push_scope() as scope:
            scope.fingerprint = ["ibkr-capacity-max-tickers"]
            scope.set_tag("subsystem", "ibkr_capacity")
            if detail:
                scope.set_extra("detail", detail[:500])
            sentry_sdk.capture_message(
                "ibkr.capacity.max_tickers",
                level="error",
            )
    except Exception:
        logger.debug("Sentry max_tickers capture skipped", exc_info=True)
