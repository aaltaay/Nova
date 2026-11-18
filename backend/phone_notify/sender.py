"""Send one notification to every subscribed phone, through each phone's push service.

The only place this package talks to the network: one https POST per phone to the address its browser
gave (a host on the short list in ``constants_phone_notify``), the body scrambled for that phone alone
(``webpush.encrypt``). The push service carries the message and cannot read it.

A push service that answers "gone" (404 / 410) means the phone dropped its subscription: the phone is taken
off the list. Any other refusal is kept as the last result and logged with the service's status, never the
phone's address or keys.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

from phone_notify import store, vapid, webpush
from phone_notify.constants_phone_notify import (
    PHONE_NOTIFY_RECORD_SIZE,
    PHONE_NOTIFY_SEND_TIMEOUT_SEC,
    PHONE_NOTIFY_SUBJECT_DEFAULT,
    PHONE_NOTIFY_SUBJECT_ENV,
    PHONE_NOTIFY_TOKEN_SEC,
)

logger = logging.getLogger(__name__)
_GONE = (404, 410)


def _subject() -> str:
    import os

    return (os.environ.get(PHONE_NOTIFY_SUBJECT_ENV) or "").strip() or PHONE_NOTIFY_SUBJECT_DEFAULT


def _post(endpoint: str, body: bytes, headers: dict[str, str]) -> int:
    """One POST to a push service; its status. Split out so a test sends nothing."""
    return requests.post(endpoint, data=body, headers=headers, timeout=PHONE_NOTIFY_SEND_TIMEOUT_SEC,
                         allow_redirects=False).status_code


def _why(status: int) -> str:
    if status in (401, 403):
        return f"the push service refused this PC's sending key ({status}); turn Notify this phone off and on"
    if status == 413:
        return "the push service said the notification was too long (413)"
    if status == 429:
        return "the push service said too many were sent; it will take them again shortly (429)"
    return f"the push service answered {status}"


def deliver(message: dict[str, Any], *, ttl: int, now: float | None = None) -> dict[str, Any]:
    """Send ``message`` (``{title, body, tag, hash}``) to each subscribed phone.

    Returns ``{ok, sent, failed, gone, error}``: ``ok`` when at least one phone's push service took it.
    Never raises: a notification that cannot go is a result, not an error for the desk's producers."""
    ts = time.time() if now is None else now
    key = vapid.private_key()
    phones = store.devices()
    if key is None:
        return {"ok": False, "sent": 0, "failed": 0, "gone": 0, "error": "this PC has no sending key yet"}
    if not phones:
        return {"ok": False, "sent": 0, "failed": 0, "gone": 0, "error": "no phone is subscribed"}
    payload = json.dumps({**message, "at": int(ts)}, separators=(",", ":")).encode("utf-8")
    sent = failed = gone = 0
    error: str | None = None
    for phone in phones:
        try:
            body = webpush.encrypt(payload, webpush.b64url_decode(phone["p256dh"]), webpush.b64url_decode(phone["auth"]),
                                   record_size=PHONE_NOTIFY_RECORD_SIZE)
            status = _post(phone["endpoint"], body, {
                "TTL": str(int(ttl)),
                "Urgency": "high",
                "Content-Encoding": "aes128gcm",
                "Content-Type": "application/octet-stream",
                "Authorization": webpush.vapid_authorization(
                    phone["endpoint"], key, subject=_subject(), expires_at=int(ts) + PHONE_NOTIFY_TOKEN_SEC),
            })
        except (requests.RequestException, ValueError) as exc:
            failed += 1
            error = f"the push service could not be reached ({type(exc).__name__})"
            logger.warning("PHONE NOTIFY: phone %s not notified: %s", phone["id"], error)
            continue
        if 200 <= status < 300:
            sent += 1
        elif status in _GONE:
            gone += 1
            store.remove_device(phone["endpoint"])
            error = "the phone dropped its subscription; turn Notify this phone on again"
            logger.warning("PHONE NOTIFY: phone %s is gone at its push service (%s); taken off the list", phone["id"], status)
        else:
            failed += 1
            error = _why(status)
            logger.warning("PHONE NOTIFY: phone %s not notified: %s", phone["id"], error)
    return {"ok": sent > 0, "sent": sent, "failed": failed, "gone": gone, "error": None if sent else error}
