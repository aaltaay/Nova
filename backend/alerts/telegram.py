"""Send alerts via Telegram Bot API sendMessage."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from constants import ALERTS_HTTP_TIMEOUT_SEC

logger = logging.getLogger(__name__)


def _redact_token(token: str) -> str:
    if len(token) <= 8:
        return "***"
    return f"***{token[-4:]}"


def send_telegram(
    bot_token: str,
    chat_id: str,
    text: str,
    *,
    timeout: float = ALERTS_HTTP_TIMEOUT_SEC,
) -> tuple[bool, str | None]:
    """POST sendMessage. Returns (ok, error_message). Never logs token."""
    base = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        base,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Nova-Alerts/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if resp.status >= 400:
                msg = f"Telegram HTTP {resp.status}"
                logger.warning("Telegram send failed (token=%s): %s", _redact_token(bot_token), msg)
                return False, msg
            try:
                parsed = json.loads(raw)
                if not parsed.get("ok"):
                    desc = parsed.get("description") or "unknown Telegram error"
                    logger.warning("Telegram API error (token=%s): %s", _redact_token(bot_token), desc)
                    return False, desc
            except json.JSONDecodeError:
                pass
            return True, None
    except urllib.error.HTTPError as exc:
        msg = f"Telegram HTTP {exc.code}"
        logger.warning("Telegram HTTP error (token=%s): %s", _redact_token(bot_token), msg)
        return False, msg
    except Exception as exc:
        msg = str(exc)
        logger.warning("Telegram error (token=%s): %s", _redact_token(bot_token), msg)
        return False, msg
