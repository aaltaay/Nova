"""The phone's one unlocked session.

Owner: this module. State: one random token and when it ends, in memory only -- a backend restart
locks the phone, and so does a second unlock (the newer one replaces it: one phone at a time).
The token is what a correct PIN buys; every phone write carries it (``PHONE_SESSION_HEADER``).
"""
from __future__ import annotations

import hmac
import secrets
import time

from phone.constants_phone import PHONE_SESSION_SEC

_token: str | None = None
_expires_at = 0.0


def open_session(*, now: float | None = None) -> tuple[str, float]:
    """A fresh session, replacing any other: ``(token, when it ends, epoch s)``."""
    global _token, _expires_at
    now = time.time() if now is None else now
    _token = secrets.token_urlsafe(32)
    _expires_at = now + PHONE_SESSION_SEC
    return _token, _expires_at


def valid(token: str | None, *, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    if not token or _token is None or now >= _expires_at:
        return False
    return hmac.compare_digest(str(token), _token)


def expires_at(token: str | None, *, now: float | None = None) -> float | None:
    """When *token*'s session ends, or None when it is not the open one."""
    return _expires_at if valid(token, now=now) else None


def close() -> None:
    global _token, _expires_at
    _token = None
    _expires_at = 0.0
