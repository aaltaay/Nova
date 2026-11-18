"""``/api/phone/notify`` (ADR 070, amendment 2026-11-18): the phone's notification settings.

Under the phone's own door: a read needs nothing (as every read), a write needs the PIN's session
(``phone.routes.require_session``) -- the one prefix another device may write to. Nothing here trades or
arms: it keeps what the operator chose and which phones to notify.

  GET  /api/phone/notify               the settings, the PC's public key, the subscribed phones' ids
  PUT  /api/phone/notify/settings      replace the settings (the whole of them)
  POST /api/phone/notify/subscribe     {endpoint, keys: {p256dh, auth}}: notify this phone
  POST /api/phone/notify/unsubscribe   {endpoint}: stop notifying it
  POST /api/phone/notify/test          send one notification now

Every write answers with the settings as they now stand (the GET's shape), so the screen shows what was kept.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from phone.routes import require_session
from phone_notify import hooks, store, vapid
from phone_notify.constants_phone_notify import (
    NOTIFY_API_PREFIX,
    NOTIFY_ENDPOINT_MAX_CHARS,
    NOTIFY_SCHEMA_VERSION,
    REASON_BAD_ADDRESS,
    REASON_BAD_SETTINGS,
    REASON_NO_DEVICE,
    REASON_NO_KEY,
    REASON_SEND_FAILED,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix=NOTIFY_API_PREFIX, tags=["phone"])


class Keys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=256)
    auth: str = Field(min_length=1, max_length=64)


class Subscription(BaseModel):
    endpoint: str = Field(min_length=1, max_length=NOTIFY_ENDPOINT_MAX_CHARS)
    keys: Keys


class Address(BaseModel):
    endpoint: str = Field(min_length=1, max_length=NOTIFY_ENDPOINT_MAX_CHARS)


def _refuse(code: str, text: str, status: int) -> HTTPException:
    return HTTPException(status_code=status, detail={"reason": code, "error": text})


def view() -> dict[str, Any]:
    """What the phone's screens read. The public key is made by the first subscribe, so it is null before it."""
    doc = store.load()
    return {
        "schema_version": NOTIFY_SCHEMA_VERSION,
        "available": True,
        "why_unavailable": None,
        "public_key": vapid.public_key_b64(),
        "settings": doc["settings"],
        "device_ids": [d["id"] for d in doc["devices"]],
        "last_sent": hooks.last_sent(),
    }


@router.get("")
def get_notify() -> dict[str, Any]:
    return view()


@router.post("/key")
def make_key(_token: str = Depends(require_session)) -> dict[str, Any]:
    """Make this PC's sending key when it has none (it is written to ``.env``): a phone subscribes to its public half."""
    _key, error = vapid.ensure()
    if error:
        raise _refuse(REASON_NO_KEY, error, 409)
    return view()


@router.put("/settings")
def put_settings(body: dict[str, Any], _token: str = Depends(require_session)) -> dict[str, Any]:
    _kept, error = store.save_settings(body)
    if error:
        raise _refuse(REASON_BAD_SETTINGS, f"{error} Nothing was changed.", 422)
    return view()


@router.post("/subscribe")
def subscribe(body: Subscription, _token: str = Depends(require_session)) -> dict[str, Any]:
    if vapid.private_key() is None:
        raise _refuse(REASON_NO_KEY, "This PC has no sending key yet. Turn Notify this phone on again.", 409)
    error = store.add_device(body.endpoint, body.keys.p256dh, body.keys.auth)
    if error:
        raise _refuse(REASON_BAD_ADDRESS, f"{error} Nothing was turned on.", 422)
    logger.warning("PHONE NOTIFY: phone %s subscribed", store.device_id(body.endpoint))
    return view()


@router.post("/unsubscribe")
def unsubscribe(body: Address, _token: str = Depends(require_session)) -> dict[str, Any]:
    if store.remove_device(body.endpoint):
        logger.warning("PHONE NOTIFY: phone %s unsubscribed", store.device_id(body.endpoint))
    return view()


@router.post("/test")
def send_test(_token: str = Depends(require_session)) -> dict[str, Any]:
    if not store.devices():
        raise _refuse(REASON_NO_DEVICE, "No phone is subscribed. Turn Notify this phone on first.", 409)
    result = hooks.send_test()
    if not result["ok"]:
        raise _refuse(REASON_SEND_FAILED, f"Not sent: {result['error']}.", 502)
    phones = result["sent"]
    return {**view(), "text": f"Sent to {phones} phone{'' if phones == 1 else 's'}. It should arrive in a few seconds."}
