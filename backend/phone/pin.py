"""The operator's phone PIN: its stored hash, the check, and the lockout.

Owner: this module (``phone.routes`` is the only caller of ``check``).
Stored: ``NOVA_PHONE_PIN_HASH`` in ``.env``, in the Live PIN's form (``ibkr.arm_pin``: salted PBKDF2,
never the PIN). ``tools/set_phone_pin.py`` writes it from a hidden prompt on the PC. The file is
re-read on every check, so a PIN set while the API runs works at once.
Invalidation: the operator sets a new hash. The failure count lives in memory, apart from the Live
PIN's, and resets on a correct PIN or a restart.
"""
from __future__ import annotations

import logging
import time

from ibkr import arm_pin
from phone.constants_phone import (
    PHONE_PIN_HASH_ENV,
    PHONE_PIN_INVALID,
    PHONE_PIN_LOCKED,
    PHONE_PIN_LOCKOUT_SEC,
    PHONE_PIN_MAX_FAILURES,
    PHONE_PIN_NOT_SET,
    PHONE_PIN_REQUIRED,
)

logger = logging.getLogger(__name__)

_failures = 0
_locked_until = 0.0


def pin_is_set() -> bool:
    return arm_pin.is_hash(arm_pin.read_hash(PHONE_PIN_HASH_ENV))


def check(pin: str | None, *, now: float | None = None) -> tuple[str | None, str]:
    """``(None, "")`` when *pin* is the operator's phone PIN; else ``(code, reason)``."""
    global _failures, _locked_until
    now = time.time() if now is None else now
    if now < _locked_until:
        return PHONE_PIN_LOCKED, f"Too many wrong PINs: the phone is locked for {int(_locked_until - now) + 1} s"
    if not pin:
        return PHONE_PIN_REQUIRED, "The phone needs your phone PIN to unlock"
    right = arm_pin.matches(arm_pin.read_hash(PHONE_PIN_HASH_ENV), str(pin))
    if right is None:
        return PHONE_PIN_NOT_SET, ("No phone PIN is set: run  py -3 tools/set_phone_pin.py  on the desk PC, "
                                   "then unlock again")
    if right:
        _failures = 0
        return None, ""
    _failures += 1
    logger.warning("PHONE: wrong phone PIN (%d in a row)", _failures)
    if _failures >= PHONE_PIN_MAX_FAILURES:
        _failures = 0
        _locked_until = now + PHONE_PIN_LOCKOUT_SEC
        return PHONE_PIN_LOCKED, f"Too many wrong PINs: the phone is locked for {int(PHONE_PIN_LOCKOUT_SEC)} s"
    return PHONE_PIN_INVALID, "Wrong PIN"


def reset_for_tests() -> None:
    global _failures, _locked_until
    _failures = 0
    _locked_until = 0.0
