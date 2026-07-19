"""POST to Discord incoming webhooks."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from alerts.webhook_url import validate_webhook_url
from constants import ALERTS_DISCORD_USERNAME, ALERTS_HTTP_TIMEOUT_SEC

logger = logging.getLogger(__name__)


def _redact_url(url: str) -> str:
    """Never log full webhook URLs."""
    if len(url) <= 12:
        return "***"
    return f"***{url[-8:]}"


def send_discord(webhook_url: str, body: dict, *, timeout: float = ALERTS_HTTP_TIMEOUT_SEC) -> tuple[bool, str | None]:
    """POST embed/content to Discord. Returns (ok, error_message)."""
    try:
        webhook_url = validate_webhook_url(webhook_url)
    except ValueError as exc:
        return False, str(exc)
    payload = dict(body)
    payload.setdefault("username", ALERTS_DISCORD_USERNAME)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "Nova-Alerts/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status >= 400:
                msg = f"Discord HTTP {resp.status}"
                logger.warning("Discord webhook failed (%s): %s", _redact_url(webhook_url), msg)
                return False, msg
            return True, None
    except urllib.error.HTTPError as exc:
        msg = f"Discord HTTP {exc.code}"
        logger.warning("Discord webhook HTTP error (%s): %s", _redact_url(webhook_url), msg)
        return False, msg
    except Exception as exc:
        # Never return raw exception text — it can embed the full webhook URL.
        msg = "Discord request failed"
        logger.warning(
            "Discord webhook error (%s): %s",
            _redact_url(webhook_url),
            str(exc).replace(webhook_url, _redact_url(webhook_url)),
        )
        return False, msg
