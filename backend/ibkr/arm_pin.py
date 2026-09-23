"""The operator's Live arm PIN: its stored hash, the check, and the lockout.

Owner: this module (``ibkr.safety.arm`` is the only caller of ``check``).
Stored: ``NOVA_LIVE_ARM_PIN_HASH`` in ``.env`` as
``pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>`` -- never the PIN itself,
never in the repo. ``tools/set_live_arm_pin.py`` writes it from a hidden
terminal prompt. The file is re-read on every check so a PIN set while the API
runs works at once; a process-environment value wins, like every other key.
Invalidation: the operator sets a new hash; the failure count lives in memory
and resets on a correct PIN or a restart.

Why the backend checks it (operator decision 2026-09-23): the PIN used to be a
constant in the public frontend source, compared in the browser, while
``POST /api/ibkr/arm`` armed Live for any local caller. A bot or an agent on
this machine could arm Live without the operator. Now it cannot without the PIN.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time

from constants_ibkr import (
    ARM_PIN_HASH_ENV,
    ARM_PIN_LENGTH,
    ARM_PIN_LOCKOUT_SEC,
    ARM_PIN_MAX_FAILURES,
    ARM_PIN_PBKDF2_ITERATIONS,
)

logger = logging.getLogger(__name__)

_SCHEME = "pbkdf2_sha256"

# Wrong PINs in a row, and when the lockout they earned ends.
_failures = 0
_locked_until = 0.0


def hash_pin(pin: str, *, iterations: int = ARM_PIN_PBKDF2_ITERATIONS) -> str:
    """The stored form of *pin*: salted PBKDF2, safe to keep in ``.env``."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, iterations)
    return f"{_SCHEME}${iterations}${salt.hex()}${digest.hex()}"


def valid_pin_shape(pin: str) -> bool:
    return len(pin) == ARM_PIN_LENGTH and pin.isdigit()


def stored_hash() -> str | None:
    """The configured hash, or ``None`` when no Live PIN is set."""
    value = (os.environ.get(ARM_PIN_HASH_ENV) or "").strip()
    if value:
        return value
    from dotenv import dotenv_values

    from paths import env_file_path

    try:
        value = str(dotenv_values(env_file_path()).get(ARM_PIN_HASH_ENV) or "").strip()
    except OSError:
        logger.warning("ARM: could not read .env for the Live PIN hash", exc_info=True)
        return None
    return value or None


def pin_is_set() -> bool:
    return _parse(stored_hash()) is not None


def _parse(stored: str | None) -> tuple[int, bytes, bytes] | None:
    try:
        scheme, iterations, salt, digest = (stored or "").split("$")
        if scheme != _SCHEME:
            return None
        return int(iterations), bytes.fromhex(salt), bytes.fromhex(digest)
    except ValueError:
        return None


def check(pin: str | None, *, now: float | None = None) -> tuple[str | None, str]:
    """``(None, "")`` when *pin* is the operator's; else ``(code, reason)``."""
    global _failures, _locked_until
    now = time.time() if now is None else now
    if now < _locked_until:
        return "ARM_PIN_LOCKED", (
            f"Too many wrong PINs -- Live arming is locked for "
            f"{int(_locked_until - now) + 1} s"
        )
    if not pin:
        return "ARM_PIN_REQUIRED", "Live needs your PIN to unlock"
    parsed = _parse(stored_hash())
    if parsed is None:
        return "ARM_PIN_NOT_SET", (
            "No Live PIN is set -- run  py -3 tools/set_live_arm_pin.py  "
            "on the desk PC, then unlock again"
        )
    iterations, salt, digest = parsed
    candidate = hashlib.pbkdf2_hmac("sha256", str(pin).encode(), salt, iterations)
    if hmac.compare_digest(candidate, digest):
        _failures = 0
        return None, ""
    _failures += 1
    logger.warning("ARM: wrong Live PIN (%d in a row)", _failures)
    if _failures >= ARM_PIN_MAX_FAILURES:
        _failures = 0
        _locked_until = now + ARM_PIN_LOCKOUT_SEC
        return "ARM_PIN_LOCKED", (
            f"Too many wrong PINs -- Live arming is locked for {int(ARM_PIN_LOCKOUT_SEC)} s"
        )
    return "ARM_PIN_INVALID", "Wrong PIN"


def reset_for_tests() -> None:
    global _failures, _locked_until
    _failures = 0
    _locked_until = 0.0
