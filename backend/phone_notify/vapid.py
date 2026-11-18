"""The PC's sending key: the P-256 pair a phone subscribes to and every push is signed with (RFC 8292).

Owner: this module. The private half is a secret, so it lives where the desk's secrets live -- one line of the
desk's ``.env`` (``NOVA_PHONE_PUSH_KEY``, AGENTS.md Invariant 3), read from the file each time so a key
written while the API runs is in force at once. It is never logged, never sent to a phone and never in the
operator cache. The public half is what a phone is given.

The backend writes the key itself, the first time a phone asks to subscribe (``ensure``): the operator is
not asked to run a tool. Replacing the line makes every subscribed phone's address useless; the phone's
Notifications screen subscribes again on its next "Notify this phone".
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec

from phone_notify import webpush
from phone_notify.constants_phone_notify import PHONE_NOTIFY_KEY_ENV

logger = logging.getLogger(__name__)
_lock = threading.Lock()


def _env_path() -> Path:
    from paths import env_file_path

    return env_file_path()


def _stored() -> str | None:
    """The key's line: the file first (a key written since the API started), else the process environment."""
    from dotenv import dotenv_values

    try:
        value = str(dotenv_values(_env_path()).get(PHONE_NOTIFY_KEY_ENV) or "").strip()
    except OSError:
        logger.warning("PHONE NOTIFY: could not read .env for the sending key", exc_info=True)
        value = ""
    return value or (os.environ.get(PHONE_NOTIFY_KEY_ENV) or "").strip() or None


def private_key() -> ec.EllipticCurvePrivateKey | None:
    """The sending key, or None when there is none yet or its line cannot be read as one."""
    stored = _stored()
    if not stored:
        return None
    try:
        return webpush.private_key_from_b64(stored)
    except ValueError:
        logger.warning("PHONE NOTIFY: %s in .env is not a sending key; notifications cannot be sent until the "
                       "line is removed (a new key is then made on the next subscribe)", PHONE_NOTIFY_KEY_ENV)
        return None


def public_key_b64() -> str | None:
    key = private_key()
    return webpush.b64url_encode(webpush.public_bytes(key.public_key())) if key is not None else None


def _write_line(value: str) -> None:
    """Add the key's line to ``.env``, every other line kept as it is; the old file or the new one, never half."""
    path = _env_path()
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    lines = [ln for ln in lines if not ln.strip().startswith(f"{PHONE_NOTIFY_KEY_ENV}=")]
    lines.append(f"{PHONE_NOTIFY_KEY_ENV}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def ensure() -> tuple[ec.EllipticCurvePrivateKey | None, str | None]:
    """The sending key, made and written to ``.env`` when there is none: ``(key, None)`` or ``(None, why)``.

    A line that is there but unreadable is left alone and said: overwriting it would silently cut off every
    phone subscribed to the key it was meant to hold."""
    with _lock:
        if _stored():
            key = private_key()
            if key is None:
                return None, (f"{PHONE_NOTIFY_KEY_ENV} in your PC's .env is not a sending key. Remove that line "
                              "and turn this on again.")
            return key, None
        key = webpush.new_private_key()
        try:
            _write_line(webpush.private_key_to_b64(key))
        except OSError as exc:
            logger.warning("PHONE NOTIFY: could not write the sending key to .env", exc_info=True)
            return None, f"Your PC could not save its sending key to .env ({type(exc).__name__}). Nothing was turned on."
        logger.warning("PHONE NOTIFY: made this PC's sending key (%s in .env)", PHONE_NOTIFY_KEY_ENV)
        return key, None
