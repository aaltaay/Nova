"""POST JSON payloads to arbitrary webhook URLs."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from alerts.webhook_url import validate_webhook_url
from constants import ALERTS_HTTP_TIMEOUT_SEC

logger = logging.getLogger(__name__)


def _redact_url(url: str) -> str:
    if len(url) <= 12:
        return "***"
    return f"***{url[-8:]}"


def send_webhook(
    url: str,
    payload: dict,
    *,
    timeout: float = ALERTS_HTTP_TIMEOUT_SEC,
) -> tuple[bool, str | None]:
    """POST JSON to a generic webhook. Returns (ok, error_message)."""
    try:
        url = validate_webhook_url(url)
    except ValueError as exc:
        return False, str(exc)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "Nova-Alerts/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status >= 400:
                msg = f"Webhook HTTP {resp.status}"
                logger.warning("Generic webhook failed (%s): %s", _redact_url(url), msg)
                return False, msg
            return True, None
    except urllib.error.HTTPError as exc:
        msg = f"Webhook HTTP {exc.code}"
        logger.warning("Generic webhook HTTP error (%s): %s", _redact_url(url), msg)
        return False, msg
    except Exception as exc:
        msg = "Webhook request failed"
        logger.warning(
            "Generic webhook error (%s): %s",
            _redact_url(url),
            str(exc).replace(url, _redact_url(url)),
        )
        return False, msg
