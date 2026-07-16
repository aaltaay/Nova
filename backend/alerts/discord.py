"""POST to Discord incoming webhooks."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from constants import ALERTS_DISCORD_USERNAME, ALERTS_HTTP_TIMEOUT_SEC

logger = logging.getLogger(__name__)


def _redact_url(url: str) -> str:
    """Never log full webhook URLs."""
    if len(url) <= 12:
        return "***"
    return f"***{url[-8:]}"


def send_discord(webhook_url: str, body: dict, *, timeout: float = ALERTS_HTTP_TIMEOUT_SEC) -> tuple[bool, str | None]:
    """POST embed/content to Discord. Returns (ok, error_message)."""
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
        msg = str(exc)
        logger.warning("Discord webhook error (%s): %s", _redact_url(webhook_url), msg)
        return False, msg
